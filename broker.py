import pyotp
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

        from SmartApi import SmartConnect
        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        session_data = obj.generateSession(client_code, login_password, totp)

        if session_data.get("status"):
            _smart_api_session = obj
            return obj
        return None
    except Exception:
        return None

def place_fast_trailing_order(tradingsymbol, transactiontype, quantity, entry_price, market_sl_price, target_pts, trailing_pts=10):
    """
    🔥 प्रमोद भाऊ विशेष: किंमत ११० वर जाताच पहिला फास्ट जंप मारून एसएल खरेदी भावावर (१००) आणणारी सिस्टीम!
    """
    global _smart_api_session
    obj = get_smart_api_session()
    if obj is None: return {"status": False, "message": "ब्रोकर लॉगिन नाही."}
    
    try:
        symbol_upper = tradingsymbol.upper()
        exchange = "NFO"
        symbol_token = "9992600" 
        variety_type = "ROBO"
        
        # मार्केटनुसार मूळ एसएल पॉईंट्स मोजणे
        calculated_sl_pts = abs(float(entry_price) - float(market_sl_price))
        if calculated_sl_pts <= 0:
            calculated_sl_pts = 15.0

        if symbol_upper.isalpha() and symbol_upper not in ["NIFTY", "BANKNIFTY", "FINNIFTY"]:
            exchange = "NSE"
            variety_type = "NORMAL"
            tokens = {"SBIN": "3045", "RELIANCE": "2885", "TATASTEEL": "3499", "INFY": "1596"}
            symbol_token = tokens.get(symbol_upper, "3045")
            
        order_params = {
            "variety": variety_type,
            "tradingsymbol": symbol_upper,
            "symboltoken": symbol_token,
            "transactiontype": transactiontype, 
            "exchange": exchange,
            "ordertype": "LIMIT" if entry_price > 0 else "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": str(entry_price),
            "quantity": str(quantity)
        }
        
        if variety_type == "ROBO":
            order_params["squareoff"] = str(target_pts)
            order_params["stoploss"] = str(round(calculated_sl_pts, 2))
            
            # 🎯 फास्ट ट्रेलिंग जंप लॉक करणे:
            # यामुळे जशी किंमत १० पॉईंट्स वाढेल (११० होईल), तसा एसएल तितक्याच पॉईंट्सने थेट वर सरकून १०० (खरेदी भावावर) लॉक होईल!
            order_params["trailingstoploss"] = str(trailing_pts)      
            
        order_id = obj.placeOrder(order_params)
        return {"status": True, "order_id": order_id, "calculated_sl": calculated_sl_pts}
    except Exception as e:
        return {"status": False, "message": str(e)}
