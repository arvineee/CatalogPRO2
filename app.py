"""
CatalogPro v3 — Production-ready Flask app
Security: hidden admin URL, rate limiting, CSRF tokens,
          security headers, login lockout, session hardening
"""
import os, functools, time
from datetime import datetime
from flask import (Flask, render_template, request, redirect, url_for,
                   send_file, session, jsonify, flash, abort, make_response)
from werkzeug.utils import secure_filename

from config import Config
from database import (init_db, create_order, get_order, update_order,
                      all_orders, stats, get_orders_by_phone,
                      get_setting, set_setting,
                      record_login_attempt, is_ip_locked, clear_login_attempts)
import threading
from lipia import stk_push
from pdf_generator import generate_catalog, generate_preview

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

for d in [Config.UPLOAD_FOLDER, Config.CATALOG_FOLDER,
          Config.DEMO_FOLDER, Config.DEMO_IMG_FOLDER]:
    os.makedirs(d, exist_ok=True)

with app.app_context():
    init_db()

# ── RATE LIMITING (simple in-memory) ─────────────────────────────────────────
_rate_store = {}   # ip -> [timestamps]

def _rate_limit(ip, max_calls=30, window=60):
    """Return True if the IP is over the rate limit."""
    now = time.time()
    calls = [t for t in _rate_store.get(ip, []) if now - t < window]
    calls.append(now)
    _rate_store[ip] = calls
    return len(calls) > max_calls

# ── SECURITY HEADERS ─────────────────────────────────────────────────────────
@app.after_request
def add_security_headers(resp):
    resp.headers["X-Content-Type-Options"]  = "nosniff"
    resp.headers["X-Frame-Options"]          = "DENY"
    resp.headers["X-XSS-Protection"]         = "1; mode=block"
    resp.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"]        = "geolocation=(), microphone=(), camera=()"
    resp.headers["Cache-Control"]             = "no-store, no-cache, must-revalidate"
    # Hide server info
    resp.headers["Server"] = "nginx"
    return resp

# ── CSRF PROTECTION ──────────────────────────────────────────────────────────
import secrets as _secrets

def _csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = _secrets.token_hex(24)
    return session["_csrf"]

def _verify_csrf():
    token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
    if not token or token != session.get("_csrf"):
        abort(403)

app.jinja_env.globals["csrf_token"] = _csrf_token

# ── HELPERS ───────────────────────────────────────────────────────────────────
def get_client_ip():
    return (request.headers.get("X-Forwarded-For", request.remote_addr)
            or "").split(",")[0].strip()

def allowed(fn):
    return ("." in fn and
            fn.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXT)

def save_upload(f, prefix="img"):
    if f and f.filename and allowed(f.filename):
        ext = f.filename.rsplit(".", 1)[1].lower()
        name = f"{prefix}_{os.urandom(8).hex()}.{ext}"
        path = os.path.join(Config.UPLOAD_FOLDER, name)
        f.save(path)
        return path
    return None

def admin_only(fn):
    @functools.wraps(fn)
    def wrapped(*a, **kw):
        if not session.get("admin_auth"):
            return redirect(url_for("admin_login"))
        return fn(*a, **kw)
    return wrapped

def get_packages():
    """Return packages with live prices + offer data from DB."""
    pkgs = {}
    for key, pkg in Config.PACKAGES.items():
        p = dict(pkg)
        stored_price = get_setting(f"price_{key}")
        if stored_price and stored_price.isdigit():
            p["price"] = int(stored_price)
        offer_orig  = get_setting(f"offer_orig_{key}")
        offer_label = get_setting(f"offer_label_{key}")
        offer_until = get_setting(f"offer_until_{key}")
        if offer_orig and offer_orig.isdigit():
            p["offer_orig"]  = int(offer_orig)
            p["offer_label"] = offer_label or "LIMITED TIME OFFER"
            p["offer_until"] = offer_until or ""
        else:
            p["offer_orig"]  = None
            p["offer_label"] = None
            p["offer_until"] = None
        pkgs[key] = p
    return pkgs

def _collect_form(req, pkg):
    logo_path = None
    if pkg["logo"]:
        logo_path = save_upload(req.files.get("logo"), "logo")

    products = []
    for i in range(1, pkg["max_products"] + 1):
        name  = req.form.get(f"pname_{i}", "").strip()
        price = req.form.get(f"pprice_{i}", "").strip()
        desc  = req.form.get(f"pdesc_{i}", "").strip()
        if not name or not price:
            continue
        img_path = None
        if pkg["images"]:
            img_path = save_upload(req.files.get(f"pimg_{i}"),
                                   f"p{i}_{os.urandom(4).hex()}")
        products.append({"name": name, "price": price,
                         "description": desc, "image_path": img_path})

    wa  = req.form.get("whatsapp", "").strip()
    qr  = (f"https://wa.me/254{wa.lstrip('0')}"
           if wa and pkg.get("qr") else None)
    theme = req.form.get("theme", pkg["themes"][0])
    if theme not in pkg["themes"]:
        theme = pkg["themes"][0]

    return {
        "business_name": req.form.get("business_name", "").strip(),
        "tagline":        req.form.get("tagline", "").strip(),
        "phone":          req.form.get("phone", "").strip(),
        "location":       req.form.get("location", "").strip(),
        "email":          req.form.get("email", "").strip(),
        "whatsapp":       wa,
        "instagram":      req.form.get("instagram", "").strip(),
        "facebook":       req.form.get("facebook", "").strip(),
        "footer_note":    req.form.get("footer_note", "").strip(),
        "theme":          theme,
        "logo_path":      logo_path,
        "qr_link":        qr,
        "products":       products,
        "pay_phone":      req.form.get("pay_phone", "").strip(),
    }

def _do_generate(order_id, mpesa_code="MANUAL", data=None):
    # `data` can be passed directly (e.g. from a background thread that has no
    # Flask request context and therefore cannot access `session`).
    if not data:
        # Try session first (only works inside a request context)
        try:
            data = session.get(f"cd_{order_id}")
        except RuntimeError:
            data = None
    if not data:
        order = get_order(order_id)
        if not order:
            return
        data = {"business_name": order["business"],
                "theme": order["theme"], "products": []}
    try:
        fn = generate_catalog(data)
        update_order(order_id, status="paid", catalog_file=fn,
                     mpesa_code=mpesa_code,
                     paid_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    except Exception as e:
        update_order(order_id, status="error")
        print(f"[PDF ERROR] {order_id}: {e}")

def _ensure_demos():
    """Generate demo PDFs with real product images if not present."""
    import shutil
    IMG = Config.DEMO_IMG_FOLDER

    def img(fn):
        p = os.path.join(IMG, fn)
        return p if os.path.exists(p) else None

    samples = {
        "fashion": {
            "business_name": "ZURI BOUTIQUE", "tagline": "Contemporary African Fashion",
            "phone": "0712 000 001", "location": "Westlands, Nairobi",
            "email": "", "whatsapp": "0712000001", "instagram": "zuri_boutique",
            "facebook": "", "footer_note": "Order via WhatsApp for same-day delivery.",
            "theme": "ivory", "logo_path": None, "qr_link": None,
            "products": [
                {"name":"Ankara Maxi Dress","price":"2,400","description":"Hand-printed kitenge, sizes 8-18","image_path":img("f1.jpg")},
                {"name":"Wrap Blouse","price":"1,100","description":"Silk blend, multiple prints","image_path":img("f2.jpg")},
                {"name":"Wide-Leg Trousers","price":"1,600","description":"High waist, tailored fit","image_path":img("f3.jpg")},
                {"name":"Beaded Clutch","price":"850","description":"Handmade Maasai beadwork","image_path":img("f4.jpg")},
                {"name":"Linen Blazer","price":"3,200","description":"Unstructured, camel and navy","image_path":img("f5.jpg")},
                {"name":"Kanga Set","price":"1,800","description":"Top and skirt, certified cotton","image_path":img("f6.jpg")},
            ],
        },
        "food": {
            "business_name": "DELA KITCHEN", "tagline": "Authentic Kenyan Home Cooking",
            "phone": "0722 000 002", "location": "Kilimani, Nairobi",
            "email": "", "whatsapp": "0722000002", "instagram": "dela_kitchen",
            "facebook": "", "footer_note": "Min order KSh 500. Delivery Mon-Sat 8am-7pm.",
            "theme": "forest", "logo_path": None, "qr_link": None,
            "products": [
                {"name":"Nyama Choma 1kg","price":"900","description":"Slow-roasted, with kachumbari","image_path":img("d1.jpg")},
                {"name":"Pilau (per portion)","price":"200","description":"Spiced rice, beef or chicken","image_path":img("d2.jpg")},
                {"name":"Mukimo Plate","price":"180","description":"Traditional potato and greens","image_path":img("d3.jpg")},
                {"name":"Chapati (5 pcs)","price":"100","description":"Soft, layered, freshly made","image_path":img("d4.jpg")},
                {"name":"Mandazi (10 pcs)","price":"80","description":"Coconut-spiced, fried to order","image_path":img("d5.jpg")},
                {"name":"Samosa Pack (12)","price":"240","description":"Beef or vegetable, with chutney","image_path":img("d6.jpg")},
            ],
        },
        "electronics": {
            "business_name": "TECH HUB KE", "tagline": "Quality Electronics. Fair Prices.",
            "phone": "0733 000 003", "location": "CBD, Nairobi",
            "email": "sales@techhubke.com", "whatsapp": "0733000003",
            "instagram": "", "facebook": "Tech Hub Kenya",
            "footer_note": "6-month warranty on all items. Free delivery in CBD.",
            "theme": "charcoal", "logo_path": None, "qr_link": None,
            "products": [
                {"name":"Bluetooth Speaker","price":"2,500","description":"10-hour battery, waterproof IPX5","image_path":img("t1.jpg")},
                {"name":"Car Phone Holder","price":"450","description":"Universal magnetic, 360 rotation","image_path":img("t2.jpg")},
                {"name":"USB-C Cable 2m","price":"350","description":"Fast charge 65W, braided nylon","image_path":img("t3.jpg")},
                {"name":"Wireless Earbuds","price":"3,800","description":"ANC, 28hr total playback","image_path":img("t4.jpg")},
                {"name":"Power Bank 20000mAh","price":"2,200","description":"Dual USB + Type-C, LED indicator","image_path":img("t5.jpg")},
                {"name":"Screen Protector","price":"300","description":"Tempered glass, most models","image_path":img("t6.jpg")},
            ],
        },
    }

    for key, data in samples.items():
        dest = os.path.join(Config.DEMO_FOLDER, f"demo_{key}.pdf")
        if not os.path.exists(dest):
            try:
                fn  = generate_catalog(data)
                src = os.path.join(Config.CATALOG_FOLDER, fn)
                shutil.copy(src, dest)
                print(f"[DEMO] Created demo_{key}.pdf with images")
            except Exception as e:
                print(f"[DEMO ERROR] {key}: {e}")

# ── ERROR HANDLERS ─────────────────────────────────────────────────────────────
@app.errorhandler(413)
def err_413(e):
    from flask import request as _req
    if _req.path.startswith("/submit"):
        flash("Your images are too large. Resize them to under 2MB each and try again.", "error")
        pkg_key = _req.path.split("/")[-1]
        return redirect(url_for("order", pkg_key=pkg_key))
    return render_template("errors/413.html"), 413

@app.errorhandler(403)
def err_403(e):
    return render_template("errors/403.html"), 403

@app.errorhandler(404)
def err_404(e):
    return render_template("errors/404.html"), 404

@app.errorhandler(429)
def err_429(e):
    return render_template("errors/429.html"), 429

# ── PUBLIC ROUTES ──────────────────────────────────────────────────────────────
@app.route("/")
def landing():
    ip = get_client_ip()
    if _rate_limit(ip, max_calls=60, window=60):
        abort(429)
    _ensure_demos()
    demos = {
        "fashion":     {"label": "Fashion Boutique",  "icon": "👗"},
        "food":        {"label": "Food & Catering",   "icon": "🍽"},
        "electronics": {"label": "Electronics Shop",  "icon": "📱"},
    }
    return render_template("landing.html", packages=get_packages(),
                           theme_meta=Config.THEME_META, demos=demos)

@app.route("/demo/<n>")
def demo_download(n):
    if n not in {"fashion", "food", "electronics"}:
        abort(404)
    _ensure_demos()
    path = os.path.join(Config.DEMO_FOLDER, f"demo_{n}.pdf")
    if not os.path.exists(path):
        flash("Demo not ready yet, please try again.", "error")
        return redirect(url_for("landing"))
    return send_file(path, as_attachment=False,
                     download_name=f"CatalogPro_Sample_{n.title()}.pdf")

@app.route("/order/<pkg_key>")
def order(pkg_key):
    pkgs = get_packages()
    if pkg_key not in pkgs:
        abort(404)
    return render_template("order.html", pkg=pkgs[pkg_key], pkg_key=pkg_key,
                           theme_meta=Config.THEME_META)

@app.route("/submit/<pkg_key>", methods=["POST"])
def submit(pkg_key):
    _verify_csrf()
    ip = get_client_ip()
    if _rate_limit(ip, max_calls=10, window=60):
        abort(429)

    pkgs = get_packages()
    pkg  = pkgs.get(pkg_key)
    if not pkg:
        abort(404)

    d = _collect_form(request, pkg)
    if not d["products"]:
        flash("Please add at least one product.", "error")
        return redirect(url_for("order", pkg_key=pkg_key))

    pay_phone = d.pop("pay_phone", None) or d["phone"]
    order_id  = create_order(d["business_name"], pkg_key,
                              pkg["price"], pay_phone, d["theme"])
    session[f"cd_{order_id}"] = d
    return redirect(url_for("preview_page", order_id=order_id))

@app.route("/preview/<order_id>")
def preview_page(order_id):
    # Sanitize order_id
    if not order_id.isalnum() or len(order_id) > 20:
        abort(404)
    order = get_order(order_id)
    if not order:
        abort(404)
    pkgs = get_packages()
    pkg  = pkgs[order["package"]]
    data = session.get(f"cd_{order_id}")
    prev_key  = f"prev_{order_id}"
    prev_file = session.get(prev_key)

    if not prev_file or not os.path.exists(
            os.path.join(Config.CATALOG_FOLDER, prev_file)):
        if data:
            try:
                prev_file = generate_preview(data)
                session[prev_key] = prev_file
            except Exception as e:
                print(f"[PREVIEW ERROR] {e}")
                prev_file = None

    return render_template("preview.html", order=order, pkg=pkg,
                           prev_file=prev_file)

@app.route("/preview-pdf/<order_id>")
def serve_preview(order_id):
    if not order_id.isalnum():
        abort(404)
    prev_file = session.get(f"prev_{order_id}")
    if not prev_file:
        abort(404)
    path = os.path.join(Config.CATALOG_FOLDER, prev_file)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="application/pdf")

@app.route("/payment/<order_id>")
def payment(order_id):
    if not order_id.isalnum():
        abort(404)
    order = get_order(order_id)
    if not order:
        abort(404)
    pkgs = get_packages()
    return render_template("payment.html", order=order,
                           pkg=pkgs[order["package"]])

@app.route("/pay/<order_id>", methods=["POST"])
def pay(order_id):
    """
    Initiates payment via STK Push. Fixes previous TypeError by 
    ensuring a valid JSON response is returned and the background 
    thread is correctly started.
    """
    ip = get_client_ip()
    if _rate_limit(ip, max_calls=5, window=60):
        return jsonify({"ok": False, "msg": "Too many requests. Wait a minute."}), 429
    if not order_id.isalnum():
        return jsonify({"ok": False, "msg": "Invalid order"}), 400

    order = get_order(order_id)
    if not order:
        return jsonify({"ok": False, "msg": "Order not found"}), 404

    phone = (request.json or {}).get("phone", order["phone"])
    phone = "".join(c for c in phone if c.isdigit() or c == "+")

    # Mark as awaiting immediately so the frontend knows to start polling
    update_order(order_id, status="awaiting_payment")

    # Capture session data NOW (in request context) so the background thread
    # doesn't need to touch Flask session at all.
    captured_data = session.get(f"cd_{order_id}")

    # Defined helper for the background thread execution
    def _run_payment(phone_num, oid, order_data):
        try:
            current_order = get_order(oid)
            resp = stk_push(phone_num, current_order["amount"], oid)

            print(f"STK RESPONSE for {oid}:", resp)

            if resp.get("ok"):
                # Lipia has a typo in their API: "refference" (double-f)
                mpesa_code = (resp.get("reference")
                              or resp.get("refference")
                              or resp.get("data", {}).get("refference")
                              or resp.get("data", {}).get("reference")
                              or "LIPIA")
                _do_generate(oid, mpesa_code=mpesa_code, data=order_data)
            else:
                update_order(oid, status="failed")

        except Exception as e:
            print(f"Payment thread error for {oid}: {e}")
            update_order(oid, status="failed")

    # Correctly start the background thread
    threading.Thread(target=_run_payment, args=(phone, order_id, captured_data)).start()

    # Return valid response to frontend — "queued" tells the JS to start polling
    return jsonify({"ok": True, "queued": True, "msg": "STK Push initiated. Check your phone."})

# /mpesa/callback is no longer used — Lipia handles STK push synchronously.
# Kept as a no-op endpoint for compatibility if anything still pings it.
@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

@app.route("/status/<order_id>")
def status(order_id):
    if not order_id.isalnum():
        abort(404)
    order = get_order(order_id)
    if not order:
        abort(404)
    if request.args.get("json"):
        return jsonify({"status": order["status"],
                        "file": order.get("catalog_file")})
    pkgs = get_packages()
    return render_template("status.html", order=order,
                           pkg=pkgs[order["package"]])

@app.route("/download/<order_id>")
def download(order_id):
    if not order_id.isalnum():
        abort(404)
    order = get_order(order_id)
    if not order or order["status"] != "paid" or not order.get("catalog_file"):
        return redirect(url_for("status", order_id=order_id))
    path = os.path.join(Config.CATALOG_FOLDER, order["catalog_file"])
    if not os.path.exists(path):
        abort(404)
    name = "".join(c for c in order["business"] if c.isalnum() or c in "_ ")
    return send_file(path, as_attachment=True,
                     download_name=f"{name}_Catalog.pdf")

@app.route("/track", methods=["GET", "POST"])
def track():
    ip = get_client_ip()
    if _rate_limit(ip, max_calls=20, window=60):
        abort(429)
    orders = None
    phone  = ""
    if request.method == "POST":
        _verify_csrf()
        phone  = request.form.get("phone", "").strip()
        phone  = "".join(c for c in phone if c.isdigit() or c in "+ ")
        orders = get_orders_by_phone(phone) if phone else []
    return render_template("track.html", orders=orders, phone=phone,
                           packages=get_packages())

# ── HIDDEN ADMIN — URL is a secret path, NOT /admin ───────────────────────────
# Access via: /<ADMIN_SECRET_PATH>/login

def _admin_url(endpoint, **kw):
    """Build admin URL using the secret path prefix."""
    base = f"/{Config.ADMIN_SECRET_PATH}"
    routes = {
        "admin_login":       f"{base}/login",
        "admin_logout":      f"{base}/logout",
        "admin_dashboard":   f"{base}/",
        "admin_update_prices": f"{base}/prices",
        "admin_mark_paid":   f"{base}/mark-paid/{kw.get('order_id','')}",
        "admin_download":    f"{base}/dl/{kw.get('order_id','')}",
        "admin_delete":      f"{base}/del/{kw.get('order_id','')}",
    }
    return routes.get(endpoint, base)

app.jinja_env.globals["admin_url"] = _admin_url

SECRET = Config.ADMIN_SECRET_PATH

@app.route(f"/{SECRET}/login", methods=["GET", "POST"])
def admin_login():
    ip = get_client_ip()
    if is_ip_locked(ip):
        remaining = Config.LOGIN_LOCKOUT_MINUTES
        return render_template("admin/login.html",
                               locked=True, remaining=remaining), 429

    if request.method == "POST":
        _verify_csrf()
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if (username == Config.ADMIN_USERNAME and
                password == Config.ADMIN_PASSWORD):
            record_login_attempt(ip, success=True)
            clear_login_attempts(ip)
            session.clear()
            session["admin_auth"] = True
            session["admin_ip"]   = ip   # session bound to IP
            session.permanent     = True
            return redirect(f"/{SECRET}/")
        else:
            record_login_attempt(ip, success=False)
            flash("Incorrect username or password.", "error")

    return render_template("admin/login.html", locked=False)

@app.route(f"/{SECRET}/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("landing"))

@app.route(f"/{SECRET}/")
@admin_only
def admin_dashboard():
    # Session IP check — if IP changes, force re-login
    if session.get("admin_ip") != get_client_ip():
        session.clear()
        return redirect(f"/{SECRET}/login")
    pkgs = get_packages()
    return render_template("admin/dashboard.html",
                           orders=all_orders(), stats=stats(),
                           packages=pkgs,
                           secret=SECRET)

@app.route(f"/{SECRET}/prices", methods=["POST"])
@admin_only
def admin_update_prices():
    _verify_csrf()
    for key in Config.PACKAGES:
        # Current price
        val = request.form.get(f"price_{key}", "").strip()
        if val and val.isdigit() and 0 < int(val) < 100000:
            set_setting(f"price_{key}", val)
        # Offer: original crossed-out price
        orig = request.form.get(f"offer_orig_{key}", "").strip()
        if orig and orig.isdigit() and int(orig) > 0:
            set_setting(f"offer_orig_{key}", orig)
        elif orig == "":
            set_setting(f"offer_orig_{key}", "0")
        # Offer label
        label = request.form.get(f"offer_label_{key}", "").strip()
        set_setting(f"offer_label_{key}", label or "LIMITED TIME OFFER")
        # Offer expiry datetime string
        until = request.form.get(f"offer_until_{key}", "").strip()
        set_setting(f"offer_until_{key}", until)
    flash("Prices and offers updated. Changes are live now.", "success")
    return redirect(f"/{SECRET}/")


@app.route(f"/{SECRET}/bypass-pay/<order_id>", methods=["POST"])
@admin_only
def admin_bypass_pay(order_id):
    _verify_csrf()
    if not order_id.isalnum():
        abort(400)
    order = get_order(order_id)
    if not order:
        flash(f"Order {order_id} not found.", "error")
        return redirect(f"/{SECRET}/")
    if order["status"] == "paid":
        flash(f"Order {order_id} already paid.", "error")
        return redirect(f"/{SECRET}/")
    ref = request.form.get("mpesa_ref", "MANUAL-BYPASS").strip() or "MANUAL-BYPASS"
    _do_generate(order_id, ref)
    flash(f"Order {order_id} marked paid and PDF generated. Ref: {ref}", "success")
    return redirect(f"/{SECRET}/")


@app.route(f"/{SECRET}/simulate-stk/<order_id>", methods=["POST"])
@admin_only
def admin_simulate_stk(order_id):
    _verify_csrf()
    if not order_id.isalnum():
        abort(400)
    order = get_order(order_id)
    if not order:
        flash("Order not found.", "error")
        return redirect(f"/{SECRET}/")
    if order["status"] == "paid":
        flash("Already paid.", "error")
        return redirect(f"/{SECRET}/")
    fake_code = f"SIM{order_id[:6]}"
    _do_generate(order_id, fake_code)
    flash(f"STK simulation complete for order {order_id}. PDF generated. Code: {fake_code}", "success")
    return redirect(f"/{SECRET}/")

@app.route(f"/{SECRET}/mark-paid/<order_id>", methods=["POST"])
@admin_only
def admin_mark_paid(order_id):
    _verify_csrf()
    if not order_id.isalnum():
        abort(400)
    order = get_order(order_id)
    if order and order["status"] != "paid":
        _do_generate(order_id, "MANUAL")
    return redirect(f"/{SECRET}/")

@app.route(f"/{SECRET}/dl/<order_id>")
@admin_only
def admin_download(order_id):
    if not order_id.isalnum():
        abort(400)
    return redirect(url_for("download", order_id=order_id))

@app.route(f"/{SECRET}/del/<order_id>", methods=["POST"])
@admin_only
def admin_delete(order_id):
    _verify_csrf()
    if not order_id.isalnum():
        abort(400)
    from database import get_db
    c = get_db()
    c.execute("DELETE FROM orders WHERE id=?", (order_id,))
    c.commit(); c.close()
    return redirect(f"/{SECRET}/")

# Block common attack paths
@app.route("/admin")
@app.route("/admin/")
@app.route("/admin/login")
@app.route("/wp-admin")
@app.route("/wp-login.php")
@app.route("/.env")
@app.route("/config.php")
def block_probes():
    abort(404)

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=5050)


