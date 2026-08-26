"""
ANGEL ONE SMARTAPI INTEGRATION (DRY-RUN SAFE)
===============================================
Ha module Angel One cha SmartAPI connect karto ani orders place karto.

⚠️ SURAKSHA - MAHATVACHE:
- API_KEY, CLIENT_CODE, PASSWORD, TOTP_SECRET he KADHIच code madhe likhu naka.
- He sagle Render cha "Environment Variables" madhe takaycha (Settings -> Environment).
- Ha code os.environ.get() vaparun te values wachto - tumhala kadhich chat madhe
  paste karaychi garaj nahi.

DRY-RUN MODE:
- Environment variable LIVE_TRADING="true" nastana (default), ha module
  KUTHLAHI REAL ORDER PLACE KARत NAHI - fakt Telegram var "yaha order jaali असta"
  asa simulate kartoy.
- Jevha tumhi 100% khatri asal, tevha Render madhe LIVE_TRADING=true takal
  tarach khare orders jatil.

Requirements (requirements.txt madhe add kara):
    smartapi-python
    pyotp
    (exact package name Angel One cha developer portal var confirm kara,
     kadhi kadhi te 'smartapi-python' असते)
"""

import os
import requests
import pyotp
from datetime import datetime, timedelta

LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() == "true"

API_KEY = os.environ.get("ANGEL_API_KEY")
CLIENT_CODE = os.environ.get("ANGEL_CLIENT_CODE")
PASSWORD = os.environ.get("ANGEL_PASSWORD")
TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET")

SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

_smart_api_session = None
_scrip_master_cache = None
_last_error = None


def get_last_error():
    """Shevatcha error kay hota te bagण्यasathi - main.py Telegram var pathavण्yasathi vaparel."""
    return _last_error


def get_smart_api_session():
    """
    Angel One SmartAPI shi login karto. Session cache karto jenekarun
    prattyek order sathi navin login karava lagnar nahi.
    """
    global _smart_api_session, _last_error
    if _smart_api_session is not None:
        return _smart_api_session

    if not all([API_KEY, CLIENT_CODE, PASSWORD, TOTP_SECRET]):
        _last_error = "Credentials Environment Variables madhe sapadle nahit (API_KEY/CLIENT_CODE/PASSWORD/TOTP_SECRET pैki kahi missing ahet)."
        print(f"Angel One error: {_last_error}")
        return None

    try:
        from SmartApi import SmartConnect  # pip install smartapi-python

        obj = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        session_data = obj.generateSession(CLIENT_CODE, PASSWORD, totp)

        if not session_data.get("status"):
            _last_error = str(session_data)
            print(f"Angel One login fail zala: {_last_error}")
            return None

        _smart_api_session = obj
        print("Angel One session yashasvi zaale.")
        return obj
    except Exception as e:
        _last_error = str(e)
        print(f"Angel One session error: {_last_error}")
        return None


def place_order(symbol_key, tradingsymbol, symboltoken, transaction_type, quantity, order_type="MARKET", price=0):
    """
    Order place karto - fakt LIVE_TRADING=true asel tarach prattyaksha order jato.
    Nahitar dry-run madhe fakt simulate kartoy.

    symbol_key: 'NIFTY' / 'BANKNIFTY' (logging sathi)
    tradingsymbol: Angel One cha exact trading symbol (e.g. 'NIFTY28AUG2524600CE')
    symboltoken: Angel One cha token for that option contract
    transaction_type: 'BUY' / 'SELL'
    quantity: lot size
    """
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
        print(f"✅ REAL ORDER placed: {order_id}")
        return {"status": "success", "order_id": order_id}
    except Exception as e:
        print(f"Order place error: {e}")
        return {"status": "error", "message": str(e)}


def get_ltp(exchange, tradingsymbol, symboltoken):
    """Live option premium (LTP - Last Traded Price) fetch karto."""
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
    """
    Angel One cha संपूर्ण instrument list (scrip master) download karun cache karto.
    Yatun aplyala pratyek option strike cha exact tradingsymbol/token milto.
    Ha file mothा ahे (~30-40 MB), tyamule ekdach download karun memory madhe thevto.
    """
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
    """
    Nifty cha weekly expiry saधारण Guruvar (Thursday) asto.
    Ha function pudhचा Thursday cha date 'DDMONYY' format madhe deto (e.g. '28AUG25'),
    jo Angel One cha tradingsymbol madhe vaparla jato.
    ⚠️ Expiry day badalू शकतो (exchange notification нुसार) - actual trading purvi
    NSE/Angel One var confirm kara.
    """
    today = datetime.now()
    days_ahead = (3 - today.weekday()) % 7  # Thursday = weekday 3
    if days_ahead == 0:
        days_ahead = 7
    next_thursday = today + timedelta(days=days_ahead)
    return next_thursday.strftime("%d%b%y").upper()


def find_option_instrument(name, strike, option_type, expiry_str=None):
    """
    Scrip master madhun exact tradingsymbol ani token shodhto.
    name: 'NIFTY' / 'BANKNIFTY'
    strike: e.g. 24600
    option_type: 'CE' / 'PE'
    expiry_str: 'DDMONYY' format, nasel tar automatic pudhचा Thursday vaparto
    """
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


def auto_discover_lot_and_strikes(name, exch_seg="NFO"):
    """
    Scrip master madhun konतahi underlying (NIFTY, RELIANCE, GOLD, इ.) cha
    ACTUAL current lot size ani strike interval shodhun kadhto - manually
    Angel One app madhe check karnyachi garaj nahi.
    exch_seg: "NFO" (stocks/indices) kiva "MCX" (commodities)
    Return: {"lot_size": int, "strike_step": float, "sample_symbol": str} kiva None
    """
    scrip_master = load_scrip_master()
    if scrip_master is None:
        return None

    matches = []
    for instrument in scrip_master:
        if instrument.get("exch_seg") != exch_seg:
            continue
        symbol = instrument.get("symbol", "")
        instrument_name = instrument.get("name", "")
        # name field madhe underlying cha exact naav asto (jasa "NIFTY", "RELIANCE", "GOLD")
        if instrument_name.upper() == name.upper() and (symbol.upper().endswith("CE") or symbol.upper().endswith("PE")):
            matches.append(instrument)

    if not matches:
        return None

    # Sagळ्यात jawalcha expiry nivadto (pahilyach match cha lotsize/expiry vaparto)
    strikes_found = sorted(set(float(m.get("strike", 0)) / 100 for m in matches if m.get("strike")))
    strike_step = None
    if len(strikes_found) >= 2:
        strike_step = round(strikes_found[1] - strikes_found[0], 2)

    sample = matches[0]
    return {
        "lot_size": int(sample.get("lotsize", 0)) if sample.get("lotsize") else None,
        "strike_step": strike_step,
        "sample_symbol": sample.get("symbol"),
    }


def get_option_premium(name, strike, option_type):
    """
    Main.py sathi सोपं interface - strike ani option type dile tar
    live premium (LTP) return karto. Kahi issue asel (session/credentials/
    symbol nahi sapadla) tar None return karto - tyavelela main.py
    estimated premium dakhavel (fallback).
    """
    tradingsymbol, token = find_option_instrument(name, strike, option_type)
    if not tradingsymbol or not token:
        return None
    return get_ltp("NFO", tradingsymbol, token)


def get_mcx_future_token(name):
    """
    MCX var (Gold, Silver, CrudeOil) cha sagळ्यात jawalcha (near-month)
    Futures contract cha token shodhto - yavarunच historical candle data
    ani live price milel.
    name: 'GOLD', 'SILVER', 'CRUDEOIL'
    """
    scrip_master = load_scrip_master()
    if scrip_master is None:
        return None, None

    matches = []
    for instrument in scrip_master:
        if instrument.get("exch_seg") != "MCX":
            continue
        if instrument.get("name", "").upper() != name.upper():
            continue
        if instrument.get("instrumenttype", "").upper() != "FUTCOM":
            continue
        matches.append(instrument)

    if not matches:
        print(f"MCX future sapadla nahi: {name}")
        return None, None

    # Sagळ्यात jawalcha (nearest) expiry nivadto
    def parse_expiry(inst):
        try:
            return datetime.strptime(inst.get("expiry", ""), "%d%b%Y")
        except Exception:
            return datetime.max

    matches.sort(key=parse_expiry)
    nearest = matches[0]
    return nearest.get("symbol"), nearest.get("token")


def get_mcx_historical_df(name, interval="FIVE_MINUTE", days=5):
    """
    Angel One cha Historical Data API vaparun MCX commodity (Gold/Silver/CrudeOil)
    cha OHLC candle data anto - pandas DataFrame स्वरूपात, jo yfinance sarkha
    Open/High/Low/Close columns ठेवतो, jenekarun sध्याचा indicator calculation
    code (SuperTrend/RSI/EMA) tasach vaparता येईल.

    ⚠️ Ha function untested ahe (sandbox madhe internet nahi) - actual
    deploy karताना error aali tar exact error message baghून fix karava lagel.
    """
    import pandas as pd
    from datetime import timedelta

    obj = get_smart_api_session()
    if obj is None:
        return None

    symbol, token = get_mcx_future_token(name)
    if not symbol or not token:
        return None

    try:
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)
        params = {
            "exchange": "MCX",
            "symboltoken": token,
            "interval": interval,
            "fromdate": from_date.strftime("%Y-%m-%d %H:%M"),
            "todate": to_date.strftime("%Y-%m-%d %H:%M"),
        }
        response = obj.getCandleData(params)
        if not response.get("status") or not response.get("data"):
            print(f"MCX historical data milala nahi: {response}")
            return None

        candles = response["data"]
        df = pd.DataFrame(candles, columns=["Datetime", "Open", "High", "Low", "Close", "Volume"])
        df["Datetime"] = pd.to_datetime(df["Datetime"])
        df.set_index("Datetime", inplace=True)
        return df
    except Exception as e:
        print(f"MCX historical data error: {e}")
        return None


def get_mcx_ltp(name):
    """MCX commodity cha live price (LTP) fetch karto."""
    symbol, token = get_mcx_future_token(name)
    if not symbol or not token:
        return None
    return get_ltp("MCX", symbol, token)


if __name__ == "__main__":
    print(f"LIVE_TRADING mode: {LIVE_TRADING}")
    if LIVE_TRADING:
        print("⚠️ LIVE mode ON ahe - khare orders jatil!")
    else:
        print("✅ DRY-RUN mode - koणताही khara order jaणar nahi.")
    session = get_smart_api_session()
    print("Session status:", "Connected" if session else "Not connected")
