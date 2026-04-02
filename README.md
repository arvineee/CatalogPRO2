# CatalogPro v2

Professional PDF Catalog Generator SaaS for Kenyan businesses.

## Quick Start (Termux)

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5050
```

## M-Pesa Setup
```bash
export MPESA_CONSUMER_KEY="your_key"
export MPESA_CONSUMER_SECRET="your_secret"
export MPESA_SHORTCODE="your_shortcode"
export MPESA_PASSKEY="your_passkey"
export MPESA_CALLBACK_URL="https://your-public-url/mpesa/callback"
export MPESA_ENV="production"
```

## Admin Panel
Visit /admin — default: admin / admin123
Change via: export ADMIN_USER="you" ADMIN_PASS="strongpassword"

## Packages
| Package  | Price    | Products | Photos | Logo | Themes |
|----------|----------|----------|--------|------|--------|
| Starter  | KSh 149  | 10       | ✗      | ✗    | 2      |
| Business | KSh 299  | 20       | ✓      | ✓    | 4      |
| Premium  | KSh 499  | 35       | ✓      | ✓    | 5 + QR |

## Themes: Ivory · Slate · Charcoal · Forest · Noir

## Key Features
- Live PDF preview (partial, watermarked) before paying
- Track order by phone number
- 3 downloadable demo catalogs on homepage
- Admin dashboard with revenue stats
- M-Pesa STK Push (sandbox works out of the box)
- 5 refined, professional PDF themes
