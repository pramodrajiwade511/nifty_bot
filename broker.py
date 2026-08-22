"""
ANGEL ONE SMARTAPI INTEGRATION (MPIN, TOTP & NSE LIVE DATA SECURE)
==================================================================
Ha module Angel One cha SmartAPI connect karto, orders place karto, 
ani NSE cha live market data WebSocket dware 24/7 catch karto.

⚠️ SURAKSHA - MAHATVACHE:
- Render cha "Environment Variables" madhe ANGEL_MPIN, ANGEL_CLIENT_CODE, 
  ANGEL_API_KEY, ani ANGEL_TOTP_SECRET nki save kara.
"""

import os
import requests
import pyotp
import threading
import time
from datetime import datetime, timedelta

LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() == "true"

API_KEY = os.environ.get("ANGEL_API_KEY")
CLIENT_CODE = os.environ.get("ANGEL_CLIENT_CODE")
PASSWORD = os.environ.get("ANGEL_PASSWORD") 
MPIN = os.environ.get("ANGEL_MPIN") # 4-Anki login PIN
TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET")

SCRIP_MASTER_URL = "https://angelbroking.com"

_smart_api_session = None
_scrip_master_cache = None
_last_error = None

# Global Variable - Yat NSE Nifty cha khara live bhav satat update hot rahil
NSE_LIVE_LTP = 0.0

def get_last_error():
    return _last_error

def get_smart_api_session():
    """
    Angel One SmartAPI shi login karto. 4-Anki MPIN ani TOTP automatic vaparto.
    """
    global _smart_api_session, _last_error
    if _smart_api_session is not None:
        return _smart_api_session

    login_password = MPIN if MPIN else PASSWORD

    if not all([API_KEY, CLIENT_CODE, login_password, TOTP_SECRET]):
        _last_error = "Credentials sapadle nahit! Please Render var Variables check kara (ANGEL_MPIN/ANGEL_CLIENT_CODE missing ahe)."
        print(f"Angel One error: {_last_error}")
        return None

    try:
        from SmartApi import SmartConnect
        obj = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        
        session_data = obj.generateSession(CLIENT_CODE, login_password, totp)

        if not session_data.get("status"):
            _last_error = str(session_data)
            print(f"Angel One login fail: {_last_error}")
            return None

        _smart_api_session = obj
        print("✅ Angel One MPIN session yashasvi zaale.")
        return obj
    except Exception as e:
        _last_error = str(e)
        print(f"Angel One session error: {_last_error}")
        return None

# ==================================================================
# 🌐 NEW FEATURE: 24/7 NSE WebSocket Live Data Stream
# ==================================================================
def start_nse_live_feed():
    """
    Back-end la background thread var satat chalto ani NSE cha live rate catch karto.
    """
    global NSE_LIVE_LTP
    while True:
        try:
            session_obj = get_smart_api_session()
            if session_obj is not None:
                from SmartApi.smartWebSocketV2 import SmartWebSocketV2
                
                feed_token = session_obj.getfeedToken()
                jwt_token = session_obj.jwtToken if hasattr(session_obj, 'jwtToken') else ""
                
                if not jwt_token:
                    jwt_token = session_obj.userId 
                
                sws = SmartWebSocketV2(jwt_token, CLIENT_CODE, feed_token, API_KEY)

                def on_data(wsapp, message):
                    global NSE_LIVE_LTP
                    if "last_traded_price" in message:
                        NSE_LIVE_LTP = float(message["last_traded_price"]) / 100

                def on_open(wsapp):
                    print("🌐 NSE WebSocket Live Feed Active! (NIFTY Token: 26000)")
                    token_list = [{"exchangeType": 1, "tokens": ["26000"]}] 
                    sws.subscribe("nse_stream_bot", 1, 3, token_list)

                sws.on_data = on_data
                sws.on_open = on_open
                sws.connect()
        except Exception as e:
            print(f"⚠️ WebSocket disconnect zala, 5 sec madhe auto-connect hot ahe: {e}")
            time.sleep(5)

def init_nse_stream():
    t = threading.Thread(target=start_nse_live_feed, daemon=True)
    t.start()

# ==================================================================
# 📦 ORIGINAL CORE FEATURES (RETAINED)
# ==================================================================
def place_order(symbol_key, tradingsymbol, symboltoken, transaction_type, quantity, order_type="MARKET", price=0):
    if not LIVE_TRADING:
        msg = (
            f"🧪 [DRY-RUN] Order SIMULATE zala (khara order gela NAHI)\n"
            f"{symbol_key} | {tradingsymbol} | {transaction_type} | Qty: {quantity}"
        )
        print(msg)
        return {"status": "dry_run", "message": msg}

    obj = get_smart_api_session()
    if obj is None:
        return {"status": "error", "message": "Angel One session tayar nahi."}

    try:
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": tradingsymbol,
            "symboltoken": symboltoken,
            "transactiontype": transaction_type,
            "exchange": "NFO",
            "ordertype": order_type,
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": price,
            "quantity": quantity,
        }
        order_id = obj.placeOrder(order_params)
        print(f"✅ REAL ORDER placed in Angel One: {order_id}")
        return {"status": "success", "order_id": order_id}
    except Exception as e:
        print(f"Order place error: {e}")
        return {"status": "error", "message": str(e)}

def get_ltp(exchange, tradingsymbol, symboltoken):
    global NSE_LIVE_LTP
    if exchange == "NSE" and symboltoken == "26000" and NSE_LIVE_LTP > 0:
        return NSE_LIVE_LTP

    obj = get_smart_api_session()
    if obj is None:
        return None
    try:
        data = obj.ltpData(exchange, tradingsymbol, symboltoken)
        if data.get("status"):
            return data["data"]["ltp"]
    except Exception as e:
        print(f"LTP fetch error: {e}")
    return None

def load_scrip_master():
    global _scrip_master_cache
    if _scrip_master_cache is not None:
        return _scrip_master_cache
    try:
        resp = requests.get(SCRIP_MASTER_URL, timeout=30)
        _scrip_master_cache = resp.json()
        print(f"Scrip master loaded: {len(_scrip_master_cache)} instruments")
        return _scrip_master_cache
    except Exception as e:
        print(f"Scrip master download error: {e}")
        return None

def get_next_weekly_expiry():
    today = datetime.now()
    days_ahead = (3 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    next_thursday = today + timedelta(days=days_ahead)
    return next_thursday.strftime("%d%b%y").upper()

def find_option_instrument(name, strike, option_type, expiry_str=None):
    scrip_master = load_scrip_master()
    if scrip_master is None:
        return None, None

    if expiry_str is None:
        expiry_str = get_next_weekly_expiry()

    expected_symbol_part = f"{name}{expiry_str}{int(strike)}{option_type}"

    for instrument in scrip_master:
        if instrument.get("exch_seg") == "NFO" and instrument.get("symbol", "").upper() == expected_symbol_part.upper():
            return instrument.get("symbol"), instrument.get("token")

    print(f"Instrument sapadla nahi: {expected_symbol_part}")
    return None, None

def get_option_premium(name, strike, option_type):
    tradingsymbol, token = find_option_instrument(name, strike, option_type)
    if not tradingsymbol or not token:
        return None
    return get_ltp("NFO", tradingsymbol, token)

if __name__ == "__main__":
    print(f"LIVE_TRADING mode: {LIVE_TRADING}")
    init_nse_stream()
    session = get_smart_api_session()
    print("Session status:", "Connected" if session else "Not connected")
