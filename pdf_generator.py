"""
CatalogPro v2 – Professional PDF Generator
Design principle: Quiet confidence. Every element earns its place.
Inspired by luxury brand lookbooks and high-end retail catalogs.
"""
import os, io, uuid
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, white, black, Color
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image as RLImage, PageBreak
)
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage
import qrcode
from config import Config

W, H = A4

# ── THEME DEFINITIONS ─────────────────────────────────────────────────────────
THEMES = {
    "ivory": {
        "page_bg":    HexColor("#f9f6f1"),
        "header_bg":  HexColor("#1a1a1a"),
        "header_txt": HexColor("#f9f6f1"),
        "accent":     HexColor("#1a1a1a"),
        "accent2":    HexColor("#8b7355"),
        "card_bg":    HexColor("#ffffff"),
        "card_border":HexColor("#e8e0d8"),
        "body_txt":   HexColor("#1a1a1a"),
        "sub_txt":    HexColor("#6b6560"),
        "price_txt":  HexColor("#1a1a1a"),
        "rule":       HexColor("#d4c9bc"),
        "dark": False,
    },
    "slate": {
        "page_bg":    HexColor("#f4f6f8"),
        "header_bg":  HexColor("#2c3e50"),
        "header_txt": HexColor("#f0e6cc"),
        "accent":     HexColor("#2c3e50"),
        "accent2":    HexColor("#c0a96e"),
        "card_bg":    HexColor("#ffffff"),
        "card_border":HexColor("#dce3ea"),
        "body_txt":   HexColor("#1c2833"),
        "sub_txt":    HexColor("#5d6d7e"),
        "price_txt":  HexColor("#2c3e50"),
        "rule":       HexColor("#bdc6ce"),
        "dark": False,
    },
    "charcoal": {
        "page_bg":    HexColor("#1c1c1e"),
        "header_bg":  HexColor("#111111"),
        "header_txt": HexColor("#f0f0f0"),
        "accent":     HexColor("#e94560"),
        "accent2":    HexColor("#e94560"),
        "card_bg":    HexColor("#2a2a2c"),
        "card_border":HexColor("#3a3a3c"),
        "body_txt":   HexColor("#f0f0f0"),
        "sub_txt":    HexColor("#8e8e93"),
        "price_txt":  HexColor("#e94560"),
        "rule":       HexColor("#3a3a3c"),
        "dark": True,
    },
    "forest": {
        "page_bg":    HexColor("#f2f5f2"),
        "header_bg":  HexColor("#1a2e1a"),
        "header_txt": HexColor("#d4ecd4"),
        "accent":     HexColor("#1a2e1a"),
        "accent2":    HexColor("#4a8c4a"),
        "card_bg":    HexColor("#ffffff"),
        "card_border":HexColor("#c8dbc8"),
        "body_txt":   HexColor("#1a2e1a"),
        "sub_txt":    HexColor("#4a6a4a"),
        "price_txt":  HexColor("#1a5c1a"),
        "rule":       HexColor("#b0ccb0"),
        "dark": False,
    },
    "noir": {
        "page_bg":    HexColor("#0d0d0d"),
        "header_bg":  HexColor("#000000"),
        "header_txt": HexColor("#c9a84c"),
        "accent":     HexColor("#c9a84c"),
        "accent2":    HexColor("#a07830"),
        "card_bg":    HexColor("#1a1a1a"),
        "card_border":HexColor("#2a2a2a"),
        "body_txt":   HexColor("#e8e8e8"),
        "sub_txt":    HexColor("#888888"),
        "price_txt":  HexColor("#c9a84c"),
        "rule":       HexColor("#2a2a2a"),
        "dark": True,
    },
}

def _prep_image(path, max_w_pt, max_h_pt):
    try:
        img = PILImage.open(path).convert("RGB")
        img.thumbnail(Config.MAX_IMAGE_SIZE if hasattr(Config,'MAX_IMAGE_SIZE') else (600,600), PILImage.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        buf.seek(0)
        rl = RLImage(buf)
        r = min(max_w_pt / rl.drawWidth, max_h_pt / rl.drawHeight)
        rl.drawWidth *= r; rl.drawHeight *= r
        return rl
    except:
        return None

def _make_qr(text, size_pt):
    qr = qrcode.QRCode(box_size=5, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
    rl = RLImage(buf)
    r = size_pt / max(rl.drawWidth, rl.drawHeight)
    rl.drawWidth *= r; rl.drawHeight *= r
    return rl

def _ps(name, **kw):
    base = getSampleStyleSheet()["Normal"]
    return ParagraphStyle(name, parent=base, **kw)


class PageBackground:
    """Canvas callback to paint page background."""
    def __init__(self, color):
        self.color = color
    def __call__(self, cv, doc):
        cv.saveState()
        cv.setFillColor(self.color)
        cv.rect(0, 0, W, H, fill=1, stroke=0)
        cv.restoreState()


def generate_catalog(data: dict, watermark: bool = False) -> str:
    """
    Generate a professional PDF catalog.
    data keys: business_name, tagline, phone, location, email,
                whatsapp, instagram, facebook, footer_note,
                theme, logo_path, qr_link, products[]
    watermark: if True, stamp PREVIEW diagonally (for partial previews)
    Returns filename only.
    """
    theme_key = data.get("theme", "ivory")
    t = THEMES.get(theme_key, THEMES["ivory"])

    filename = f"catalog_{uuid.uuid4().hex[:10]}.pdf"
    filepath = os.path.join(Config.CATALOG_FOLDER, filename)

    os.makedirs(Config.CATALOG_FOLDER, exist_ok=True)

    FULL_W  = 17.8*cm
    COL_GAP = 0.35*cm
    COL_W   = (FULL_W - COL_GAP) / 2

    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=1.6*cm, rightMargin=1.6*cm,
        topMargin=1.4*cm, bottomMargin=1.6*cm,
    )

    bg_cb = PageBackground(t["page_bg"])

    def on_page(cv, doc):
        bg_cb(cv, doc)
        if watermark:
            cv.saveState()
            cv.setFont("Helvetica-Bold", 52)
            cv.setFillColor(HexColor("#cccccc") if not t["dark"] else HexColor("#333333"))
            cv.setFillAlpha(0.18)
            cv.translate(W/2, H/2)
            cv.rotate(35)
            cv.drawCentredString(0, 0, "PREVIEW")
            cv.rotate(-35)
            cv.translate(-W/2, -H/2)
            cv.restoreState()

    story = []

    # ── STYLES ──────────────────────────────────────────────────────────────────
    S = {
        "biz":     _ps("biz",     fontName="Helvetica-Bold",   fontSize=22, textColor=t["header_txt"], alignment=TA_CENTER, spaceAfter=3, leading=26),
        "tagline": _ps("tag",     fontName="Helvetica",        fontSize=9,  textColor=HexColor("#b0a090") if not t["dark"] else HexColor("#909090"), alignment=TA_CENTER, spaceAfter=0),
        "contact": _ps("contact", fontName="Helvetica",        fontSize=8,  textColor=t["header_txt"],  alignment=TA_CENTER, spaceAfter=0, leading=13),
        "sec_hdr": _ps("sechdr",  fontName="Helvetica-Bold",   fontSize=7,  textColor=t["accent2"],     alignment=TA_LEFT,   spaceAfter=0, letterSpacing=2),
        "pname":   _ps("pname",   fontName="Helvetica-Bold",   fontSize=9.5,textColor=t["body_txt"],    spaceAfter=2, leading=12),
        "pdesc":   _ps("pdesc",   fontName="Helvetica",        fontSize=7.5,textColor=t["sub_txt"],     spaceAfter=3, leading=10),
        "price":   _ps("price",   fontName="Helvetica-Bold",   fontSize=11, textColor=t["price_txt"],   alignment=TA_RIGHT,  spaceAfter=0),
        "social":  _ps("social",  fontName="Helvetica",        fontSize=7.5,textColor=t["accent2"],     alignment=TA_CENTER),
        "footer":  _ps("footer",  fontName="Helvetica",        fontSize=6.5,textColor=t["sub_txt"],     alignment=TA_CENTER),
        "qr_lbl":  _ps("qrlbl",   fontName="Helvetica",        fontSize=7.5,textColor=t["sub_txt"],     alignment=TA_CENTER),
    }

    # ── HEADER ──────────────────────────────────────────────────────────────────
    hdr_rows = []

    if data.get("logo_path") and os.path.exists(data["logo_path"]):
        logo = _prep_image(data["logo_path"], 2.2*cm, 1.5*cm)
        if logo:
            logo.hAlign = "CENTER"
            hdr_rows.append([logo])

    hdr_rows.append([Paragraph(data.get("business_name","").upper(), S["biz"])])
    if data.get("tagline"):
        hdr_rows.append([Paragraph(data["tagline"], S["tagline"])])

    # Contact line inside header
    parts = []
    if data.get("phone"):    parts.append(data["phone"])
    if data.get("location"): parts.append(data["location"])
    if data.get("email"):    parts.append(data["email"])
    if parts:
        hdr_rows.append([Spacer(1, 4)])
        hdr_rows.append([Paragraph("  ·  ".join(parts), S["contact"])])

    hdr = Table(hdr_rows, colWidths=[FULL_W])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), t["header_bg"]),
        ("TOPPADDING",    (0,0),(-1,-1), 18),
        ("BOTTOMPADDING", (0,-1),(-1,-1), 18),
        ("LEFTPADDING",   (0,0),(-1,-1), 20),
        ("RIGHTPADDING",  (0,0),(-1,-1), 20),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(hdr)

    # Thin accent line under header
    story.append(HRFlowable(width="100%", thickness=2, color=t["accent2"], spaceAfter=0, spaceBefore=0))

    # Social handles (slim bar)
    socials = []
    if data.get("whatsapp"):  socials.append(f"WhatsApp: {data['whatsapp']}")
    if data.get("instagram"): socials.append(f"@{data['instagram']}")
    if data.get("facebook"):  socials.append(data["facebook"])
    if socials:
        soc_tbl = Table([[Paragraph("  ·  ".join(socials), S["social"])]], colWidths=[FULL_W])
        soc_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), t["header_bg"]),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ]))
        story.append(soc_tbl)
        story.append(HRFlowable(width="100%", thickness=1, color=t["rule"], spaceAfter=0, spaceBefore=0))

    story.append(Spacer(1, 0.4*cm))

    # ── SECTION LABEL ───────────────────────────────────────────────────────────
    story.append(Paragraph("PRODUCTS & SERVICES", S["sec_hdr"]))
    story.append(HRFlowable(width="100%", thickness=0.75, color=t["rule"], spaceBefore=4, spaceAfter=10))

    # ── PRODUCT GRID ────────────────────────────────────────────────────────────
    products = data.get("products", [])
    has_images = any(p.get("image_path") for p in products)
    IMG_H = 3.2*cm

    pairs = [products[i:i+2] for i in range(0, len(products), 2)]

    for pair in pairs:
        cells = []
        for p in pair:
            inner = []

            # Product image
            if has_images:
                if p.get("image_path") and os.path.exists(p["image_path"]):
                    img = _prep_image(p["image_path"], COL_W - 0.5*cm, IMG_H)
                    if img:
                        img.hAlign = "CENTER"
                        img_tbl = Table([[img]], colWidths=[COL_W - 0.5*cm])
                        img_tbl.setStyle(TableStyle([
                            ("ALIGN",   (0,0),(-1,-1), "CENTER"),
                            ("TOPPADDING",    (0,0),(-1,-1), 0),
                            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
                        ]))
                        inner.append(img_tbl)
                else:
                    # Placeholder box
                    ph = Table([[Paragraph("", S["pdesc"])]], colWidths=[COL_W - 0.5*cm])
                    ph.setStyle(TableStyle([
                        ("BACKGROUND",    (0,0),(-1,-1), t["rule"]),
                        ("ROWHEIGHTS",    (0,0),(-1,-1), IMG_H),
                        ("TOPPADDING",    (0,0),(-1,-1), 0),
                        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                    ]))
                    inner.append(ph)
                    inner.append(Spacer(1, 6))

            inner.append(Paragraph(p.get("name",""), S["pname"]))
            if p.get("description"):
                inner.append(Paragraph(p["description"], S["pdesc"]))
            # Thin rule before price
            inner.append(HRFlowable(width="100%", thickness=0.5, color=t["rule"], spaceBefore=3, spaceAfter=4))
            inner.append(Paragraph(f"KSh {p.get('price','')}", S["price"]))

            # Build inner cell table
            cell_tbl = Table([[r] for r in inner], colWidths=[COL_W - 0.5*cm])
            cell_tbl.setStyle(TableStyle([
                ("TOPPADDING",    (0,0),(-1,-1), 2),
                ("BOTTOMPADDING", (0,0),(-1,-1), 2),
                ("LEFTPADDING",   (0,0),(-1,-1), 0),
                ("RIGHTPADDING",  (0,0),(-1,-1), 0),
            ]))
            cells.append(cell_tbl)

        while len(cells) < 2:
            cells.append(Paragraph("", S["footer"]))

        row = Table([cells], colWidths=[COL_W, COL_W], hAlign="CENTER",
                    spaceBefore=0, spaceAfter=0)
        row.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(0,0), t["card_bg"]),
            ("BACKGROUND",    (1,0),(1,0), t["card_bg"]),
            ("BOX",           (0,0),(0,0), 0.6, t["card_border"]),
            ("BOX",           (1,0),(1,0), 0.6, t["card_border"]),
            ("TOPPADDING",    (0,0),(-1,-1), 10),
            ("BOTTOMPADDING", (0,0),(-1,-1), 12),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("RIGHTPADDING",  (0,0),(-1,-1), 10),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ("LINEABOVE",     (0,0),(0,0), 2.5, t["accent"]),
            ("LINEABOVE",     (1,0),(1,0), 2.5, t["accent2"]),
        ]))
        story.append(KeepTogether(row))
        story.append(Spacer(1, 0.3*cm))

    # ── QR + FOOTER ─────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.2*cm))
    story.append(HRFlowable(width="100%", thickness=0.75, color=t["rule"], spaceAfter=10))

    if data.get("qr_link"):
        qr_img = _make_qr(data["qr_link"], 2.2*cm)
        qr_lbl = [
            Paragraph("Scan to order on WhatsApp", S["qr_lbl"]),
        ]
        qr_lbl_tbl = Table([[r] for r in qr_lbl], colWidths=[FULL_W - 3.5*cm])
        qr_lbl_tbl.setStyle(TableStyle([
            ("VALIGN",  (0,0),(-1,-1), "MIDDLE"),
            ("LEFTPADDING", (0,0),(-1,-1), 10),
        ]))
        qr_row = Table([[qr_img, qr_lbl_tbl]], colWidths=[3.5*cm, FULL_W-3.5*cm])
        qr_row.setStyle(TableStyle([
            ("VALIGN",  (0,0),(-1,-1), "MIDDLE"),
            ("ALIGN",   (0,0),(0,0), "CENTER"),
            ("TOPPADDING", (0,0),(-1,-1), 0),
            ("BOTTOMPADDING", (0,0),(-1,-1), 0),
        ]))
        story.append(qr_row)
        story.append(Spacer(1, 0.3*cm))

    note = data.get("footer_note") or "Thank you for your business. Please contact us to place an order."
    story.append(Paragraph(note, S["footer"]))
    story.append(Spacer(1, 0.15*cm))
    story.append(Paragraph(
        f"Generated by CatalogPro  ·  {datetime.now().strftime('%d %B %Y')}",
        S["footer"]
    ))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return filename


def generate_preview(data: dict) -> str:
    """Generate a partial preview (1/3 products, watermarked)."""
    preview_data = dict(data)
    products = data.get("products", [])
    # Show only 1/3 of products (min 2)
    count = max(2, len(products) // 3)
    preview_data["products"] = products[:count]
    preview_data["footer_note"] = "⚠ PREVIEW — This shows only part of your catalog. Pay to unlock the full version."
    return generate_catalog(preview_data, watermark=True)
