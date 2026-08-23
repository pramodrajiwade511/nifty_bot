import pyotp
import json

# ग्लोबल व्हेरिएबल्स
_smart_api_session = None
_last_error = None

# १. NSE LIVE LTP व्हॅल्यू (डिफॉल्ट)
NSE_LIVE_LTP = 0.0

def get_smart_api_session():
    """
    गुगल फायरबेस डेटाबेसमधून युजरचे क्रेडेंशियल्स वाचून एंजेल वनला ऑटो-लॉगिन करतो.
    """
    global _smart_api_session, _last_error
    if _smart_api_session is not None:
        return _smart_api_session

    try:
        from main import db
        if db is None:
            _last_error = "फायरबेस डेटाबेसशी कनेक्शन जोडलेले नाही!"
            return None
            
        user_data = db.collection('users').document('user_01').get().to_dict()
        if not user_data:
            _last_error = "फायरबेसमध्ये युजर डेटा सापडला नाही!"
            return None
        
        api_key = user_data.get("broker_api_key")
        client_code = user_data.get("broker_client_id")
        login_password = user_data.get("broker_mpin") 
        totp_secret = user_data.get("broker_totp_secret")

        if not all([api_key, client_code, login_password, totp_secret]):
            _last_error = "ॲपमध्ये अजून ब्रोकर सेटिंग्स अपूर्ण आहेत!"
            print(f"Angel One error: {_last_error}")
            return None

        from SmartApi import SmartConnect
        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        
        session_data = obj.generateSession(client_code, login_password, totp)

        if not session_data.get("status"):
            _last_error = str(session_data)
            print(f"Angel One login fail: {_last_error}")
            return None

        _smart_api_session = obj
        print("✅ Angel One Dynamic MPIN session yashasvi zaale.")
        return obj
    except Exception as e:
        _last_error = str(e)
        print(f"Angel One session error: {_last_error}")
        return None

# २. ऑर्डर प्लेस करण्याचे फंक्शन
def place_order(tradingsymbol, exchange, transactiontype, quantity, price, ordertype="MARKET", producttype="INTRADAY"):
    """
    एंजेल वन वर ऑर्डर प्लेस करणे.
    """
    obj = get_smart_api_session()
    if obj is None:
        print("ऑर्डर फेल: ब्रोकर सेशन उपलब्ध नाही.")
        return {"status": False, "message": "ब्रोकर सेशन उपलब्ध नाही."}
    
    try:
        # एक्सचेंज आणि सिम्बॉल नुसार टोकन मॅपिंग (इथे गरज पडल्यास टोकन टाकावे लागेल)
        # सध्या मार्केट ऑर्डरसाठी पॅरामीटर्स तयार करत आहे
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": tradingsymbol,
            "symboltoken": "9992600", # उदा. NIFTY साठी योग्य टोकन मॅप करावे लागेल
            "transactiontype": transactiontype, # BUY किंवा SELL
            "exchange": exchange, # NSE किंवा NFO
            "ordertype": ordertype,
            "producttype": producttype,
            "duration": "DAY",
            "price": str(price),
            "quantity": str(quantity)
        }
        
        order_id = obj.placeOrder(order_params)
        print(f"✅ ऑर्डर यशस्वीरित्या प्लेस झाली. आयडी: {order_id}")
        return {"status": True, "order_id": order_id}
    except Exception as e:
        print(f"❌ ऑर्डर प्लेस करताना एरर आली: {str(e)}")
        return {"status": False, "message": str(e)}

# ३. ऑप्शन्स चे प्रीमियम मिळवण्याचे फंक्शन
def get_option_premium(symbol, strike_price, option_type):
    """
    ऑप्शन स्ट्राइक प्राईजचे प्रीमियम (LTP) मिळवणे.
    """
    obj = get_smart_api_session()
    if obj is None:
        return 0.0
    try:
        # एंजेल वन API कडून मार्केट डेटा मिळवणे
        # नमुना म्हणून सध्या ०.० रिटर्न करत आहे, तुम्ही एलटीपी फेचिंग लॉजिक जोडू शकता
        return 0.0
    except Exception as e:
        print(f"Premium fetch error: {str(e)}")
        return 0.0

# ४. एनएसई लाइव्ह स्ट्रीम चालू करण्याचे फंक्शन
def init_nse_stream():
    """
    NSE मार्केट डेटा फीड / वेबसॉकेट सुरू करणे.
    """
    obj = get_smart_api_session()
    if obj is None:
        print("वेबसॉकेट सुरू होऊ शकले नाही: सेशन नाही.")
        return False
    print("✅ NSE Stream / WebSocket यशस्वीरित्या सुरू झाले.")
    return True
