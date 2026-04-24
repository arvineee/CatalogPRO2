"""
CatalogPro — Scheduler (PythonAnywhere-compatible)

BackgroundScheduler is NOT supported on PythonAnywhere.
Instead, each job is a plain function called by standalone scripts
that you schedule via the PythonAnywhere Tasks tab:

  Task 1 (every hour):   python /home/CatalogPRO/CatalogPRO2/run_abandoned.py
  Task 2 (daily 08:00):  python /home/CatalogPRO/CatalogPRO2/run_daily_summary.py
  Task 3 (weekly Sun):   python /home/CatalogPRO/CatalogPRO2/run_backup.py
"""
import os, subprocess
from datetime import datetime, timedelta
from config import Config


def init_scheduler(app):
    """No-op on PythonAnywhere — jobs run via scheduled task scripts."""
    print("[SCHEDULER] PythonAnywhere mode: using scheduled task scripts instead of BackgroundScheduler.")


# ── Job 1: Flag abandoned orders ──────────────────────────────────────────────
def check_abandoned(app):
    with app.app_context():
        try:
            from models import db, Order
            cutoff = datetime.utcnow() - timedelta(minutes=45)
            abandoned = Order.query.filter(
                Order.status.in_(["pending", "awaiting_payment"]),
                Order.created_at <= cutoff,
                Order.follow_up_sent == False,
            ).all()

            for order in abandoned:
                order.follow_up_sent = True
                print(f"[FOLLOWUP] Flagged order {order.id} — {order.business} — {order.phone}")

            if abandoned:
                db.session.commit()
                print(f"[FOLLOWUP] {len(abandoned)} abandoned orders flagged.")
            else:
                print("[FOLLOWUP] No abandoned orders found.")
        except Exception as e:
            print(f"[FOLLOWUP ERROR] {e}")


# ── Job 2: Daily summary email ─────────────────────────────────────────────────
def daily_summary(app):
    with app.app_context():
        try:
            from models import db, Order
            from email_utils import send_admin_daily_summary
            from sqlalchemy import func

            today = datetime.utcnow().date()

            today_orders = Order.query.filter(
                Order.status == "paid",
                func.date(Order.paid_at) == today,
            ).all()

            today_revenue = sum(o.amount for o in today_orders)
            total_orders  = Order.query.filter_by(status="paid").count()
            total_revenue = db.session.query(func.sum(Order.amount)).filter_by(status="paid").scalar() or 0
            pending       = Order.query.filter(Order.status.in_(["pending", "awaiting_payment"])).count()

            by_pkg = {}
            for o in today_orders:
                by_pkg.setdefault(o.package, [0, 0])
                by_pkg[o.package][0] += 1
                by_pkg[o.package][1] += o.amount

            send_admin_daily_summary({
                "date":          str(today),
                "today_orders":  len(today_orders),
                "today_revenue": today_revenue,
                "total_orders":  total_orders,
                "total_revenue": total_revenue,
                "pending":       pending,
                "by_package":    [(pkg, v[0], v[1]) for pkg, v in by_pkg.items()],
            })
            print(f"[DAILY SUMMARY] Sent for {today}.")
        except Exception as e:
            print(f"[DAILY SUMMARY ERROR] {e}")


# ── Job 3: MySQL backup ────────────────────────────────────────────────────────
def run_backup():
    """Dump MySQL DB to a timestamped SQL file in the backups folder."""
    os.makedirs(Config.BACKUP_FOLDER, exist_ok=True)
    uri = Config.SQLALCHEMY_DATABASE_URI
    try:
        from urllib.parse import urlparse
        p    = urlparse(uri.replace("mysql+pymysql://", "mysql://"))
        user = p.username
        pwd  = p.password
        host = p.hostname
        db   = p.path.lstrip("/")
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        out  = os.path.join(Config.BACKUP_FOLDER, f"catalogpro_{ts}.sql")
        env  = os.environ.copy()
        env["MYSQL_PWD"] = pwd or ""
        cmd  = ["mysqldump", "-u", user, f"-h{host}", db]
        with open(out, "w") as f:
            subprocess.run(cmd, stdout=f, env=env, check=True)
        print(f"[BACKUP] Saved → {out}")
        # Keep only last 5 backups
        backups = sorted(
            [os.path.join(Config.BACKUP_FOLDER, x)
             for x in os.listdir(Config.BACKUP_FOLDER) if x.endswith(".sql")]
        )
        for old in backups[:-5]:
            os.remove(old)
            print(f"[BACKUP] Removed old backup: {old}")
    except Exception as e:
        print(f"[BACKUP ERROR] {e}")

