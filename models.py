"""
CatalogPro — SQLAlchemy Models (MySQL via PythonAnywhere)
Replaces database.py entirely.
"""
import uuid, json, random, string
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _gen_order_id():
    return uuid.uuid4().hex[:12].upper()


def _gen_referral_code(name: str = "") -> str:
    prefix = "".join(c for c in name.upper()[:4] if c.isalpha()) or "CAT"
    suffix = "".join(random.choices(string.digits, k=4))
    return f"{prefix}{suffix}"


# ── ORDERS ────────────────────────────────────────────────────────────────────
class Order(db.Model):
    __tablename__ = "orders"

    id            = db.Column(db.String(20),  primary_key=True, default=_gen_order_id)
    business      = db.Column(db.String(200), nullable=False)
    package       = db.Column(db.String(50),  nullable=False)
    amount        = db.Column(db.Integer,     nullable=False)
    phone         = db.Column(db.String(20),  nullable=False, index=True)
    email         = db.Column(db.String(200), nullable=True)
    theme         = db.Column(db.String(50),  default="ivory")
    status        = db.Column(db.String(30),  default="pending", index=True)
    catalog_file  = db.Column(db.String(200), nullable=True)
    mpesa_code    = db.Column(db.String(100), nullable=True)
    catalog_json  = db.Column(db.Text,        nullable=True)   # full order data as JSON
    referral_code = db.Column(db.String(20),  nullable=True)
    discount      = db.Column(db.Integer,     default=0)
    follow_up_sent= db.Column(db.Boolean,     default=False)
    email_sent    = db.Column(db.Boolean,     default=False)
    paid_at       = db.Column(db.DateTime,    nullable=True)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow, index=True)

    # helper: store/retrieve catalog build data
    def set_data(self, data: dict):
        self.catalog_json = json.dumps(data, default=str)

    def get_data(self) -> dict:
        if self.catalog_json:
            try:
                return json.loads(self.catalog_json)
            except Exception:
                pass
        return {}

    def to_dict(self) -> dict:
        return {
            "id":            self.id,
            "business":      self.business,
            "package":       self.package,
            "amount":        self.amount,
            "phone":         self.phone,
            "email":         self.email,
            "theme":         self.theme,
            "status":        self.status,
            "catalog_file":  self.catalog_file,
            "mpesa_code":    self.mpesa_code,
            "referral_code": self.referral_code,
            "discount":      self.discount,
            "follow_up_sent":self.follow_up_sent,
            "paid_at":       str(self.paid_at)  if self.paid_at   else None,
            "created_at":    str(self.created_at) if self.created_at else None,
        }


# ── SETTINGS (key-value store) ────────────────────────────────────────────────
class Setting(db.Model):
    __tablename__ = "settings"
    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        row = cls.query.get(key)
        return row.value if row else default

    @classmethod
    def set(cls, key: str, value: str):
        row = cls.query.get(key)
        if row:
            row.value = value
        else:
            db.session.add(cls(key=key, value=value))
        db.session.commit()


# ── REFERRALS ─────────────────────────────────────────────────────────────────
class Referral(db.Model):
    __tablename__ = "referrals"
    id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    code        = db.Column(db.String(20),  unique=True, nullable=False)
    owner_phone = db.Column(db.String(20),  nullable=False, index=True)
    owner_name  = db.Column(db.String(200), nullable=True)
    uses        = db.Column(db.Integer,     default=0)
    discount    = db.Column(db.Integer,     default=50)   # KSh off for referred user
    created_at  = db.Column(db.DateTime,    default=datetime.utcnow)

    @classmethod
    def create_for(cls, phone: str, name: str = "") -> "Referral":
        """Create or return existing referral code for this phone."""
        existing = cls.query.filter_by(owner_phone=phone).first()
        if existing:
            return existing
        code = _gen_referral_code(name)
        # ensure uniqueness
        while cls.query.filter_by(code=code).first():
            code = _gen_referral_code(name)
        ref = cls(code=code, owner_phone=phone, owner_name=name, discount=50)
        db.session.add(ref)
        db.session.commit()
        return ref

