import os, secrets
BASE = os.path.dirname(__file__)

class Config:
    # ── Core ──────────────────────────────────────────────────────────────
    SECRET_KEY   = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    DATABASE     = os.path.join(BASE, "catalogpro.db")

    # ── Admin — hidden URL, no /admin button on site ───────────────────────
    # Change ADMIN_SECRET_PATH to something only you know e.g. "myfarm2024"
    ADMIN_SECRET_PATH = os.environ.get("ADMIN_SECRET_PATH", "path")
    ADMIN_USERNAME    = 'Admin'
    ADMIN_PASSWORD    = 'pass'

    # ── Security ───────────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SAMESITE  = "Lax"
    SESSION_COOKIE_SECURE    = False   # Set True in production (HTTPS)
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour admin sessions
    WTF_CSRF_ENABLED         = True
    MAX_LOGIN_ATTEMPTS       = 5       # lock after this many failures
    LOGIN_LOCKOUT_MINUTES    = 15

    # ── Lipia M-Pesa ──────────────────────────────────────────────────────
    # Get your API key from your Lipia dashboard → Security Tab
    LIPIA_API_KEY = os.environ.get("LIPIA_API_KEY","")

    # ── Files ─────────────────────────────────────────────────────────────
    UPLOAD_FOLDER  = os.path.join(BASE, "static", "uploads")
    CATALOG_FOLDER = os.path.join(BASE, "static", "catalogs")
    DEMO_FOLDER    = os.path.join(BASE, "static", "demos")
    DEMO_IMG_FOLDER= os.path.join(BASE, "static", "demo_imgs")
    ALLOWED_EXT    = {"png", "jpg", "jpeg", "webp"}
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB — supports 35 product images + logo (Premium)

    # ── Packages ──────────────────────────────────────────────────────────
    PACKAGES = {
        "starter": {
            "label": "Starter", "price": 149, "max_products": 10,
            "images": False, "logo": False,
            "themes": ["ivory", "slate"],
            "qr": False, "tagline": "Clean & professional",
            "color": "#4a90d9",
            "features": [
                "Up to 10 products", "2 clean themes",
                "Business contact details", "WhatsApp-ready PDF", "Instant download",
            ],
        },
        "business": {
            "label": "Business", "price": 299, "max_products": 20,
            "images": True, "logo": True,
            "themes": ["ivory", "slate", "charcoal", "forest"],
            "qr": False, "tagline": "Most popular",
            "color": "#c0392b", "highlight": True,
            "features": [
                "Up to 20 products", "Product photos",
                "Your business logo", "4 premium themes",
                "Contact & location details", "Instant download",
            ],
        },
        "premium": {
            "label": "Premium", "price": 499, "max_products": 35,
            "images": True, "logo": True,
            "themes": ["ivory", "slate", "charcoal", "forest", "noir"],
            "qr": True, "tagline": "Complete package",
            "color": "#a07830",
            "features": [
                "Up to 35 products", "Product photos", "Business logo",
                "5 exclusive themes", "WhatsApp QR code",
                "Social media handles", "Custom footer message", "Instant download",
            ],
        },
    }

    THEME_META = {
        "ivory":    {"label": "Ivory",    "desc": "Warm white, timeless",   "preview": "#f9f6f1", "accent": "#1a1a1a"},
        "slate":    {"label": "Slate",    "desc": "Cool grey, corporate",   "preview": "#2c3e50", "accent": "#e8d5b0"},
        "charcoal": {"label": "Charcoal", "desc": "Dark, bold, modern",     "preview": "#1c1c1e", "accent": "#e94560"},
        "forest":   {"label": "Forest",   "desc": "Deep green, natural",    "preview": "#1a2e1a", "accent": "#c8e6c9"},
        "noir":     {"label": "Noir",     "desc": "Black & gold, luxury",   "preview": "#0a0a0a", "accent": "#c9a84c"},
    }
