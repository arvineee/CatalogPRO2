"""
CatalogPro — Email Utilities (Gmail SMTP, no extra libraries)
"""
import smtplib, os
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText
from email.mime.base      import MIMEBase
from email                import encoders
from config               import Config


def _smtp():
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.ehlo()
    server.starttls()
    server.login(Config.GMAIL_USER, Config.GMAIL_PASSWORD)
    return server


def send_catalog(to_email: str, business: str, order_id: str, pdf_path: str) -> bool:
    """Send the catalog PDF as an attachment to the customer."""
    if not Config.EMAIL_ENABLED or not to_email:
        return False
    if not os.path.exists(pdf_path):
        return False
    try:
        msg = MIMEMultipart()
        msg["From"]    = f"CatalogPro <{Config.GMAIL_USER}>"
        msg["To"]      = to_email
        msg["Subject"] = f"Your CatalogPro PDF — {business}"

        body = f"""Hello,

Thank you for using CatalogPro! Your professional PDF catalog is attached.

Business:  {business}
Order ID:  {order_id}

HOW TO USE YOUR CATALOG:
  • Share it directly on your WhatsApp status
  • Forward it to customers and groups
  • Post the PDF on your Facebook business page
  • Print copies to display in your shop

You can re-download your catalog any time at:
  https://felixkirui.pythonanywhere.com/status/{order_id}

Need help? WhatsApp us: wa.me/{Config.SUPPORT_WHATSAPP}

— CatalogPro Kenya
"""
        msg.attach(MIMEText(body, "plain"))

        # Attach PDF
        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        safe_name = "".join(c for c in business if c.isalnum() or c in "_ ")
        part.add_header("Content-Disposition", f'attachment; filename="{safe_name}_Catalog.pdf"')
        msg.attach(part)

        server = _smtp()
        server.sendmail(Config.GMAIL_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


def send_admin_daily_summary(stats: dict) -> bool:
    """Email the admin a daily revenue + order summary."""
    if not Config.EMAIL_ENABLED:
        return False
    try:
        msg = MIMEMultipart()
        msg["From"]    = f"CatalogPro <{Config.GMAIL_USER}>"
        msg["To"]      = Config.GMAIL_USER
        msg["Subject"] = f"📊 CatalogPro Daily Summary — {stats.get('date','')}"

        rows = "\n".join(
            f"  {p.title():10s}  x{c}  KSh {r:,}"
            for p, c, r in stats.get("by_package", [])
        )
        body = f"""CatalogPro Daily Summary
========================
Date:         {stats.get('date','')}
Orders today: {stats.get('today_orders', 0)}
Revenue today:KSh {stats.get('today_revenue', 0):,}

Total orders: {stats.get('total_orders', 0)}
Total revenue:KSh {stats.get('total_revenue', 0):,}

Breakdown by package (today):
{rows or '  No paid orders today.'}

Pending (unpaid): {stats.get('pending', 0)} orders

— CatalogPro Auto-Report
"""
        msg.attach(MIMEText(body, "plain"))
        server = _smtp()
        server.sendmail(Config.GMAIL_USER, Config.GMAIL_USER, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[DAILY EMAIL ERROR] {e}")
        return False

