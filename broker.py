"""
broker.py - Angel One SmartAPI integration for nifty_bot (app.py)

MPIN vaparun login hoto. Env vars (Render Environment मध्ये set kara):
    ANGEL_API_KEY
    ANGEL_CLIENT_CODE
    ANGEL_MPIN
    ANGEL_TOTP_SECRET

⚠️ MPIN kadhihi code madhe hardcode karू naye kiva GitHub var commit karू naye -
   fakt Render Environment var, environment variable mhanunach store kara.

Requires:
    pip install smartapi-python pyotp pandas requests --break-system-packages
"""

import os
import logging
from datetime import datetime, timedelta

import requests
import pyotp
import pandas as pd
from SmartApi import SmartConnect

logging.basicConfig(level=logging.INFO, format="%(asctime)s [broker] %(message)s")
log = logging.getLogger("broker")

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
API_KEY = os.environ.get("ANGEL_API_KEY")
CLIENT_CODE = os.environ.get("ANGEL_CLIENT_CODE")
MPIN = os.environ.get("ANGEL_MPIN")
TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET")

SCRIP_MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"

# app.py cha symbol_key -> Angel scrip master cha "name" field.
SCRIP_NAME_MAP = {
    "NIFTY": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": "SENSEX",
    "GOLD": "GOLD",
    "SILVER": "SILVER",
    "CRUDEOIL": "CRUDEOIL",
}

_smart_api_session = None
_last_error = None
_scrip_master_cache = None
_scrip_master_cache_time = None


# ----------------------------------------------------------------------------
# Login (MPIN based)
# ----------------------------------------------------------------------------
def get_smart_api_session():
    """
    Angel One shी MPIN + TOTP vaparun login karto. Ekda session झाला ki
    to cache madhe thevla jato. Yashस्वी zalyas SmartConnect object return
    karto, fail zalyas None.
    """
    global _smart_api_session, _last_error

    if _smart_api_session is not None:
        return _smart_api_session

    if not all([API_KEY, CLIENT_CODE, MPIN, TOTP_SECRET]):
        _last_error = (
            "ANGEL_API_KEY / ANGEL_CLIENT_CODE / ANGEL_MPIN / ANGEL_TOTP_SECRET "
            "env variables पैki eक kiva jasta set nahiyet (Render Environment check kara)."
        )
        log.error(_last_error)
        return None

    try:
        smart_api = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        session_data = smart_api.generateSession(CLIENT_CODE, MPIN, totp)

        if not session_data.get("status"):
            _last_error = session_data.get("message", "Unknown login failure")
            log.error(f"Login failed: {_last_error}")
            return None

        _smart_api_session = smart_api
        _last_error = None
        log.info("Angel One login successful (MPIN वापरून).")
        return smart_api

    except Exception as e:
        _last_error = str(e)
        log.exception("Login exception")
        return None


def get_last_error():
    return _last_error


def reset_session():
    """Session invalid zali (token expire) tar he call करून parat login karता येईl."""
    global _smart_api_session
    _smart_api_session = None


# ----------------------------------------------------------------------------
# Scrip master (instrument list) - cached, dर 12 tasानी refresh
# ----------------------------------------------------------------------------
def _load_scrip_master():
    global _scrip_master_cache, _scrip_master_cache_time

    if (
        _scrip_master_cache is not None
        and _scrip_master_cache_time is not None
        and (datetime.now() - _scrip_master_cache_time) < timedelta(hours=12)
    ):
        return _scrip_master_cache

    try:
        resp = requests.get(SCRIP_MASTER_URL, timeout=30)
        resp.raise_for_status()
        _scrip_master_cache = resp.json()
        _scrip_master_cache_time = datetime.now()
        log.info(f"Scrip master loaded: {len(_scrip_master_cache)} instruments")
        return _scrip_master_cache
    except Exception as e:
        log.exception("Scrip master download failed")
        return None


def get_option_contract(symbol_key, strike, option_type):
    """Scrip master madhun option cha token+tradingsymbol (nearest expiry) kadhto."""
    scrip_master = _load_scrip_master()
    if scrip_master is None:
        return None
    name = SCRIP_NAME_MAP.get(symbol_key, symbol_key)
    strike_paise = str(int(round(strike * 100)))
    candidates = [
        row for row in scrip_master
        if row.get("name") == name
        and row.get("instrumenttype") in ("OPTIDX", "OPTSTK")
        and row.get("strike") == strike_paise
        and str(row.get("symbol", "")).endswith(option_type)
    ]
    if not candidates:
        return None
    try:
        candidates.sort(key=lambda r: datetime.strptime(r.get("expiry", ""), "%d%b%Y"))
    except Exception:
        pass
    return candidates[0]


# ----------------------------------------------------------------------------
# Option premium (live LTP)
# ----------------------------------------------------------------------------
def get_option_premium(symbol_key, strike, option_type):
    """
    symbol_key (e.g. 'NIFTY'), ATM strike, option_type ('CE'/'PE') वरून
    sagळ्यात jawळच्या expiry cha live LTP देतो. Adchan aali tar None.
    """
    smart_api = get_smart_api_session()
    if smart_api is None:
        return None

    contract = get_option_contract(symbol_key, strike, option_type)
    if contract is None:
        log.warning(f"No option contract found for {symbol_key} {strike} {option_type}")
        return None

    try:
        ltp_resp = smart_api.ltpData(
            contract.get("exch_seg", "NFO"),
            contract["symbol"],
            contract["token"],
        )
        if ltp_resp.get("status") and ltp_resp.get("data"):
            return float(ltp_resp["data"]["ltp"])
        log.warning(f"LTP fetch returned no data: {ltp_resp}")
        return None
    except Exception as e:
        log.exception("LTP fetch failed")
        return None


# ----------------------------------------------------------------------------
# Order placement (LIVE_TRADING gate app.py madhe aहे)
# ----------------------------------------------------------------------------
def place_order(symbol_key, strike, option_type, transaction_type, quantity):
    """
    Real order Angel One var place karto (INTRADAY, MARKET order).
    transaction_type: "BUY" kiva "SELL"
    Yashaswi zalyas order response return karto, fail zalyas None.
    """
    smart_api = get_smart_api_session()
    if smart_api is None:
        log.error("Order place failed: no session")
        return None

    contract = get_option_contract(symbol_key, strike, option_type)
    if contract is None:
        log.error(f"Order place failed: contract not found for {symbol_key} {strike} {option_type}")
        return None

    order_params = {
        "variety": "NORMAL",
        "tradingsymbol": contract["symbol"],
        "symboltoken": contract["token"],
        "transactiontype": transaction_type,
        "exchange": contract.get("exch_seg", "NFO"),
        "ordertype": "MARKET",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "quantity": str(quantity),
    }
    try:
        resp = smart_api.placeOrder(order_params)
        log.info(f"Order response ({transaction_type} {contract['symbol']} x{quantity}): {resp}")
        return resp
    except Exception as e:
        log.exception(f"Order placement failed ({transaction_type} {contract['symbol']})")
        return None


# ----------------------------------------------------------------------------
# MCX historical candles
# ----------------------------------------------------------------------------
def get_mcx_historical_df(symbol_key):
    """
    MCX commodity (GOLD/SILVER/CRUDEOIL) chi sagळ्यात jawळच्या expiry chya
    futures contract chi 5-din chi 5-minute candle data pandas DataFrame
    mhanun return karto (columns: Open, High, Low, Close, Volume).
    """
    smart_api = get_smart_api_session()
    if smart_api is None:
        return pd.DataFrame()

    scrip_master = _load_scrip_master()
    if scrip_master is None:
        return pd.DataFrame()

    name = SCRIP_NAME_MAP.get(symbol_key, symbol_key)
    candidates = [
        row for row in scrip_master
        if row.get("name") == name
        and row.get("exch_seg") == "MCX"
        and row.get("instrumenttype") == "FUTCOM"
    ]
    if not candidates:
        log.warning(f"No MCX futures contract found for {name}")
        return pd.DataFrame()

    try:
        candidates.sort(key=lambda r: datetime.strptime(r.get("expiry", ""), "%d%b%Y"))
    except Exception:
        pass
    contract = candidates[0]

    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=5)
    params = {
        "exchange": "MCX",
        "symboltoken": contract["token"],
        "interval": "FIVE_MINUTE",
        "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
        "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
    }

    try:
        resp = smart_api.getCandleData(params)
        if not resp.get("status") or not resp.get("data"):
            log.warning(f"MCX candle fetch failed: {resp}")
            return pd.DataFrame()

        df = pd.DataFrame(resp["data"], columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        log.exception("MCX candle fetch exception")
        return pd.DataFrame()


# ----------------------------------------------------------------------------
# Auto-discover lot size & strike step
# ----------------------------------------------------------------------------
def auto_discover_lot_and_strikes(symbol_key):
    """
    Scrip master vaparun symbol_key cha actual current lot_size ani
    strike_step shodhून {"lot_size": int, "strike_step": number} return karto.
    """
    scrip_master = _load_scrip_master()
    if scrip_master is None:
        return None

    name = SCRIP_NAME_MAP.get(symbol_key, symbol_key)

    fut_candidates = [
        row for row in scrip_master
        if row.get("name") == name
        and row.get("instrumenttype") in ("FUTIDX", "FUTSTK", "FUTCOM")
    ]
    lot_size = None
    if fut_candidates:
        try:
            fut_candidates.sort(key=lambda r: datetime.strptime(r.get("expiry", ""), "%d%b%Y"))
        except Exception:
            pass
        lot_size = int(fut_candidates[0].get("lotsize", 0)) or None

    opt_strikes = sorted({
        int(row["strike"]) / 100
        for row in scrip_master
        if row.get("name") == name and row.get("instrumenttype") in ("OPTIDX", "OPTSTK")
        and row.get("strike")
    })
    strike_step = None
    if len(opt_strikes) >= 2:
        diffs = [round(b - a, 2) for a, b in zip(opt_strikes, opt_strikes[1:]) if b > a]
        if diffs:
            strike_step = min(diffs)

    if lot_size is None and strike_step is None:
        return None

    return {"lot_size": lot_size or 0, "strike_step": strike_step or 0}
# broker.py cha SHEVTI ha function ADD kara (existing kahihi badla naka)

INDEX_LTP_TOKENS = {
    # (exchange, symboltoken, tradingsymbol) - Angel One cha well-known index tokens
    "NIFTY": ("NSE", "99926000", "Nifty 50"),
    "BANKNIFTY": ("NSE", "99926009", "Nifty Bank"),
    "SENSEX": ("BSE", "99919000", "SENSEX"),
}


def get_index_ltp(symbol_key):
    """
    Index cha live spot price थेट Angel One वरून (yfinance ऐवजी) आणतो.
    yfinance kadhi kadhi stale/juna data देतो, tyामुळे strike calculation
    chukते - he function tyavar उपाय आहे. Adchan aali tar None.
    """
    smart_api = get_smart_api_session()
    if smart_api is None:
        return None

    mapping = INDEX_LTP_TOKENS.get(symbol_key)
    if mapping is None:
        return None

    exchange, token, tradingsymbol = mapping
    try:
        ltp_resp = smart_api.ltpData(exchange, tradingsymbol, token)
        if ltp_resp.get("status") and ltp_resp.get("data"):
            return float(ltp_resp["data"]["ltp"])
        log.warning(f"Index LTP fetch returned no data for {symbol_key}: {ltp_resp}")
        return None
    except Exception as e:
        log.exception(f"Index LTP fetch failed for {symbol_key}")
        return None
