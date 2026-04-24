# CatalogPro v4 — PythonAnywhere Setup Guide

## 1. Create MySQL Database on PythonAnywhere

1. Log in to PythonAnywhere → **Databases** tab
2. Set a MySQL password (save it!)
3. Under "Create a database", type: `catalogpro`
4. Your full DB name will be: `youruser$catalogpro`
5. Your host will be: `youruser.mysql.pythonanywhere-services.com`

---

## 2. Set Environment Variables

In PythonAnywhere → **Web** tab → scroll to **Environment variables** (or edit your WSGI file):

```bash
DATABASE_URL=mysql+pymysql://youruser:YOURPASSWORD@youruser.mysql.pythonanywhere-services.com/youruser$catalogpro
SECRET_KEY=generate-a-random-64-char-string-here
ADMIN_PASSWORD=your-secure-admin-password
ADMIN_USERNAME=Admin
ADMIN_SECRET_PATH=yoursecretadminpath2024
LIPIA_API_KEY=your-lipia-api-key
GMAIL_USER=yourgmail@gmail.com
GMAIL_PASSWORD=your-gmail-app-password
SUPPORT_WHATSAPP=2547XXXXXXXX
ADMIN_WHATSAPP=2547XXXXXXXX
```

---

## 3. Install Dependencies

In PythonAnywhere Bash console:

```bash
cd ~/catalogpro
pip install --user -r requirements.txt
```

---

## 4. WSGI Configuration

In PythonAnywhere → Web tab → WSGI configuration file, replace with:

```python
import sys, os
sys.path.insert(0, '/home/youruser/catalogpro')
os.environ['DATABASE_URL'] = 'mysql+pymysql://youruser:PASS@youruser.mysql.pythonanywhere-services.com/youruser$catalogpro'
os.environ['SECRET_KEY']   = 'your-secret-key-here'
# ... add other env vars here

from app import app as application
```

---

## 5. Folder Structure

Your app folder should look like:

```
~/catalogpro/
  app.py
  models.py
  config.py
  scheduler.py
  email_utils.py
  lipia.py
  pdf_generator.py
  requirements.txt
  templates/
    base.html
    landing.html
    order.html
    preview.html
    payment.html
    status.html
    track.html
    view.html
    privacy.html
    terms.html
    admin/
      login.html
      dashboard.html
    errors/
      403.html
      404.html
      429.html
  static/
    uploads/
    catalogs/
    demos/
    demo_imgs/
    favicon.ico
  backups/
```

---

## 6. Template Placement

Move the HTML files as follows:
- `admin_dashboard.html` → `templates/admin/dashboard.html`
- `admin_login.html`     → `templates/admin/login.html`
- `403.html`             → `templates/errors/403.html`
- `404.html`             → `templates/errors/404.html`
- `429.html`             → `templates/errors/429.html`
- All others             → `templates/`

---

## 7. Update app.py render_template calls

Make sure these match your folder structure:
```python
render_template("admin/dashboard.html", ...)
render_template("admin/login.html", ...)
render_template("errors/403.html")
render_template("errors/404.html")
render_template("errors/429.html")
```

---

## 8. First Run — Tables Created Automatically

On first load, Flask-SQLAlchemy runs `db.create_all()` which creates:
- `orders` table
- `settings` table
- `referrals` table

No manual SQL needed.

---

## 9. Admin Panel

Access at: `https://yoursite.pythonanywhere.com/ADMIN_SECRET_PATH/`

Default path is set via `ADMIN_SECRET_PATH` env var.

---

## 10. Gmail App Password (for email delivery)

1. Go to Google Account → Security → 2-Step Verification (enable it)
2. Then → App Passwords → Generate one for "Mail"
3. Use that 16-character password as `GMAIL_PASSWORD`

