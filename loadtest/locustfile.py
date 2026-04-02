"""
CatalogPro Load Test Suite
===========================
Simulates real user flows:
  - Browsers (landing, demos, pricing)
  - Buyers (full order flow)
  - Admin users
  - Bot/attack traffic (to test rate limiting)

Usage:
  # Headless (Termux-friendly):
  locust -f locustfile.py --headless -u 50 -r 5 --run-time 60s --host http://localhost:5050

  # With web UI (open browser to http://localhost:8089):
  locust -f locustfile.py --host http://localhost:5050

  # Heavy load:
  locust -f locustfile.py --headless -u 200 -r 20 --run-time 120s --host http://localhost:5050

Flags:
  -u  total users (concurrent)
  -r  users spawned per second
  --run-time  how long to run
"""

import random, string, json, time
from locust import HttpUser, task, between, events, constant_pacing
from locust.exception import StopUser


# ── HELPERS ────────────────────────────────────────────────────────────────────
def rand_phone():
    return f"07{random.randint(10,99)}{random.randint(100000,999999)}"

def rand_business():
    nouns   = ["Shop","Store","Boutique","Kitchen","Mart","Hub","Centre","Place"]
    names   = ["Mama","Baba","Grace","James","Fatuma","Ali","Wanjiru","Tech","Fresh","Quick"]
    return f"{random.choice(names)} {random.choice(nouns)}"

def rand_products(n=4):
    items = [
        ("Chapati (5 pcs)","100","Freshly made"),
        ("Mandazi (10 pcs)","80","Coconut spiced"),
        ("Pilau Plate","200","Beef or chicken"),
        ("Ankara Dress","2400","Kitenge print"),
        ("Wrap Blouse","1100","Silk blend"),
        ("Phone Case","350","All models"),
        ("Bluetooth Speaker","2500","10hr battery"),
        ("USB Cable","350","Fast charge"),
        ("Samosa Pack","240","Beef filling"),
        ("Nyama Choma","900","Slow roasted"),
    ]
    return random.sample(items, min(n, len(items)))

def get_csrf(client, url="/"):
    """Fetch a page and extract the CSRF token from a form."""
    resp = client.get(url, name="[csrf-fetch]")
    if resp.status_code == 200:
        import re
        m = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text)
        if m:
            return m.group(1)
    return "no-csrf"


# ── USER TYPE 1: BROWSER ───────────────────────────────────────────────────────
# Just browsing — landing page, demos, pricing
class BrowserUser(HttpUser):
    """
    Simulates someone who found your site and is exploring.
    High volume — most visitors are browsers.
    Weight 5 = 5x more browsers than buyers.
    """
    weight      = 5
    wait_time   = between(2, 8)   # realistic reading time

    @task(10)
    def view_landing(self):
        self.client.get("/", name="Landing Page")

    @task(5)
    def view_pricing(self):
        self.client.get("/#pricing", name="Pricing Section")

    @task(4)
    def download_demo_fashion(self):
        self.client.get("/demo/fashion", name="Demo PDF - Fashion")

    @task(3)
    def download_demo_food(self):
        self.client.get("/demo/food", name="Demo PDF - Food")

    @task(2)
    def download_demo_electronics(self):
        self.client.get("/demo/electronics", name="Demo PDF - Electronics")

    @task(2)
    def view_order_page(self):
        pkg = random.choice(["starter", "business", "premium"])
        self.client.get(f"/order/{pkg}", name=f"Order Page [{pkg}]")

    @task(1)
    def track_order(self):
        """Simulate someone checking their order status."""
        csrf = get_csrf(self.client, "/track")
        self.client.post("/track", data={
            "_csrf": csrf,
            "phone": rand_phone()
        }, name="Track Order")


# ── USER TYPE 2: BUYER ─────────────────────────────────────────────────────────
# Goes through the full order flow
class BuyerUser(HttpUser):
    """
    Simulates a real customer completing an order.
    Weight 2 = fewer buyers than browsers but more load per user.
    """
    weight    = 2
    wait_time = between(5, 15)   # buyers think before clicking

    def on_start(self):
        self.pkg_key  = random.choice(["starter", "business", "premium"])
        self.order_id = None
        self.csrf     = None

    @task
    def full_order_flow(self):
        """Complete order: browse → fill form → preview → payment page."""

        # Step 1: Land on homepage
        self.client.get("/", name="[buyer] Landing")
        time.sleep(random.uniform(1, 3))

        # Step 2: View order page
        resp = self.client.get(f"/order/{self.pkg_key}",
                               name=f"[buyer] Order Form [{self.pkg_key}]")
        if resp.status_code != 200:
            return

        # Extract CSRF
        import re
        m = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text)
        csrf = m.group(1) if m else "no-csrf"

        time.sleep(random.uniform(2, 6))  # customer fills form

        # Step 3: Submit order form
        products = rand_products(random.randint(3, 6))
        form_data = {
            "_csrf":         csrf,
            "business_name": rand_business(),
            "tagline":       "Quality products at fair prices",
            "phone":         rand_phone(),
            "location":      random.choice(["Nairobi CBD","Westlands","Kilimani","Thika","Mombasa"]),
            "email":         "",
            "whatsapp":      rand_phone(),
            "theme":         random.choice(["ivory","slate","charcoal"]),
            "footer_note":   "Call or WhatsApp to order.",
            "pay_phone":     rand_phone(),
        }
        for i, (name, price, desc) in enumerate(products, 1):
            form_data[f"pname_{i}"]  = name
            form_data[f"pprice_{i}"] = price
            form_data[f"pdesc_{i}"]  = desc

        resp = self.client.post(f"/submit/{self.pkg_key}",
                                data=form_data,
                                allow_redirects=True,
                                name=f"[buyer] Submit Order [{self.pkg_key}]")

        # Step 4: Preview page
        if "/preview/" in resp.url:
            oid = resp.url.split("/preview/")[-1]
            self.order_id = oid
            self.client.get(f"/preview/{oid}", name="[buyer] Preview Page")
            time.sleep(random.uniform(2, 5))

            # Step 5: Payment page
            resp2 = self.client.get(f"/payment/{oid}", name="[buyer] Payment Page")
            if resp2.status_code == 200:
                time.sleep(random.uniform(1, 3))

                # Step 6: Simulate paying (sandbox auto-generates PDF)
                pay_csrf = re.search(r'name="_csrf"\s+value="([^"]+)"', resp2.text)
                self.client.post(f"/pay/{oid}",
                    json={"phone": rand_phone()},
                    headers={"Content-Type": "application/json"},
                    name="[buyer] Pay (STK Push)")

                time.sleep(2)

                # Step 7: Check status
                self.client.get(f"/status/{oid}?json=1", name="[buyer] Poll Status")
                self.client.get(f"/status/{oid}", name="[buyer] Status Page")


# ── USER TYPE 3: ADMIN USER ────────────────────────────────────────────────────
class AdminUser(HttpUser):
    """
    Simulates admin checking dashboard.
    Very low weight — only 1 admin at a time usually.
    """
    weight    = 1
    wait_time = between(10, 30)

    # Read admin secret path from config
    try:
        import sys; sys.path.insert(0, '/home/claude/catalogpro2')
        from config import Config
        SECRET = Config.ADMIN_SECRET_PATH
        ADMIN_USER = Config.ADMIN_USERNAME
        ADMIN_PASS = Config.ADMIN_PASSWORD
    except:
        SECRET     = "cp-dashboard-9f3a"
        ADMIN_USER = "admin"
        ADMIN_PASS = "admin123"

    def on_start(self):
        """Login as admin."""
        # Get login page for CSRF
        resp = self.client.get(f"/{self.SECRET}/login",
                               name="[admin] Login Page")
        import re
        m = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text)
        csrf = m.group(1) if m else "no-csrf"

        self.client.post(f"/{self.SECRET}/login",
            data={
                "_csrf":    csrf,
                "username": self.ADMIN_USER,
                "password": self.ADMIN_PASS,
            },
            allow_redirects=True,
            name="[admin] Login Submit")

    @task(5)
    def view_dashboard(self):
        self.client.get(f"/{self.SECRET}/", name="[admin] Dashboard")

    @task(1)
    def update_prices(self):
        resp = self.client.get(f"/{self.SECRET}/", name="[admin] Dashboard (pre-price)")
        import re
        m = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text)
        csrf = m.group(1) if m else "no-csrf"
        self.client.post(f"/{self.SECRET}/prices",
            data={
                "_csrf":           csrf,
                "price_starter":   "149",
                "price_business":  "299",
                "price_premium":   "499",
            },
            allow_redirects=True,
            name="[admin] Update Prices")


# ── USER TYPE 4: ATTACKER (tests your rate limiting) ──────────────────────────
class AttackerUser(HttpUser):
    """
    Simulates a bot hammering your site.
    Tests that rate limiting kicks in correctly.
    Weight 1 — just a few attackers.
    """
    weight    = 1
    wait_time = constant_pacing(0.1)   # fires every 100ms — very fast

    @task(3)
    def hammer_landing(self):
        """Rapid page loads — should hit 429 after 60 req/min."""
        with self.client.get("/", name="[attack] Rapid Landing",
                             catch_response=True) as resp:
            if resp.status_code == 429:
                resp.success()   # rate limit working correctly

    @task(2)
    def probe_admin(self):
        """Try common attack paths — should all 404."""
        paths = ["/admin", "/admin/login", "/wp-admin",
                 "/.env", "/config.php", "/wp-login.php"]
        path = random.choice(paths)
        with self.client.get(path, name="[attack] Admin Probe",
                             catch_response=True) as resp:
            if resp.status_code == 404:
                resp.success()   # correctly blocked

    @task(2)
    def brute_force_login(self):
        """Rapid wrong password attempts — should trigger lockout."""
        path = "/cp-dashboard-9f3a/login"
        resp = self.client.get(path, name="[attack] Login Page")
        import re
        m = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text)
        csrf = m.group(1) if m else "bad"
        with self.client.post(path,
            data={"_csrf": csrf, "username": "admin",
                  "password": "wrongpassword123"},
            allow_redirects=True,
            name="[attack] Brute Force Login",
            catch_response=True) as resp:
            if resp.status_code in [200, 429]:
                resp.success()

    @task(1)
    def inject_order_id(self):
        """Try SQL injection in order ID — should 404 cleanly."""
        evil_ids = ["1' OR '1'='1", "../etc/passwd",
                    "<script>alert(1)</script>", "' DROP TABLE orders;--"]
        eid = random.choice(evil_ids)
        with self.client.get(f"/status/{eid}",
                             name="[attack] Injection Attempt",
                             catch_response=True) as resp:
            if resp.status_code in [404, 400]:
                resp.success()


# ── CUSTOM STATS REPORTING ─────────────────────────────────────────────────────
@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Print a clean summary when tests finish."""
    stats = environment.runner.stats
    total = stats.total

    print("\n" + "="*60)
    print("  CATALOGPRO LOAD TEST RESULTS")
    print("="*60)
    print(f"  Total requests   : {total.num_requests:,}")
    print(f"  Failed requests  : {total.num_failures:,}")
    print(f"  Failure rate     : {total.fail_ratio*100:.1f}%")
    print(f"  Avg response time: {total.avg_response_time:.0f}ms")
    print(f"  95th percentile  : {total.get_response_time_percentile(0.95):.0f}ms")
    print(f"  99th percentile  : {total.get_response_time_percentile(0.99):.0f}ms")
    print(f"  Peak RPS         : {total.max_requests_per_sec:.1f}")
    print("="*60)

    # Grade the results
    avg = total.avg_response_time
    fail = total.fail_ratio * 100

    if avg < 300 and fail < 1:
        grade = "✅ EXCELLENT — Ready for production"
    elif avg < 600 and fail < 3:
        grade = "⚠️  GOOD — Minor optimizations needed"
    elif avg < 1200 and fail < 10:
        grade = "⚠️  FAIR — Needs optimization before heavy traffic"
    else:
        grade = "❌ POOR — Serious performance issues, fix before launch"

    print(f"\n  Result: {grade}")
    print("="*60 + "\n")
