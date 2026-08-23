import pyotp
import json

# ग्लोबल व्हेरिएबल्स
_smart_api_session = None
_last_error = None
NSE_LIVE_LTP = 0.0

def get_smart_api_session(api_key=None, client_code=None, login_password=None, totp_secret=None):
    """
    ॲप इंटरफेसवरून थेट क्रेडेंशियल्स घेऊन एंजेल वनला ऑटो-लॉगिन करतो.
    """
    global _smart_api_session, _last_error
    if _smart_api_session is not None:
        return _smart_api_session

    if not all([api_key, client_code, login_password, totp_secret]):
        return None

    try:
        from SmartApi import SmartConnect
        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        
        session_data = obj.generateSession(client_code, login_password, totp)

        if not session_data.get("status"):
            _last_error = str(session_data)
            print(f"Angel One login fail: {_last_error}")
            return None

        _smart_api_session = obj
        print("✅ Angel One Session यशस्वी झाले.")
        return obj
    except Exception as e:
        _last_error = str(e)
        print(f"Angel One session error: {_last_error}")
        return None

def place_order(tradingsymbol, exchange, transactiontype, quantity, price, ordertype="MARKET", producttype="INTRADAY"):
    """
    एंजेल वन वर ऑर्डर प्लेस करणे.
    """
    global _smart_api_session
    if _smart_api_session is None:
        return {"status": False, "message": "ब्रोकर लॉगिन केलेले नाही. कृपया आधी डॅशबोर्डवर लॉगिन करा."}
    
    try:
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": tradingsymbol,
            "symboltoken": "9992600", 
            "transactiontype": transactiontype, 
            "exchange": exchange, 
            "ordertype": ordertype,
            "producttype": producttype,
            "duration": "DAY",
            "price": str(price),
            "quantity": str(quantity)
        }
        
        order_id = _smart_api_session.placeOrder(order_params)
        return {"status": True, "order_id": order_id}
    except Exception as e:
        return {"status": False, "message": str(e)}

def get_option_premium(symbol, strike_price, option_type):
    return 0.0

def init_nse_stream():
    return True
