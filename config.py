"""
CatalogPro — Configuration
"""
import os, secrets
BASE = os.path.dirname(__file__)


class Config:
    # ── Core ──────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))

    # ── MySQL via PythonAnywhere ───────────────────────────────────────────────
    # Set DATABASE_URL in your PythonAnywhere environment:
    #   mysql+pymysql://YOUR_PA_USER:YOUR_DB_PASS@YOUR_PA_USER.mysql.pythonanywhere-services.com/YOUR_PA_USER$catalogpro
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///catalogpro.db"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle":  280,   # PythonAnywhere drops idle connections after ~5 min
        "pool_pre_ping": True,
        "pool_timeout":  20,
        "pool_size":     5,
        "max_overflow":  2,
    }
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Admin (hidden URL) ────────────────────────────────────────────────────
    ADMIN_SECRET_PATH = os.environ.get("ADMIN_SECRET_PATH", "")
    ADMIN_USERNAME    = os.environ.get("ADMIN_USERNAME", "")
    ADMIN_PASSWORD    = os.environ.get("ADMIN_PASSWORD", "")

    # ── Security ──────────────────────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY      = True
    SESSION_COOKIE_SAMESITE      = "Lax"
    SESSION_COOKIE_SECURE        = True   # set True in production (HTTPS)
    PERMANENT_SESSION_LIFETIME   = 3600
    MAX_LOGIN_ATTEMPTS           = 5
    LOGIN_LOCKOUT_MINUTES        = 15

    # ── M-Pesa / Lipia ────────────────────────────────────────────────────────
    LIPIA_API_KEY = os.environ.get("LIPIA_API_KEY", "")

    # ── Email (Gmail SMTP) ────────────────────────────────────────────────────
    GMAIL_USER     = os.environ.get("GMAIL_USER",     "")          # your@gmail.com
    GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")          # Gmail App Password
    EMAIL_ENABLED  = bool(os.environ.get("GMAIL_USER", ""))

    # ── WhatsApp Support ──────────────────────────────────────────────────────
    SUPPORT_WHATSAPP = os.environ.get("SUPPORT_WHATSAPP", "")  # international format

    # ── Admin WhatsApp (for daily summary & follow-up alerts) ─────────────────
    ADMIN_WHATSAPP = os.environ.get("ADMIN_WHATSAPP", "")

    # ── Files ─────────────────────────────────────────────────────────────────
    UPLOAD_FOLDER   = os.path.join(BASE, "static", "uploads")
    CATALOG_FOLDER  = os.path.join(BASE, "static", "catalogs")
    DEMO_FOLDER     = os.path.join(BASE, "static", "demos")
    DEMO_IMG_FOLDER = os.path.join(BASE, "static", "demo_imgs")
    BACKUP_FOLDER   = os.path.join(BASE, "backups")
    ALLOWED_EXT     = {"png", "jpg", "jpeg", "webp"}
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024   # 50 MB

    # ── Referral ──────────────────────────────────────────────────────────────
    REFERRAL_DISCOUNT_KSH = 50   # discount given to new customer using a referral code

    # ── Packages ──────────────────────────────────────────────────────────────
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

