import sqlite3, uuid
from datetime import datetime
from config import Config

def get_db():
    c = sqlite3.connect(Config.DATABASE)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = get_db()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            id           TEXT PRIMARY KEY,
            business     TEXT NOT NULL,
            package      TEXT NOT NULL,
            amount       INTEGER NOT NULL,
            phone        TEXT NOT NULL,
            theme        TEXT DEFAULT 'ivory',
            status       TEXT DEFAULT 'pending',
            catalog_file TEXT,
            mpesa_code   TEXT,
            created_at   TEXT NOT NULL,
            paid_at      TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
            ip         TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            success    INTEGER DEFAULT 0
        );
    """)
    c.commit(); c.close()

# ── Settings (admin price overrides, etc.) ────────────────────────────────────
def get_setting(key):
    c = get_db()
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    c.close()
    return row["value"] if row else None

def set_setting(key, value):
    c = get_db()
    c.execute("""INSERT INTO settings(key,value) VALUES(?,?)
                 ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, value))
    c.commit(); c.close()

# ── Login security ────────────────────────────────────────────────────────────
def record_login_attempt(ip, success=False):
    c = get_db()
    c.execute("INSERT INTO login_attempts(ip, attempted_at, success) VALUES(?,?,?)",
              (ip, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 1 if success else 0))
    c.commit(); c.close()

def is_ip_locked(ip):
    """True if IP has too many failed attempts in the lockout window."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(minutes=Config.LOGIN_LOCKOUT_MINUTES)
              ).strftime("%Y-%m-%d %H:%M:%S")
    c = get_db()
    count = c.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE ip=? AND success=0 AND attempted_at > ?",
        (ip, cutoff)
    ).fetchone()[0]
    c.close()
    return count >= Config.MAX_LOGIN_ATTEMPTS

def clear_login_attempts(ip):
    c = get_db()
    c.execute("DELETE FROM login_attempts WHERE ip=?", (ip,))
    c.commit(); c.close()

# ── Orders ────────────────────────────────────────────────────────────────────
def create_order(business, package, amount, phone, theme="ivory"):
    oid = uuid.uuid4().hex[:10].upper()
    c = get_db()
    c.execute("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
              (oid, business, package, amount, phone, theme,
               "pending", None, None,
               datetime.now().strftime("%Y-%m-%d %H:%M:%S"), None))
    c.commit(); c.close()
    return oid

def get_order(oid):
    c = get_db()
    r = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    c.close()
    return dict(r) if r else None

def get_orders_by_phone(phone):
    phone = phone.strip().replace(" ", "")
    c = get_db()
    rows = c.execute(
        "SELECT * FROM orders WHERE REPLACE(phone,' ','') LIKE ? ORDER BY created_at DESC",
        (f"%{phone[-9:]}%",)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def update_order(oid, **kw):
    c = get_db()
    sets = ", ".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE orders SET {sets} WHERE id=?", list(kw.values()) + [oid])
    c.commit(); c.close()

def all_orders(limit=200):
    c = get_db()
    rows = c.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
                     (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def stats():
    c = get_db()
    total   = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    paid    = c.execute("SELECT COUNT(*) FROM orders WHERE status='paid'").fetchone()[0]
    revenue = c.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='paid'").fetchone()[0]
    today   = c.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at)=DATE('now') AND status='paid'").fetchone()[0]
    c.close()
    return {"total": total, "paid": paid, "revenue": revenue, "today": today}
