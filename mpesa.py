import requests, base64
from datetime import datetime
from config import Config

def _token():
    url = ("https://sandbox.safaricom.co.ke" if Config.MPESA_ENV=="sandbox"
           else "https://api.safaricom.co.ke") + "/oauth/v1/generate?grant_type=client_credentials"
    r = requests.get(url, auth=(Config.MPESA_CONSUMER_KEY, Config.MPESA_CONSUMER_SECRET), timeout=10)
    return r.json().get("access_token")

def _pwd_ts():
    ts  = datetime.now().strftime("%Y%m%d%H%M%S")
    raw = Config.MPESA_SHORTCODE + Config.MPESA_PASSKEY + ts
    return base64.b64encode(raw.encode()).decode(), ts

def stk_push(phone, amount, order_id, desc="CatalogPro"):
    phone = phone.strip().replace(" ","").replace("-","")
    if phone.startswith("0"):   phone = "254" + phone[1:]
    elif phone.startswith("+"): phone = phone[1:]
    token = _token()
    pwd, ts = _pwd_ts()
    base = "https://sandbox.safaricom.co.ke" if Config.MPESA_ENV=="sandbox" else "https://api.safaricom.co.ke"
    r = requests.post(base + "/mpesa/stkpush/v1/processrequest", timeout=15,
        headers={"Authorization": f"Bearer {token}"},
        json={"BusinessShortCode": Config.MPESA_SHORTCODE, "Password": pwd,
              "Timestamp": ts, "TransactionType": "CustomerPayBillOnline",
              "Amount": amount, "PartyA": phone, "PartyB": Config.MPESA_SHORTCODE,
              "PhoneNumber": phone, "CallBackURL": Config.MPESA_CALLBACK_URL,
              "AccountReference": order_id, "TransactionDesc": desc})
    return r.json()

def parse_callback(data):
    try:
        body = data["Body"]["stkCallback"]
        if body["ResultCode"] != 0: return None
        items = {i["Name"]: i.get("Value") for i in body["CallbackMetadata"]["Item"]}
        return {"mpesa_code": items.get("MpesaReceiptNumber"),
                "amount": items.get("Amount"),
                "order_id": body.get("AccountReference")}
    except: return None
