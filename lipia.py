"""
Lipia M-Pesa payment helper
Docs: https://lipia-api.kreativelabske.com/api
"""
import requests
from config import Config

LIPIA_BASE = "https://lipia-api.kreativelabske.com/api"


def _headers():
    return {
        "Authorization": f"Bearer {Config.LIPIA_API_KEY}",
        "Content-Type": "application/json",
    }


def normalise_phone(phone: str) -> str:
    """Convert any Kenyan format to 07XXXXXXXX expected by Lipia."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+254"):
        phone = "0" + phone[4:]
    elif phone.startswith("254"):
        phone = "0" + phone[3:]
    return phone


def stk_push(phone: str, amount, order_id: str, desc: str = "CatalogPro"):
    """
    Initiate an STK Push via Lipia.

    Returns a dict with one of:
      {"ok": True,  "reference": "RD37AV1CXF", "checkout_id": "ws_CO_..."}
      {"ok": False, "msg": "<error description>"}

    NOTE: Lipia is *synchronous* — this call blocks until the user
    approves or rejects the prompt (up to ~60 s). Always run in a thread.

    Known Lipia quirks handled here:
      - Response is sometimes a bare string e.g. "Authorized" instead of JSON.
      - The M-Pesa receipt field is misspelled "refference" (double-f).
      - timeout must be >= 60 s to allow the user time to enter their PIN.
    """
    phone = normalise_phone(phone)
    payload = {
        "phone": phone,
        "amount": str(amount),
    }

    try:
        r = requests.post(
            f"{LIPIA_BASE}/request/stk",
            json=payload,
            headers=_headers(),
            timeout=65,  # give user 60 s to enter PIN + 5 s network
        )
        raw = r.text.strip()
        print(f"LIPIA RAW RESPONSE for {order_id}: {raw}")

    except requests.exceptions.Timeout:
        return {"ok": False, "msg": "Payment request timed out. Please try again."}
    except Exception as e:
        return {"ok": False, "msg": f"Network error: {e}"}

    # ── Handle bare-string responses ────────────────────────────────────────
    # Lipia occasionally returns a plain string instead of JSON.
    # "Authorized" (with or without surrounding quotes) means the user
    # entered their PIN and the payment was accepted.
    stripped = raw.strip('"').strip("'")
    if stripped.lower() == "authorized":
        return {
            "ok": True,
            "reference": "LIPIA",
            "checkout_id": "",
        }

    # ── Parse JSON ──────────────────────────────────────────────────────────
    try:
        data = r.json()
    except ValueError:
        return {"ok": False, "msg": stripped or f"Payment server error: {raw[:120]}"}

    # Lipia sometimes returns a JSON-encoded string (valid JSON but not a dict)
    # e.g. "App suspended due to policy violations" — r.json() succeeds but
    # returns a str, so .get() would crash. Catch it here.
    if not isinstance(data, dict):
        return {"ok": False, "msg": str(data).strip('"').strip("'") or "Unexpected response from payment server."}

    # ── Success ─────────────────────────────────────────────────────────────
    # Lipia success format: {"message": "callback received successfully", "data": {...}}
    # NOTE: Lipia has a typo — the receipt field is "refference" (double-f).
    if data.get("message") == "callback received successfully" and data.get("data"):
        d = data["data"]
        reference = (
            d.get("refference")   # Lipia's actual (misspelled) field
            or d.get("reference") # just in case they fix it one day
            or "LIPIA"
        )
        return {
            "ok": True,
            "reference": reference,
            "checkout_id": d.get("CheckoutRequestID", ""),
            "amount": d.get("amount"),
            "phone": d.get("phone"),
        }

    # ── Error ────────────────────────────────────────────────────────────────
    # Lipia returns {"message": "<reason>"} for all error cases.
    msg = data.get("message", "Payment failed. Please try again.") if isinstance(data, dict) else str(data)
    friendly = {
        "invalid phone number":      "Invalid phone number. Use format 07XXXXXXXX.",
        "Request cancelled by user": "You cancelled the M-Pesa request.",
        "insuccifient user balance": "Insufficient M-Pesa balance.",
        "insufficient user balance": "Insufficient M-Pesa balance.",
        "user took too long to pay": "Request expired — you took too long. Try again.",
    }
    return {"ok": False, "msg": friendly.get(msg, msg)}


