import pyotp
import requests
import json

_smart_api_session = None
db = None  

def get_smart_api_session():
    global _smart_api_session, db
    if _smart_api_session is not None:
        return _smart_api_session
    try:
        if db is None: return None
        user_data = db.collection('users').document('user_01').get().to_dict()
        if not user_data: return None
        
        api_key = user_data.get("broker_api_key")
        client_code = user_data.get("broker_client_id")
        login_password = user_data.get("broker_mpin") 
        totp_secret = user_data.get("broker_totp_secret")

        # डायरेक्ट एंजेल वन API वर लॉगिन रिक्वेस्ट पाठवणे (नो लायब्ररी)
        url = "https://angelone.in"
        totp_token = pyotp.TOTP(totp_secret).now()
        
        headers = {"Content-Type": "application/json", "X-PrivateKey": api_key}
        payload = {"clientcode": client_code, "password": login_password, "totp": totp_token}
        
        res = requests.post(url, headers=headers, json=payload).json()
        if res.get("status"):
            _smart_api_session = {"jwt": res["data"]["jwtToken"], "key": api_key, "client": client_code}
            return _smart_api_session
        return None
    except Exception:
        return None

def place_fast_trailing_order(tradingsymbol, transactiontype, quantity, entry_price, market_sl_price, target_pts, trailing_pts=10):
    """थेट एंजेल वन सर्व्हरवर रोबो/ब्रॅकेट ऑर्डर प्लेस करणे"""
    global _smart_api_session
    session = get_smart_api_session()
    if not session: return {"status": False, "message": "ब्रोकर लॉगिन नाही."}
    
    try:
        calculated_sl_pts = abs(float(entry_price) - float(market_sl_price))
        if calculated_sl_pts <= 0: calculated_sl_pts = 15.0
            
        url = "https://angelone.in"
        headers = {
            "Authorization": f"Bearer {session['jwt']}",
            "X-PrivateKey": session['key'],
            "X-ClientCode": session['client'],
            "Content-Type": "application/json"
        }
        
        # डायरेक्ट ऑर्डर गियर पॅरामीटर्स
        order_params = {
            "variety": "ROBO",
            "tradingsymbol": tradingsymbol.upper(),
            "symboltoken": "9992600",
            "transactiontype": transactiontype.upper(),
            "exchange": "NFO",
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": "0",
            "quantity": str(quantity),
            "squareoff": str(target_pts),
            "stoploss": str(round(calculated_sl_pts, 2)),
            "trailingstoploss": str(trailing_pts)
        }
        
        res = requests.post(url, headers=headers, json=order_params).json()
        if res.get("status"):
            return {"status": True, "order_id": res["data"]["orderid"], "calculated_sl": calculated_sl_pts}
        return {"status": False, "message": res.get("message")}
    except Exception as e:
        return {"status": False, "message": str(e)}
