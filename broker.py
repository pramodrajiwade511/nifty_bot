# broker.py
import os
import pyotp
import requests
import pandas as pd
from SmartApi import SmartConnect

# फायरबेस डेटाबेस डॅशबोर्डवरून इथे पास केला जाईल
db = None

SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
_scrip_master_cache = None

# Angel One वर NSE index chi live price (LTP) sathi lagणारे fixed token/tradingsymbol
# ⚠️ he tokens Angel One cha scrip master vaparun verify kara (badalू शकतात)
INDEX_INFO = {
    "NIFTY": {"exchange": "NSE", "tradingsymbol": "Nifty 50", "symboltoken": "99926000"},
    "BANKNIFTY": {"exchange": "NSE", "tradingsymbol": "Nifty Bank", "symboltoken": "99926009"},
    "FINNIFTY": {"exchange": "NSE", "tradingsymbol": "Nifty Fin Service", "symboltoken": "99926037"},
}

# Stocks jya trackच karायच्या - navin stock add karayla ithe fakt navач टाka
STOCK_LIST = ["RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "SBIN", "AXISBANK", "ITC", "LT", "KOTAKBANK", "TATASTEEL"]


def load_scrip_master():
    """Angel One cha संपूर्ण instrument list ekdach download karun cache karto."""
    global _scrip_master_cache
    if _scrip_master_cache is not None:
        return _scrip_master_cache
    try:
        resp = requests.get(SCRIP_MASTER_URL, timeout=30)
        _scrip_master_cache = resp.json()
        return _scrip_master_cache
    except Exception as e:
        print(f"Scrip master download error: {e}")
        return None


def find_equity_token(symbol):
    """
    Scrip master madhun konतahi NSE stock (RELIANCE, TCS, इ.) cha
    tradingsymbol ani token shodhto - "{symbol}-EQ" format वापरून.
    """
    scrip_master = load_scrip_master()
    if scrip_master is None:
        return None, None

    expected = f"{symbol.upper()}-EQ"
    for instrument in scrip_master:
        if instrument.get("exch_seg") == "NSE" and instrument.get("symbol", "").upper() == expected:
            return instrument.get("symbol"), instrument.get("token")
    return None, None


class AngelOneConnector:
    def __init__(self):
        self.smart_conn = None
        self.last_error = None

    def login_with_user_credentials(self, api_key, client_code, password, totp_secret):
        """युझरने स्क्रीनवर टाकलेल्या क्रेडेंशियल्सवरून ऑटो-लॉगइन करणे"""
        try:
            self.smart_conn = SmartConnect(api_key=api_key)
            totp = pyotp.TOTP(totp_secret).now()
            session_data = self.smart_conn.generateSession(client_code, password, totp)
            if not session_data.get("status"):
                self.smart_conn = None
                self.last_error = str(session_data)
                return f"❌ लॉगइन अयशस्वी: {session_data}"
            return "🟢 कनेक्टेड: एंजल वन लॉगइन यशस्वी!"
        except Exception as e:
            self.smart_conn = None
            self.last_error = str(e)
            return f"❌ लॉगइन अयशस्वी: कृपया क्रेडेंशियल्स तपासा ({str(e)})"

    def _resolve_symbol_info(self, symbol):
        """
        Index (NIFTY/BANKNIFTY/FINNIFTY) असेल tar INDEX_INFO madhun,
        nasel tar (stock असेल) scrip master varun equity token shodhto.
        Return: {"exchange":..., "tradingsymbol":..., "symboltoken":...} kiva None
        """
        info = next((v for k, v in INDEX_INFO.items() if k in symbol.upper()), None)
        if info is not None:
            return info

        tradingsymbol, token = find_equity_token(symbol)
        if tradingsymbol and token:
            return {"exchange": "NSE", "tradingsymbol": tradingsymbol, "symboltoken": token}
        return None

    def get_live_market_price(self, symbol):
        """
        NSE कडून खऱ्या मार्केटची लाईव्ह किंमत (LTP) मिळवणे - index किंवा stock donhi sathi.
        Session nasel (login zala nahi) tar fakt fallback price deto - te
        khara live nahi, tyachi jaणीव thevaच.
        """
        fallback = {"NIFTY": 24251.15, "BANKNIFTY": 52140.30, "FINNIFTY": 23800.0}.get(
            next((k for k in ("NIFTY", "BANKNIFTY", "FINNIFTY") if k in symbol.upper()), None), 102.5
        )

        if not self.smart_conn:
            return fallback

        info = self._resolve_symbol_info(symbol)
        if info is None:
            return fallback

        try:
            ltp_data = self.smart_conn.ltpData(info["exchange"], info["tradingsymbol"], info["symboltoken"])
            if ltp_data.get("status") and ltp_data.get("data"):
                return float(ltp_data["data"]["ltp"])
            return fallback
        except Exception as e:
            self.last_error = str(e)
            return fallback

    def get_nse_order_flow(self, symbol):
        """
        Live market depth (5 levels cha bid/ask volume) Angel One kadun anto -
        index किंवा stock donhi sathi.
        Session nasel kiva symbol token sapadla nahi tar dummy backup data
        deto (app crash hoऊ nये, pan he 'live' NAHI he lakshात theva).
        """
        if not self.smart_conn:
            return self._dummy_order_flow()

        info = self._resolve_symbol_info(symbol)
        if info is None:
            return self._dummy_order_flow()

        try:
            market_data = self.smart_conn.getMarketData("FULL", {info["exchange"]: [info["symboltoken"]]})
            if not market_data.get("status"):
                return self._dummy_order_flow()

            fetched = market_data["data"]["fetched"][0]
            depth = fetched.get("depth", {})
            buy_levels = depth.get("buy", [])
            sell_levels = depth.get("sell", [])

            rows = []
            for i in range(min(len(buy_levels), len(sell_levels))):
                buy_qty = buy_levels[i].get("quantity", 0)
                sell_qty = sell_levels[i].get("quantity", 0)
                price = buy_levels[i].get("price", 0)
                if buy_qty > sell_qty * 1.5:
                    report = "🟢 Call Buy Trigger"
                elif sell_qty > buy_qty * 1.5:
                    report = "🚨 Put Buy / Sell"
                else:
                    report = "Neutral"
                rows.append({"price": price, "bid_vol": buy_qty, "ask_vol": sell_qty, "report": report})

            if not rows:
                return self._dummy_order_flow()
            return pd.DataFrame(rows)
        except Exception as e:
            self.last_error = str(e)
            return self._dummy_order_flow()

    def _dummy_order_flow(self):
        """⚠️ HA KHARA DATA NAHI - fakt session/connection nasel tevha app crash
        na houता dakhavण्yasathi backup. Yavar trading decision GHEUU NAKA."""
        live_depth = [
            {"price": 115.0, "bid_vol": 4000, "ask_vol": 12000, "report": "🚨 Resistance Level (DEMO DATA)"},
            {"price": 110.0, "bid_vol": 3000, "ask_vol": 38000, "report": "🚀 Strong Call Buy (DEMO DATA)"},
            {"price": 105.0, "bid_vol": 9000, "ask_vol": 14000, "report": "Neutral (DEMO DATA)"},
            {"price": 100.0, "bid_vol": 15000, "ask_vol": 18000, "report": "🟢 Call Buy Trigger (DEMO DATA)"},
            {"price": 95.0, "bid_vol": 42000, "ask_vol": 7000, "report": "🚨 Put Buy / Sell (DEMO DATA)"},
            {"price": 90.0, "bid_vol": 25000, "ask_vol": 11000, "report": "🟢 Support Level (DEMO DATA)"},
        ]
        return pd.DataFrame(live_depth)


# ग्लोबल ऑब्जेक्ट तयार करणे जे main.py द्वारे वापरले जाते
angel_broker = AngelOneConnector()


def get_order_flow(symbol):
    """
    main.py 'broker.get_order_flow(symbol)' असं call kartो, pan class cha
    method 'get_nse_order_flow' naावाने hota - naाव jullat navhती, tyामुळे
    prattyek veli crash houन dummy data yeत hota. Ha wrapper function tोच
    naाव-गोंधळ fix kartो.
    """
    return angel_broker.get_nse_order_flow(symbol)


def get_live_price(symbol):
    """main.py sathi सोपं module-level wrapper."""
    return angel_broker.get_live_market_price(symbol)
