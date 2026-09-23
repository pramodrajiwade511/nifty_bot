import os
import requests
import pandas as pd
import pandas_ta as ta
from flask import Flask, request, jsonify
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    import broker
    BROKER_AVAILABLE = True
except Exception as e:
    print(f"broker.py load error: {e}")
    BROKER_AVAILABLE = False

app = Flask(__name__)
IST = ZoneInfo("Asia/Kolkata")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# LIVE_TRADING="true" asel tarच khऱ्या Angel One var actual order jाईl.
# Nasel/khali asel tar bot fakt PAPER mode madhe chalel (Telegram alerts fakt,
# khara paisa risk madhे nahi). Test purna zalyavarच "true" kara.
LIVE_TRADING = os.environ.get("LIVE_TRADING", "false").lower() == "true"

ALL_SYMBOLS = {
    "NIFTY": {"ticker": "^NSEI", "lot_size": 65, "strike_step": 50, "display": "Nifty 50"},
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot_size": 30, "strike_step": 100, "display": "Bank Nifty"},
    "SENSEX": {"ticker": "^BSESN", "lot_size": 20, "strike_step": 100, "display": "Sensex"},
    "GOLD": {"ticker": None, "source": "MCX", "lot_size": 0, "strike_step": 0, "display": "Gold (MCX)"},
    "SILVER": {"ticker": None, "source": "MCX", "lot_size": 0, "strike_step": 0, "display": "Silver (MCX)"},
    "CRUDEOIL": {"ticker": None, "source": "MCX", "lot_size": 0, "strike_step": 0, "display": "Crude Oil (MCX)"},
}
INDICES_KEYS = ["NIFTY", "BANKNIFTY", "SENSEX"]
COMMODITY_KEYS = ["GOLD", "SILVER", "CRUDEOIL"]
SYMBOL_GROUP = os.environ.get("SYMBOL_GROUP", "ALL")

if SYMBOL_GROUP == "INDICES":
    SYMBOLS = {k: v for k, v in ALL_SYMBOLS.items() if k in INDICES_KEYS}
elif SYMBOL_GROUP == "COMMODITIES":
    SYMBOLS = {k: v for k, v in ALL_SYMBOLS.items() if k in COMMODITY_KEYS}
else:
    SYMBOLS = ALL_SYMBOLS

state = {
    sym: {
        "daily_trades": [],
        "last_status_price": None,
        "last_status_time": None,
        "ce_entry": None,
        "ce_sl": None,
        "ce_peak_pnl": 0.0,
        "pe_entry": None,
        "pe_sl": None,
        "pe_peak_pnl": 0.0,
        "active_strike": None,
    }
    for sym in SYMBOLS
}

last_gm_date = ""
last_daily_summary_date = ""

SL_POINTS = 10
TRAIL_POINTS = 10


def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")


def fix_multiindex(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def try_get_real_premium(symbol_key, strike, option_type):
    if not BROKER_AVAILABLE:
        return None
    try:
        return broker.get_option_premium(symbol_key, strike, option_type)
    except Exception as e:
        print(f"Real premium fetch error: {e}")
        return None


def place_real_order(symbol_key, strike, option_type, transaction_type, quantity):
    if not LIVE_TRADING:
        print(f"[PAPER MODE] Would place {transaction_type} {symbol_key} {strike}{option_type} x{quantity}")
        return {"paper": True}
    if not BROKER_AVAILABLE:
        return None
    try:
        return broker.place_order(symbol_key, strike, option_type, transaction_type, quantity)
    except Exception as e:
        print(f"Order placement error: {e}")
        return None


def get_today_total_pnl(today_str):
    total = 0
    for sym in SYMBOLS:
        total += sum(t['pnl'] for t in state[sym]["daily_trades"] if t['date'] == today_str)
    return total


def calculate_reports(symbol_key):
    daily_trades = state[symbol_key]["daily_trades"]
    display_name = SYMBOLS[symbol_key]["display"]
    if not daily_trades:
        return f"📊 {display_name}: अजून कोणताही ट्रेड पूर्ण झाला नाही."
    today_str = datetime.now(IST).strftime('%Y-%m-%d')
    today_trades = [t for t in daily_trades if t['date'] == today_str]
    lines = [f"📊 **{display_name} REPORT** 📊"]
    today_pnl = 0
    for t in today_trades:
        today_pnl += t['pnl']
        lines.append(f"• {t['type']} {t['strike']} | Entry: {t['entry']} → Exit: {t['exit']} | P&L: ₹{round(t['pnl'],2)}")
    lines.append(f"\n🗓️ आजचा एकूण P&L: ₹{round(today_pnl, 2)}")
    return "\n".join(lines)


def check_ema_straddle_for_symbol(symbol_key, now, today_str, current_time_str):
    """
    EMA9/EMA21 crossover (koणत्याही dishela) zala ki CE ani PE donhi ATM options
    ekaच वेळी BUY karto. Pratyek leg la swतंत्र 10-point SL + 10-point trailing SL
    (PREMIUM वर). Ekada position open asel tar navीn entry ghetli jात नाही.
    """
    global last_gm_date
    cfg = SYMBOLS[symbol_key]
    s = state[symbol_key]
    lot_size = cfg["lot_size"]
    strike_step = cfg["strike_step"]
    display_name = cfg["display"]

    if lot_size <= 0 or not BROKER_AVAILABLE:
        return

    if cfg.get("source") == "MCX":
        df = broker.get_mcx_historical_df(symbol_key)
    else:
        df = yf.download(tickers=cfg["ticker"], period="5d", interval="5m", progress=False)
        df = fix_multiindex(df)

    if df is None or df.empty or len(df) < 22:
        return

    df['EMA9'] = ta.ema(df['Close'], length=9)
    df['EMA21'] = ta.ema(df['Close'], length=21)

    latest_price = round(df['Close'].iloc[-1], 2)
    latest_ema9 = df['EMA9'].iloc[-1]
    latest_ema21 = df['EMA21'].iloc[-1]
    prev_ema9 = df['EMA9'].iloc[-2]
    prev_ema21 = df['EMA21'].iloc[-2]

    s["last_status_price"] = latest_price
    s["last_status_time"] = now.strftime('%H:%M:%S')

    crossover_up = (not pd.isna(prev_ema9)) and (not pd.isna(prev_ema21)) and prev_ema9 <= prev_ema21 and latest_ema9 > latest_ema21
    crossover_down = (not pd.isna(prev_ema9)) and (not pd.isna(prev_ema21)) and prev_ema9 >= prev_ema21 and latest_ema9 < latest_ema21
    crossover_happened = crossover_up or crossover_down

    already_active = s["ce_entry"] is not None or s["pe_entry"] is not None

    if not already_active and crossover_happened and current_time_str >= "09:17" and current_time_str < "15:15":
        # yfinance kadhi kadhi stale price देतो, tyामुळे strike calculation sathi
        # thet Angel One cha live index price vaparto (jast bharwaसाcha). Nasel
        # milala tar yfinance cha price fallback mhanun vaparto.
        live_spot = broker.get_index_ltp(symbol_key) if cfg.get("source") != "MCX" else None
        strike_calc_price = live_spot if live_spot is not None else latest_price
        atm_strike = round(strike_calc_price / strike_step) * strike_step
        ce_premium = try_get_real_premium(symbol_key, atm_strike, 'CE')
        pe_premium = try_get_real_premium(symbol_key, atm_strike, 'PE')

        if ce_premium is None or pe_premium is None:
            return

        ce_order = place_real_order(symbol_key, atm_strike, 'CE', 'BUY', lot_size)
        pe_order = place_real_order(symbol_key, atm_strike, 'PE', 'BUY', lot_size)
        if LIVE_TRADING and (ce_order is None or pe_order is None):
            send_telegram_message(f"🚨 {display_name}: LIVE order placement fail zala")
            return

        s["ce_entry"] = ce_premium
        s["ce_sl"] = round(ce_premium - SL_POINTS, 2)
        s["ce_peak_pnl"] = 0.0
        s["pe_entry"] = pe_premium
        s["pe_sl"] = round(pe_premium - SL_POINTS, 2)
        s["pe_peak_pnl"] = 0.0
        s["active_strike"] = atm_strike

        mode_tag = "🔴 LIVE" if LIVE_TRADING else "📝 PAPER"
        direction = "Bullish (EMA9 वर क्रॉस)" if crossover_up else "Bearish (EMA9 खाली क्रॉस)"
        send_telegram_message(
            f"🟡 **{display_name} EMA CROSSOVER — CE+PE BUY** [{mode_tag}]\n\n"
            f"Crossover: {direction}\nStrike (ATM): {atm_strike}\n"
            f"👉 BUY {atm_strike} CE | Entry: ₹{ce_premium} | SL: ₹{s['ce_sl']}\n"
            f"👉 BUY {atm_strike} PE | Entry: ₹{pe_premium} | SL: ₹{s['pe_sl']}\n\n"
            f"दोन्ही legs वर 10-point SL + 10-point Trailing SL."
        )
        return

    if s["ce_entry"] is not None:
        atm_strike = s["active_strike"]
        ce_ltp = try_get_real_premium(symbol_key, atm_strike, 'CE')
        if ce_ltp is not None:
            pnl = ce_ltp - s["ce_entry"]
            s["ce_peak_pnl"] = max(s["ce_peak_pnl"], pnl)
            trailing_hit = s["ce_peak_pnl"] > 0 and (s["ce_peak_pnl"] - pnl) >= TRAIL_POINTS
            sl_hit = ce_ltp <= s["ce_sl"]
            day_end = current_time_str >= "15:20"
            if sl_hit or trailing_hit or day_end:
                reason = "SL Hit" if sl_hit else ("Trailing SL Hit" if trailing_hit else "Day End Square-off")
                place_real_order(symbol_key, atm_strike, 'CE', 'SELL', lot_size)
                leg_pnl = round(pnl * lot_size, 2)
                mode_tag = "🔴 LIVE" if LIVE_TRADING else "📝 PAPER"
                send_telegram_message(f"🔴 {display_name} CE EXIT ({reason}) [{mode_tag}]\nExit: ₹{ce_ltp} | P&L: ₹{leg_pnl}")
                s["daily_trades"].append({'date': today_str, 'type': 'CE', 'strike': f"{atm_strike} CE", 'entry': s["ce_entry"], 'exit': ce_ltp, 'pnl': leg_pnl})
                s["ce_entry"] = None
                s["ce_sl"] = None
                s["ce_peak_pnl"] = 0.0
            else:
                new_sl = round(ce_ltp - TRAIL_POINTS, 2)
                if new_sl > s["ce_sl"]:
                    s["ce_sl"] = new_sl

    if s["pe_entry"] is not None:
        atm_strike = s["active_strike"]
        pe_ltp = try_get_real_premium(symbol_key, atm_strike, 'PE')
        if pe_ltp is not None:
            pnl = pe_ltp - s["pe_entry"]
            s["pe_peak_pnl"] = max(s["pe_peak_pnl"], pnl)
            trailing_hit = s["pe_peak_pnl"] > 0 and (s["pe_peak_pnl"] - pnl) >= TRAIL_POINTS
            sl_hit = pe_ltp <= s["pe_sl"]
            day_end = current_time_str >= "15:20"
            if sl_hit or trailing_hit or day_end:
                reason = "SL Hit" if sl_hit else ("Trailing SL Hit" if trailing_hit else "Day End Square-off")
                place_real_order(symbol_key, atm_strike, 'PE', 'SELL', lot_size)
                leg_pnl = round(pnl * lot_size, 2)
                mode_tag = "🔴 LIVE" if LIVE_TRADING else "📝 PAPER"
                send_telegram_message(f"🔴 {display_name} PE EXIT ({reason}) [{mode_tag}]\nExit: ₹{pe_ltp} | P&L: ₹{leg_pnl}")
                s["daily_trades"].append({'date': today_str, 'type': 'PE', 'strike': f"{atm_strike} PE", 'entry': s["pe_entry"], 'exit': pe_ltp, 'pnl': leg_pnl})
                s["pe_entry"] = None
                s["pe_sl"] = None
                s["pe_peak_pnl"] = 0.0
            else:
                new_sl = round(pe_ltp - TRAIL_POINTS, 2)
                if new_sl > s["pe_sl"]:
                    s["pe_sl"] = new_sl

    if s["ce_entry"] is None and s["pe_entry"] is None and s["active_strike"] is not None:
        send_telegram_message(calculate_reports(symbol_key))
        s["active_strike"] = None


def check_signals():
    global last_gm_date, last_daily_summary_date
    now = datetime.now(IST)
    today_str = now.strftime('%Y-%m-%d')
    current_time_str = now.strftime('%H:%M')
    weekday = now.weekday()

    if weekday >= 5 or current_time_str < "09:00" or current_time_str > "15:35":
        return

    if current_time_str >= "09:00" and current_time_str < "09:15" and last_gm_date != today_str:
        mode_tag = "🔴 LIVE TRADING" if LIVE_TRADING else "📝 PAPER MODE"
        send_telegram_message(f"Good Morning! EMA Crossover CE+PE Bot सक्रिय झाला. Mode: {mode_tag}")
        last_gm_date = today_str

    for symbol_key in SYMBOLS:
        try:
            check_ema_straddle_for_symbol(symbol_key, now, today_str, current_time_str)
        except Exception as e:
            print(f"Error for {symbol_key}: {e}")
            send_telegram_message(f"⚠️ Bot Error ({symbol_key}): {e}")

    if current_time_str >= "15:30" and last_daily_summary_date != today_str:
        total_pnl = get_today_total_pnl(today_str)
        send_telegram_message(f"🔔 **DAY END SUMMARY** ({today_str})\n💰 एकूण आजचा नफा/तोटा: ₹{round(total_pnl, 2)}")
        last_daily_summary_date = today_str


@app.route('/')
def home():
    print("Cron-job ping received.")
    check_signals()
    mode_text = "LIVE TRADING" if LIVE_TRADING else "PAPER MODE"
    return f"Bot is running! EMA Crossover CE+PE Bot Active. Mode: {mode_text}", 200


@app.route('/api/status')
def api_status():
    today_str = datetime.now(IST).strftime('%Y-%m-%d')
    symbols_data = []
    for symbol_key, cfg in SYMBOLS.items():
        s = state[symbol_key]
        symbols_data.append({
            "key": symbol_key, "display": cfg["display"],
            "price": s["last_status_price"],
            "ce_entry": s.get("ce_entry"), "ce_sl": s.get("ce_sl"),
            "pe_entry": s.get("pe_entry"), "pe_sl": s.get("pe_sl"),
        })
    total_pnl = get_today_total_pnl(today_str)
    return jsonify({"live_trading": LIVE_TRADING, "symbols": symbols_data, "total_pnl_today": total_pnl, "updated_at": datetime.now(IST).strftime('%H:%M:%S')})


@app.route('/test-broker')
def test_broker():
    if not BROKER_AVAILABLE:
        msg = "❌ broker.py load zala nahi."
        send_telegram_message(msg)
        return msg, 200
    try:
        session = broker.get_smart_api_session()
        if session:
            mode_tag = "🔴 LIVE TRADING ON" if LIVE_TRADING else "📝 PAPER MODE (LIVE_TRADING=false)"
            msg = f"✅ Angel One session यशस्वी झाले! Connection working ahe.\nMode: {mode_tag}"
        else:
            detail = broker.get_last_error() or "unknown error"
            msg = f"❌ Angel One session fail zala.\nकारण: {detail}"
        send_telegram_message(msg)
        return msg, 200
    except Exception as e:
        err_msg = f"❌ Broker test error: {e}"
        send_telegram_message(err_msg)
        return err_msg, 200


@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    try:
        update = request.get_json()
        if not update or "message" not in update or "text" not in update["message"]:
            return "OK", 200
        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"].lower().strip()

        if text == "/start":
            mode_tag = "🔴 LIVE TRADING" if LIVE_TRADING else "📝 PAPER MODE"
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          json={"chat_id": chat_id, "text": f"😊 EMA Crossover CE+PE Bot सुरू झाला!\nMode: {mode_tag}\n/report ani /status vapra."})
        elif text == "/report":
            report_message = "\n\n".join(calculate_reports(sym) for sym in SYMBOLS)
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": report_message})
        elif text == "/status":
            mode_tag = "🔴 LIVE TRADING" if LIVE_TRADING else "📝 PAPER MODE"
            lines = [f"🔍 **BOT STATUS** (Mode: {mode_tag})"]
            for symbol_key, cfg in SYMBOLS.items():
                s = state[symbol_key]
                ce_text = f"CE Entry: ₹{s['ce_entry']} SL: ₹{s['ce_sl']}" if s.get("ce_entry") else "CE: उघडलेलं नाही"
                pe_text = f"PE Entry: ₹{s['pe_entry']} SL: ₹{s['pe_sl']}" if s.get("pe_entry") else "PE: उघडलेलं नाही"
                lines.append(f"\n**{cfg['display']}**\nPrice: {s['last_status_price']}\n{ce_text}\n{pe_text}")
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": "\n".join(lines)})
        return "OK", 200
    except Exception as e:
        print(f"Error: {e}")
        return "Error", 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
