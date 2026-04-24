"""
CatalogPro v4 — Full rewrite
  • Flask-SQLAlchemy + MySQL (PythonAnywhere)
  • Email delivery of catalog PDF
  • Referral discount system
  • Shareable /view/<order_id> link
  • Live order counter
  • Privacy Policy + Terms pages
  • Revenue chart data endpoint
  • Abandoned order tracking (via APScheduler)
  • WhatsApp support button (in base template)
  • Upsell on success page
"""
import os, functools, time, secrets as _secrets
from datetime   import datetime, timedelta
from flask      import (Flask, render_template, request, redirect, url_for,
                        send_file, session, jsonify, flash, abort, make_response)
from werkzeug.utils import secure_filename
from sqlalchemy import func

from config     import Config
from models     import db, Order, Setting, Referral
from lipia      import stk_push
from pdf_generator import generate_catalog, generate_preview
import threading

app = Flask(__name__)
app.config.from_object(Config)

# ── Database ──────────────────────────────────────────────────────────────────
db.init_app(app)

with app.app_context():
    db.create_all()

# ── Folders ───────────────────────────────────────────────────────────────────
for d in [Config.UPLOAD_FOLDER, Config.CATALOG_FOLDER,
          Config.DEMO_FOLDER,   Config.DEMO_IMG_FOLDER,
          Config.BACKUP_FOLDER]:
    os.makedirs(d, exist_ok=True)

# ── Scheduler ─────────────────────────────────────────────────────────────────
from scheduler import init_scheduler
init_scheduler(app)

# ── Rate limiting ─────────────────────────────────────────────────────────────
_rate_store = {}

def _rate_limit(ip, max_calls=30, window=60):
    now = time.time()
    calls = [t for t in _rate_store.get(ip, []) if now - t < window]
    calls.append(now)
    _rate_store[ip] = calls
    return len(calls) > max_calls

# ── Security headers ──────────────────────────────────────────────────────────
@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"]  = "nosniff"
    resp.headers["X-Frame-Options"]          = "SAMEORIGIN"   # allow iframe on /view
    resp.headers["X-XSS-Protection"]         = "1; mode=block"
    resp.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"]        = "geolocation=(), microphone=()"
    resp.headers["Cache-Control"]             = "no-store, no-cache, must-revalidate"
    resp.headers["Server"]                    = "nginx"
    return resp

# ── CSRF ──────────────────────────────────────────────────────────────────────
def _csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = _secrets.token_hex(24)
    return session["_csrf"]

def _verify_csrf():
    token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
    if not token or token != session.get("_csrf"):
        abort(403)

app.jinja_env.globals["csrf_token"] = _csrf_token

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_client_ip():
    return (request.headers.get("X-Forwarded-For", request.remote_addr) or "").split(",")[0].strip()

def allowed(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXT

def save_upload(f, prefix="img"):
    if f and f.filename and allowed(f.filename):
        ext  = f.filename.rsplit(".", 1)[1].lower()
        name = f"{prefix}_{os.urandom(8).hex()}.{ext}"
        path = os.path.join(Config.UPLOAD_FOLDER, name)
        f.save(path)
        return path
    return None

def get_packages():
    pkgs = {}
    for key, pkg in Config.PACKAGES.items():
        p = dict(pkg)
        stored_price = Setting.get(f"price_{key}")
        if stored_price and stored_price.isdigit():
            p["price"] = int(stored_price)
        offer_orig  = Setting.get(f"offer_orig_{key}")
        offer_label = Setting.get(f"offer_label_{key}")
        offer_until = Setting.get(f"offer_until_{key}")
        if offer_orig and offer_orig.isdigit() and int(offer_orig) > 0:
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
        name  = req.form.get(f"pname_{i}",  "").strip()
        price = req.form.get(f"pprice_{i}", "").strip()
        desc  = req.form.get(f"pdesc_{i}",  "").strip()
        if not name or not price:
            continue
        img_path = None
        if pkg["images"]:
            img_path = save_upload(req.files.get(f"pimg_{i}"), f"p{i}_{os.urandom(4).hex()}")
        products.append({"name": name, "price": price, "description": desc, "image_path": img_path})

    wa  = req.form.get("whatsapp", "").strip()
    qr  = (f"https://wa.me/254{wa.lstrip('0')}" if wa and pkg.get("qr") else None)
    theme = req.form.get("theme", pkg["themes"][0])
    if theme not in pkg["themes"]:
        theme = pkg["themes"][0]

    return {
        "business_name": req.form.get("business_name", "").strip(),
        "tagline":        req.form.get("tagline",       "").strip(),
        "phone":          req.form.get("phone",         "").strip(),
        "location":       req.form.get("location",      "").strip(),
        "email":          req.form.get("email",         "").strip(),
        "whatsapp":       wa,
        "instagram":      req.form.get("instagram",     "").strip(),
        "facebook":       req.form.get("facebook",      "").strip(),
        "footer_note":    req.form.get("footer_note",   "").strip(),
        "theme":          theme,
        "logo_path":      logo_path,
        "qr_link":        qr,
        "products":       products,
        "pay_phone":      req.form.get("pay_phone",     "").strip(),
    }

def _do_generate(order_id: str, mpesa_code: str = "MANUAL", data: dict = None):
    """Generate PDF, update order, send email."""
    order = Order.query.get(order_id)
    if not order:
        return
    if not data:
        data = order.get_data()
    if not data:
        data = {"business_name": order.business, "theme": order.theme, "products": []}
    try:
        fn = generate_catalog(data)
        order.status       = "paid"
        order.catalog_file = fn
        order.mpesa_code   = mpesa_code
        order.paid_at      = datetime.utcnow()
        db.session.commit()

        # Send email with PDF attachment
        if order.email and not order.email_sent:
            try:
                from email_utils import send_catalog
                pdf_path = os.path.join(Config.CATALOG_FOLDER, fn)
                ok = send_catalog(order.email, order.business, order_id, pdf_path)
                if ok:
                    order.email_sent = True
                    db.session.commit()
            except Exception as e:
                print(f"[EMAIL ERROR] {order_id}: {e}")

        # Increment referral use counter
        if order.referral_code:
            ref = Referral.query.filter_by(code=order.referral_code).first()
            if ref:
                ref.uses += 1
                db.session.commit()

    except Exception as e:
        order.status = "error"
        db.session.commit()
        print(f"[PDF ERROR] {order_id}: {e}")

def _ensure_demos():
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
                {"name":"Ankara Maxi Dress","price":"2,400","description":"Hand-printed kitenge","image_path":img("f1.jpg")},
                {"name":"Wrap Blouse","price":"1,100","description":"Silk blend, multiple prints","image_path":img("f2.jpg")},
                {"name":"Wide-Leg Trousers","price":"1,600","description":"High waist, tailored fit","image_path":img("f3.jpg")},
                {"name":"Beaded Clutch","price":"850","description":"Handmade Maasai beadwork","image_path":img("f4.jpg")},
                {"name":"Linen Blazer","price":"3,200","description":"Unstructured, camel & navy","image_path":img("f5.jpg")},
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
                {"name":"Power Bank 20000mAh","price":"2,200","description":"Dual USB + Type-C","image_path":img("t5.jpg")},
                {"name":"Screen Protector","price":"300","description":"Tempered glass, most models","image_path":img("t6.jpg")},
            ],
        },
    }
    for key, data in samples.items():
        dest = os.path.join(Config.DEMO_FOLDER, f"demo_{key}.pdf")
        if not os.path.exists(dest):
            try:
                import shutil as _sh
                fn  = generate_catalog(data)
                src = os.path.join(Config.CATALOG_FOLDER, fn)
                _sh.copy(src, dest)
                print(f"[DEMO] Created demo_{key}.pdf")
            except Exception as e:
                print(f"[DEMO ERROR] {key}: {e}")

# Pre-generate demos on startup (non-blocking)
threading.Thread(target=lambda: _ensure_demos(), daemon=True).start()

# ── Admin helpers ─────────────────────────────────────────────────────────────
SECRET = Config.ADMIN_SECRET_PATH
_login_attempts = {}

def _admin_url(endpoint, **kw):
    base = f"/{SECRET}"
    routes = {
        "admin_login":         f"{base}/login",
        "admin_logout":        f"{base}/logout",
        "admin_dashboard":     f"{base}/",
        "admin_update_prices": f"{base}/prices",
        "admin_mark_paid":     f"{base}/mark-paid/{kw.get('order_id','')}",
        "admin_download":      f"{base}/dl/{kw.get('order_id','')}",
        "admin_delete":        f"{base}/del/{kw.get('order_id','')}",
        "admin_bypass_pay":    f"{base}/bypass-pay/{kw.get('order_id','')}",
        "admin_simulate_stk":  f"{base}/simulate-stk/{kw.get('order_id','')}",
    }
    return routes.get(endpoint, base)

app.jinja_env.globals["admin_url"] = _admin_url
app.jinja_env.globals["support_whatsapp"] = Config.SUPPORT_WHATSAPP

def admin_only(fn):
    @functools.wraps(fn)
    def wrapped(*a, **kw):
        if not session.get("admin_auth"):
            return redirect(f"/{SECRET}/login")
        return fn(*a, **kw)
    return wrapped

# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(413)
def err_413(e):
    flash("Images too large. Resize to under 2MB each and try again.", "error")
    return redirect(url_for("landing")), 413

@app.errorhandler(403)
def err_403(e):
    return render_template("errors/403.html"), 403

@app.errorhandler(404)
def err_404(e):
    return render_template("errors/404.html"), 404

@app.errorhandler(429)
def err_429(e):
    return render_template("errors/429.html"), 429

# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def landing():
    ip = get_client_ip()
    if _rate_limit(ip, 60, 60):
        abort(429)
    # Live stats for the counter
    total_paid = Order.query.filter_by(status="paid").count()
    demos = {
        "fashion":     {"label": "Fashion Boutique",  "icon": "👗"},
        "food":        {"label": "Food & Catering",   "icon": "🍽"},
        "electronics": {"label": "Electronics Shop",  "icon": "📱"},
    }
    return render_template("landing.html",
                           packages=get_packages(),
                           theme_meta=Config.THEME_META,
                           demos=demos,
                           total_paid=total_paid)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/demo/<n>")
def demo_download(n):
    if n not in {"fashion", "food", "electronics"}:
        abort(404)
    path = os.path.join(Config.DEMO_FOLDER, f"demo_{n}.pdf")
    if not os.path.exists(path):
        flash("Demo generating, please try again in 30 seconds.", "error")
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
    if _rate_limit(ip, 10, 60):
        abort(429)

    pkgs = get_packages()
    pkg  = pkgs.get(pkg_key)
    if not pkg:
        abort(404)

    d = _collect_form(request, pkg)
    if not d["products"]:
        flash("Please add at least one product.", "error")
        return redirect(url_for("order", pkg_key=pkg_key))

    pay_phone     = d.pop("pay_phone", None) or d["phone"]
    referral_code = request.form.get("referral_code", "").strip().upper()
    discount      = 0

    # Validate referral
    if referral_code:
        ref = Referral.query.filter_by(code=referral_code).first()
        if ref:
            discount = ref.discount
        else:
            referral_code = ""  # invalid — ignore silently

    final_amount = max(1, pkg["price"] - discount)

    # Create order in DB
    order = Order(
        business      = d["business_name"],
        package       = pkg_key,
        amount        = final_amount,
        phone         = pay_phone,
        email         = d.get("email", ""),
        theme         = d["theme"],
        status        = "pending",
        referral_code = referral_code or None,
        discount      = discount,
    )
    db.session.add(order)
    db.session.commit()

    # Store full build data in DB (not session — needed for background threads)
    order.set_data(d)
    db.session.commit()

    return redirect(url_for("preview_page", order_id=order.id))


@app.route("/preview/<order_id>")
def preview_page(order_id):
    if not order_id.isalnum() or len(order_id) > 20:
        abort(404)
    order = Order.query.get(order_id)
    if not order:
        abort(404)
    pkgs = get_packages()
    pkg  = pkgs[order.package]
    data = order.get_data()

    prev_key  = f"prev_{order_id}"
    prev_file = session.get(prev_key)
    if not prev_file or not os.path.exists(os.path.join(Config.CATALOG_FOLDER, prev_file)):
        if data:
            try:
                prev_file = generate_preview(data)
                session[prev_key] = prev_file
            except Exception as e:
                print(f"[PREVIEW ERROR] {e}")
                prev_file = None
    return render_template("preview.html", order=order, pkg=pkg, prev_file=prev_file)


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
    order = Order.query.get(order_id)
    if not order:
        abort(404)
    pkgs = get_packages()
    return render_template("payment.html", order=order, pkg=pkgs[order.package])


@app.route("/pay/<order_id>", methods=["POST"])
def pay(order_id):
    ip = get_client_ip()
    if _rate_limit(ip, 5, 60):
        return jsonify({"ok": False, "msg": "Too many requests. Wait a minute."}), 429
    if not order_id.isalnum():
        return jsonify({"ok": False, "msg": "Invalid order"}), 400

    order = Order.query.get(order_id)
    if not order:
        return jsonify({"ok": False, "msg": "Order not found"}), 404

    phone = (request.json or {}).get("phone", order.phone)
    phone = "".join(c for c in phone if c.isdigit() or c == "+")

    order.status = "awaiting_payment"
    db.session.commit()

    # Capture data now (in request context) for background thread
    captured_data = order.get_data()

    def _run_payment(phone_num, oid, order_data):
        try:
            o = Order.query.get(oid)
            resp = stk_push(phone_num, o.amount, oid)
            print(f"STK RESPONSE for {oid}:", resp)
            if resp.get("ok"):
                mpesa_code = (resp.get("reference")
                              or resp.get("refference")
                              or resp.get("data", {}).get("refference")
                              or "LIPIA")
                _do_generate(oid, mpesa_code=mpesa_code, data=order_data)
            else:
                o2 = Order.query.get(oid)
                if o2:
                    o2.status = "failed"
                    db.session.commit()
        except Exception as e:
            print(f"[PAYMENT THREAD ERROR] {oid}: {e}")
            try:
                o3 = Order.query.get(oid)
                if o3:
                    o3.status = "failed"
                    db.session.commit()
            except Exception:
                pass

    threading.Thread(target=_run_payment, args=(phone, order_id, captured_data), daemon=True).start()
    return jsonify({"ok": True, "queued": True, "msg": "STK Push initiated. Check your phone."})


@app.route("/mpesa/callback", methods=["POST"])
def mpesa_callback():
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})


@app.route("/status/<order_id>")
def status(order_id):
    if not order_id.isalnum():
        abort(404)
    order = Order.query.get(order_id)
    if not order:
        abort(404)
    if request.args.get("json"):
        return jsonify({"status": order.status, "file": order.catalog_file})
    pkgs = get_packages()
    pkg  = pkgs[order.package]

    # Referral code for customer to share
    referral = None
    if order.status == "paid":
        referral = Referral.create_for(order.phone, order.business)

    # Upsell: suggest Premium if they bought Starter/Business
    upsell = None
    if order.status == "paid" and order.package != "premium":
        next_pkg = "business" if order.package == "starter" else "premium"
        upsell = pkgs.get(next_pkg)

    return render_template("status.html", order=order, pkg=pkg,
                           referral=referral, upsell=upsell,
                           upsell_key="business" if order.package=="starter" else "premium")


@app.route("/download/<order_id>")
def download(order_id):
    if not order_id.isalnum():
        abort(404)
    order = Order.query.get(order_id)
    if not order or order.status != "paid" or not order.catalog_file:
        return redirect(url_for("status", order_id=order_id))
    path = os.path.join(Config.CATALOG_FOLDER, order.catalog_file)
    if not os.path.exists(path):
        abort(404)
    name = "".join(c for c in order.business if c.isalnum() or c in "_ ")
    return send_file(path, as_attachment=True, download_name=f"{name}_Catalog.pdf")


@app.route("/view/<order_id>")
def view_catalog(order_id):
    """Shareable link — renders PDF in-browser with branding."""
    if not order_id.isalnum():
        abort(404)
    order = Order.query.get(order_id)
    if not order or order.status != "paid" or not order.catalog_file:
        abort(404)
    pkgs = get_packages()
    return render_template("view.html", order=order, pkg=pkgs[order.package])


@app.route("/view-pdf/<order_id>")
def view_pdf(order_id):
    """Serve PDF inline for the /view shareable page."""
    if not order_id.isalnum():
        abort(404)
    order = Order.query.get(order_id)
    if not order or order.status != "paid" or not order.catalog_file:
        abort(404)
    path = os.path.join(Config.CATALOG_FOLDER, order.catalog_file)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="application/pdf")


@app.route("/track", methods=["GET", "POST"])
def track():
    ip = get_client_ip()
    if _rate_limit(ip, 20, 60):
        abort(429)
    orders = None
    phone  = ""
    if request.method == "POST":
        _verify_csrf()
        phone  = request.form.get("phone", "").strip()
        phone  = "".join(c for c in phone if c.isdigit() or c in "+ ")
        if phone:
            orders = Order.query.filter_by(phone=phone).order_by(Order.created_at.desc()).all()
        else:
            orders = []
    return render_template("track.html", orders=orders, phone=phone,
                           packages=get_packages())


@app.route("/api/validate-referral", methods=["POST"])
def validate_referral():
    code = (request.json or {}).get("code", "").strip().upper()
    if not code:
        return jsonify({"ok": False, "msg": "Enter a referral code."})
    ref = Referral.query.filter_by(code=code).first()
    if ref:
        return jsonify({"ok": True, "discount": ref.discount,
                        "msg": f"✓ Code applied — KSh {ref.discount} off!"})
    return jsonify({"ok": False, "msg": "Invalid referral code."})


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route(f"/{SECRET}/login", methods=["GET", "POST"])
def admin_login():
    ip = get_client_ip()
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if time.time() - t < Config.LOGIN_LOCKOUT_MINUTES * 60]
    if len(attempts) >= Config.MAX_LOGIN_ATTEMPTS:
        return render_template("admin/login.html", locked=True,
                               remaining=Config.LOGIN_LOCKOUT_MINUTES), 429

    if request.method == "POST":
        _verify_csrf()
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == Config.ADMIN_USERNAME and password == Config.ADMIN_PASSWORD:
            _login_attempts.pop(ip, None)
            session.clear()
            session["admin_auth"] = True
            session["admin_ip"]   = ip
            session.permanent     = True
            return redirect(f"/{SECRET}/")
        else:
            attempts.append(time.time())
            _login_attempts[ip] = attempts
            flash("Incorrect username or password.", "error")

    return render_template("admin/login.html", locked=False)


@app.route(f"/{SECRET}/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route(f"/{SECRET}/")
@admin_only
def admin_dashboard():
    if session.get("admin_ip") != get_client_ip():
        session.clear()
        return redirect(f"/{SECRET}/login")

    pkgs = get_packages()
    orders = Order.query.order_by(Order.created_at.desc()).all()

    # Stats
    paid_orders = [o for o in orders if o.status == "paid"]
    today = datetime.utcnow().date()
    total_revenue = sum(o.amount for o in paid_orders)
    today_paid    = [o for o in paid_orders if o.paid_at and o.paid_at.date() == today]

    stats = {
        "total":   len(orders),
        "paid":    len(paid_orders),
        "revenue": total_revenue,
        "today":   len(today_paid),
    }

    # 30-day revenue chart data
    chart_labels = []
    chart_data   = []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        rev = sum(o.amount for o in paid_orders if o.paid_at and o.paid_at.date() == day)
        chart_labels.append(day.strftime("%d %b"))
        chart_data.append(rev)

    # Follow-up list (abandoned, follow_up_sent=True but not paid)
    followups = Order.query.filter(
        Order.follow_up_sent == True,
        Order.status.in_(["pending", "awaiting_payment"]),
    ).order_by(Order.created_at.desc()).limit(20).all()

    return render_template("admin/dashboard.html",
                           orders=orders, stats=stats, packages=pkgs,
                           secret=SECRET,
                           chart_labels=chart_labels,
                           chart_data=chart_data,
                           followups=followups)


@app.route(f"/{SECRET}/prices", methods=["POST"])
@admin_only
def admin_update_prices():
    _verify_csrf()
    for key in Config.PACKAGES:
        val = request.form.get(f"price_{key}", "").strip()
        if val and val.isdigit() and 0 < int(val) < 100000:
            Setting.set(f"price_{key}", val)
        orig  = request.form.get(f"offer_orig_{key}", "").strip()
        label = request.form.get(f"offer_label_{key}", "").strip()
        until = request.form.get(f"offer_until_{key}", "").strip()
        Setting.set(f"offer_orig_{key}",  orig  if orig and orig.isdigit() else "0")
        Setting.set(f"offer_label_{key}", label or "LIMITED TIME OFFER")
        Setting.set(f"offer_until_{key}", until)
    flash("Prices and offers updated.", "success")
    return redirect(f"/{SECRET}/")


@app.route(f"/{SECRET}/bypass-pay/<order_id>", methods=["POST"])
@admin_only
def admin_bypass_pay(order_id):
    _verify_csrf()
    if not order_id.isalnum():
        abort(400)
    order = Order.query.get(order_id)
    if not order:
        flash(f"Order {order_id} not found.", "error")
        return redirect(f"/{SECRET}/")
    if order.status == "paid":
        flash(f"Order {order_id} already paid.", "error")
        return redirect(f"/{SECRET}/")
    ref = request.form.get("mpesa_ref", "MANUAL-BYPASS").strip() or "MANUAL-BYPASS"
    _do_generate(order_id, ref)
    flash(f"Order {order_id} marked paid. Ref: {ref}", "success")
    return redirect(f"/{SECRET}/")


@app.route(f"/{SECRET}/simulate-stk/<order_id>", methods=["POST"])
@admin_only
def admin_simulate_stk(order_id):
    _verify_csrf()
    if not order_id.isalnum():
        abort(400)
    order = Order.query.get(order_id)
    if not order:
        flash("Order not found.", "error")
        return redirect(f"/{SECRET}/")
    if order.status == "paid":
        flash("Already paid.", "error")
        return redirect(f"/{SECRET}/")
    _do_generate(order_id, f"SIM{order_id[:6]}")
    flash(f"STK simulation done for {order_id}.", "success")
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
    order = Order.query.get(order_id)
    if order:
        db.session.delete(order)
        db.session.commit()
    return redirect(f"/{SECRET}/")


# Block common probes
for probe in ["/admin", "/admin/", "/wp-admin", "/wp-login.php", "/.env"]:
    app.add_url_rule(probe, probe, lambda: abort(404))


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host="0.0.0.0", port=5050)

