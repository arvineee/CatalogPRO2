"""
scheduler.py — Manual jobs only (no background scheduler).
All jobs are triggered manually via the admin dashboard buttons.
"""

import os
import glob
from datetime import datetime


def init_scheduler(app):
    """No-op — APScheduler removed. Free PythonAnywhere doesn't support background threads."""
    pass


def run_backup():
    """Dump MySQL database to timestamped .sql file."""
    from config import Config

    backup_dir = Config.BACKUP_FOLDER
    os.makedirs(backup_dir, exist_ok=True)

    db_url = Config.SQLALCHEMY_DATABASE_URI
    try:
        rest = db_url.split("://", 1)[1]
        userpass, hostdb = rest.rsplit("@", 1)
        user, password = userpass.split(":", 1)
        host, dbname = hostdb.split("/", 1)
        dbname = dbname.split("?")[0]
    except Exception as e:
        raise RuntimeError(f"Could not parse DB URL for backup: {e}")

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(backup_dir, f"backup_{ts}.sql")

    cmd = (
        f'mysqldump --user="{user}" --password="{password}" '
        f'--host="{host}" "{dbname}" > "{out_file}"'
    )
    ret = os.system(cmd)
    if ret != 0:
        raise RuntimeError(f"mysqldump exited with code {ret}")

    all_backups = sorted(glob.glob(os.path.join(backup_dir, "backup_*.sql")))
    for old in all_backups[:-5]:
        try:
            os.remove(old)
        except OSError:
            pass

    print(f"[BACKUP] Saved {out_file}")
    return out_file
