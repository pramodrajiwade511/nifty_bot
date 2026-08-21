import os
import requests
import pandas as pd
import pandas_ta as ta
import mplfinance as mpf
from flask import Flask, request
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np

# broker.py cha Angel One integration - nasel/fail zala tar bot band pडत nahi,
# fakt live premium ऐवजी estimate vaparला जाईल
try:
    import broker
    BROKER_AVAILABLE = True
except Exception as e:
    print(f"broker.py load error (estimated premium vaparla jaईl): {e}")
    BROKER_AVAILABLE = False

app = Flask(__name__)

IST = ZoneInfo("Asia/Kolkata")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# Dobhi indices sathi config - navin index add karaycha asel tar ithe entry takaycha
# ⚠️ VERIFY KARA: khालचे lot_size ANDAJE ahet (जुन्या NSE revision वरून). Angel One app
# madhe order place karताना actual lot size dakhavla jato - to eकदा check karून, khालche
# आकडे barobar aahet ki nahi ते confirm kara, karan chukicha lot size = chukicha P&L calc.
ALL_SYMBOLS = {
    "NIFTY": {"ticker": "^NSEI", "lot_size": 65, "strike_step": 50, "display": "Nifty 50"},
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot_size": 30, "strike_step": 100, "display": "Bank Nifty"},
    "SENSEX": {"ticker": "^BSESN", "lot_size": 20, "strike_step": 100, "display": "Sensex"},
    "RELIANCE": {"ticker": "RELIANCE.NS", "lot_size": 500, "strike_step": 10, "display": "Reliance"},
    "HDFCBANK": {"ticker": "HDFCBANK.NS", "lot_size": 650, "strike_step": 10, "display": "HDFC Bank"},
    "ICICIBANK": {"ticker": "ICICIBANK.NS", "lot_size": 700, "strike_step": 10, "display": "ICICI Bank"},
    "TCS": {"ticker": "TCS.NS", "lot_size": 225, "strike_step": 20, "display": "TCS"},
    "INFY": {"ticker": "INFY.NS", "lot_size": 500, "strike_step": 10, "display": "Infosys"},
    "SBIN": {"ticker": "SBIN.NS", "lot_size": 1875, "strike_step": 5, "display": "SBI"},
    "AXISBANK": {"ticker": "AXISBANK.NS", "lot_size": 875, "strike_step": 5, "display": "Axis Bank"},
    "ITC": {"ticker": "ITC.NS", "lot_size": 1575, "strike_step": 2.5, "display": "ITC"},
    "LT": {"ticker": "LT.NS", "lot_size": 275, "strike_step": 20, "display": "L&T"},
    "KOTAKBANK": {"ticker": "KOTAKBANK.NS", "lot_size": 400, "strike_step": 10, "display": "Kotak Bank"},
    # Commodities (MCX) - yfinance नाही, Angel One cha Historical Data API vaparto (source="MCX")
    # ⚠️ lot_size/strike_step ithe UNKNOWN ahet (verify na karता) - "/check-lot-sizes" route
    # deploy zalyavar automatic shodhून deईl, tovar he 0 dakhavtील (trades sathi vaparले jaणar
    # nahit jopर्yंत verify hot nahi).
    "GOLD": {"ticker": None, "source": "MCX", "lot_size": 0, "strike_step": 0, "display": "Gold (MCX)"},
    "SILVER": {"ticker": None, "source": "MCX", "lot_size": 0, "strike_step": 0, "display": "Silver (MCX)"},
    "CRUDEOIL": {"ticker": None, "source": "MCX", "lot_size": 0, "strike_step": 0, "display": "Crude Oil (MCX)"},
}

# SYMBOL_GROUP env variable var adharun kontya symbols track karayche te thरवतो.
# Yamule ekach code 2 veglya Render services var deploy karता येईल - ek indices sathi,
# ek stocks sathi - donhi independent, ekmekanवर परिणाम na houता.
# Render madhe SYMBOL_GROUP="INDICES" kiva SYMBOL_GROUP="STOCKS" kiva SYMBOL_GROUP="COMMODITIES" set kara.
# Set nasel tar (default) sagळे symbols ekaच bot madhe (jase aata ahे).
INDICES_KEYS = ["NIFTY", "BANKNIFTY", "SENSEX"]
COMMODITY_KEYS = ["GOLD", "SILVER", "CRUDEOIL"]
SYMBOL_GROUP = os.environ.get("SYMBOL_GROUP", "ALL")

if SYMBOL_GROUP == "INDICES":
    SYMBOLS = {k: v for k, v in ALL_SYMBOLS.items() if k in INDICES_KEYS}
elif SYMBOL_GROUP == "STOCKS":
    SYMBOLS = {k: v for k, v in ALL_SYMBOLS.items() if k not in INDICES_KEYS and k not in COMMODITY_KEYS}
elif SYMBOL_GROUP == "COMMODITIES":
    SYMBOLS = {k: v for k, v in ALL_SYMBOLS.items() if k in COMMODITY_KEYS}
else:
    SYMBOLS = ALL_SYMBOLS

# Pratyek symbol sathi swतंत्र state
state = {
    sym: {
        "current_trade": None,
        "entry_price": 0.0,
        "stop_loss": 0.0,
        "daily_trades": [],
        "s1": None,
        "r1": None,
        "pivot": None,
        "last_levels_date": "",
        "last_status_price": None,
        "last_status_dir": None,
        "last_status_time": None,
        "last_rsi": None,
        "last_adx": None,
        "or_high": None,
        "or_low": None,
        "or_date": "",
        "last_vwap": None,
        "atm_strike": None,
        "trade_date": None,
        "targets": None,
        "base_premium": None,
        "entry_spot": None,
        "option_type": None,
    }
    for sym in SYMBOLS
}

last_gm_date = ""
last_daily_summary_date = ""
last_error_msg = None
last_error_date = ""

STRATEGY_MODE = "ORB"  # "TREND" = SuperTrend+RSI+EMA+ADX (BUY+SELL donhi)
                        # "ORB" = Opening Range Breakout (fakt BUY, pahilya candle cha high todla tar)

MAX_INITIAL_SL_POINTS = 20  # ORB madhe Opening Range khup wide asel tar risk itka jasta nasava
                              # - ha maximum cap, actual SL (OR low/high) yापेksha jawal asel tar tोच vaparला jaईl

DAILY_PROFIT_TARGET = 1000  # Rupees - ha target zala ki tya divsa navin trade nahi
DAILY_LOSS_LIMIT = 1000     # Rupees - itka tota zala ki tya divsa navin trade nahi (capital protect karण्yasathi)
last_target_hit_date = ""
last_loss_limit_hit_date = ""


def get_today_total_pnl(today_str):
    """Donhi symbols (Nifty+BankNifty) cha aajcha combined realized P&L kadhto."""
    total = 0
    for sym in SYMBOLS:
        total += sum(t['pnl'] for t in state[sym]["daily_trades"] if t['date'] == today_str)
    return total


def daily_limit_reached(today_str):
    """
    Aajcha profit target (+₹1000) किंवा loss limit (-₹1000) touch झाला असेल tar
    True return karto - tyavelela navin trade ghyaycha nahi (existing open trade
    matra normally manage hot rahil, fakt navin entry band).
    """
    total_pnl = get_today_total_pnl(today_str)
    return total_pnl >= DAILY_PROFIT_TARGET or total_pnl <= -DAILY_LOSS_LIMIT


def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")


def send_telegram_chart(image_path, caption_text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': CHAT_ID, 'caption': caption_text}
            requests.post(url, files=files, data=data, timeout=15)
    except Exception as e:
        print(f"Error sending chart: {e}")


def fix_multiindex(df):
    """yfinance kadhi kadhi MultiIndex columns deta - te fix karnyasathi helper"""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def get_supertrend_columns(st_df):
    """pandas_ta version pramane SUPERT column names badaltat, tyamule dynamic shodhto"""
    st_col = None
    dir_col = None
    for c in st_df.columns:
        if c.startswith('SUPERTd_'):
            dir_col = c
        elif c.startswith('SUPERT_'):
            st_col = c
    return st_col, dir_col


def get_option_strikes(price, signal_type, strike_step):
    """
    Spot pricevaroon ATM, ITM, OTM strikes kadhto.
    signal_type 'BUY' -> Call (CE) options, 'SELL' -> Put (PE) options
    strike_step: Nifty=50, BankNifty=100
    """
    atm = round(price / strike_step) * strike_step
    option_type = "CE" if signal_type == "BUY" else "PE"

    if option_type == "CE":
        itm = atm - strike_step
        otm = atm + strike_step
    else:
        itm = atm + strike_step
        otm = atm - strike_step

    return {
        "ATM": f"{atm} {option_type}",
        "ITM": f"{itm} {option_type}",
        "OTM": f"{otm} {option_type}",
    }


def get_targets(entry_price, sl_price, signal_type):
    """
    Risk-Reward vaparun T1, T2, T3 target kadhto.
    Risk = entry ani SL madhla farak. T1=1x risk, T2=2x risk, T3=3x risk.
    """
    risk = abs(entry_price - sl_price)
    if signal_type == 'BUY':
        t1 = round(entry_price + risk * 1, 2)
        t2 = round(entry_price + risk * 2, 2)
        t3 = round(entry_price + risk * 3, 2)
    else:
        t1 = round(entry_price - risk * 1, 2)
        t2 = round(entry_price - risk * 2, 2)
        t3 = round(entry_price - risk * 3, 2)
    return {"T1": t1, "T2": t2, "T3": t3}


ATM_DELTA_ESTIMATE = 0.5  # ATM option cha delta साधारण 0.5 astoy - ha fakt ढोबळ अंदाज ahे


def get_estimated_premium_moves(entry_price, sl_price, targets):
    """
    Live option-chain data नाहीये, tyamule real premium dakhavता येत नाही.
    ATM Delta ~0.5 gruhit dharun, spot movement varun premium madhe
    andaje kiती point change hoईl te kadhto. Ha FAKT ANDAJ ahe,
    actual premium IV/theta/time decay var avalambun asto.
    """
    risk = abs(entry_price - sl_price)
    sl_move = round(risk * ATM_DELTA_ESTIMATE, 1)
    t1_move = round(abs(targets['T1'] - entry_price) * ATM_DELTA_ESTIMATE, 1)
    t2_move = round(abs(targets['T2'] - entry_price) * ATM_DELTA_ESTIMATE, 1)
    t3_move = round(abs(targets['T3'] - entry_price) * ATM_DELTA_ESTIMATE, 1)
    return {"SL": sl_move, "T1": t1_move, "T2": t2_move, "T3": t3_move}


def try_get_real_premium(symbol_key, strike, option_type):
    """
    Angel One var connect ahe ka te bघून, khara live option premium (LTP)
    fetch karण्याचा प्रयत्न karto. Koणतीही adchan aali (session nahi, symbol
    nahi sapadla, internet issue) tar None deto - tyavelela caller ne
    estimated premium vaparava.
    """
    if not BROKER_AVAILABLE:
        return None
    try:
        return broker.get_option_premium(symbol_key, strike, option_type)
    except Exception as e:
        print(f"Real premium fetch error: {e}")
        return None


def generate_signal_chart(df, signal_type, price_level, sl_price, symbol_key):
    """
    Trading app sarkha professional dark-theme candlestick chart banवतो.
    signal_type: 'BUY', 'SELL', 'BUY_EXIT', 'SELL_EXIT'
    """
    try:
        chart_df = df.tail(60).copy()
        chart_df.index.name = 'Date'

        is_up = signal_type in ('BUY', 'SELL_EXIT')

        marker_series = [np.nan] * len(chart_df)
        marker_series[-1] = price_level
        arrow_marker = '^' if is_up else 'v'
        arrow_color = '#00e676' if is_up else '#ff1744'

        apds = [
            mpf.make_addplot(marker_series, type='scatter', markersize=220,
                              marker=arrow_marker, color=arrow_color)
        ]

        s1 = state[symbol_key]["s1"]
        r1 = state[symbol_key]["r1"]

        hlines_list = [sl_price]
        hlines_colors = ['#ffab00']
        if s1:
            hlines_list.append(s1)
            hlines_colors.append('#2979ff')
        if r1:
            hlines_list.append(r1)
            hlines_colors.append('#d500f9')

        mc = mpf.make_marketcolors(
            up='#26a69a', down='#ef5350', edge='inherit', wick='inherit', volume='in'
        )
        style = mpf.make_mpf_style(
            base_mpf_style='nightclouds',
            marketcolors=mc,
            facecolor='#131722',
            edgecolor='#131722',
            gridcolor='#2a2e39',
            gridstyle='--',
            figcolor='#131722',
            rc={'axes.labelcolor': 'white', 'xtick.color': 'white', 'ytick.color': 'white'}
        )

        display_name = SYMBOLS[symbol_key]["display"]
        title_map = {
            'BUY': f'{display_name} — BUY CALL SIGNAL',
            'SELL': f'{display_name} — BUY PUT SIGNAL',
            'BUY_EXIT': f'{display_name} — BUY EXIT (SL HIT)',
            'SELL_EXIT': f'{display_name} — SELL EXIT (SL HIT)',
        }

        image_path = f"/tmp/chart_{symbol_key}_{signal_type}_{datetime.now(IST).strftime('%H%M%S')}.png"

        mpf.plot(
            chart_df,
            type='candle',
            style=style,
            addplot=apds,
            hlines=dict(hlines=hlines_list, colors=hlines_colors, linestyle='-.', linewidths=1.2),
            title=title_map.get(signal_type, display_name),
            ylabel='Price',
            figsize=(10, 6),
            savefig=dict(fname=image_path, dpi=150, bbox_inches='tight')
        )
        return image_path
    except Exception as e:
        print(f"Error generating chart: {e}")
        return None


def get_levels(ticker):
    try:
        df = yf.download(tickers=ticker, period="2d", interval="1d", progress=False)
        df = fix_multiindex(df)
        if len(df) >= 2:
            prev_day = df.iloc[-2]
            pivot = (prev_day['High'] + prev_day['Low'] + prev_day['Close']) / 3
            r1 = (2 * pivot) - prev_day['Low']
            s1 = (2 * pivot) - prev_day['High']
            return round(s1, 2), round(r1, 2), round(pivot, 2)
    except Exception as e:
        print(f"Error in get_levels: {e}")
    return None, None, None


BROKERAGE_PER_ORDER = 20  # ₹20 prati order (ANDAJ - Angel One cha actual F&O brokerage
                           # check kara, discount brokers sathi साधारण ₹20 flat असते,
                           # pan plan/scheme nusar badalू शकते)


def calculate_reports(symbol_key):
    daily_trades = state[symbol_key]["daily_trades"]
    display_name = SYMBOLS[symbol_key]["display"]
    if not daily_trades:
        return f"📊 {display_name}: अजून कोणताही ट्रेड पूर्ण झाला नाही."
    today_str = datetime.now(IST).strftime('%Y-%m-%d')
    today_trades = [t for t in daily_trades if t['date'] == today_str]

    lines = [f"📊 **{display_name} PERFORMANCE REPORT** 📊\n"]
    lines.append("📋 आजचे ट्रेड्स:")
    today_gross = 0
    today_brokerage = 0
    for t in today_trades:
        gross = t['pnl']
        brokerage = BROKERAGE_PER_ORDER * 2  # entry + exit = 2 orders
        net = gross - brokerage
        today_gross += gross
        today_brokerage += brokerage
        strike_text = t.get('strike') or '-'
        lines.append(
            f"• {t['type']} {strike_text} | Entry: {t['entry']} → Exit: {t['exit']}\n"
            f"  Gross P&L: ₹{round(gross,2)} | Brokerage(अंदाजे): ₹{brokerage} | Net: ₹{round(net,2)}"
        )

    total_trades = len(daily_trades)
    total_pnl = sum(t['pnl'] for t in daily_trades)
    weekly_avg = total_pnl / total_trades if total_trades > 0 else 0

    lines.append(f"\n🗓️ आजचा एकूण Gross नफा/तोटा: ₹{round(today_gross, 2)}")
    lines.append(f"💸 आजचं अंदाजे एकूण Brokerage: ₹{today_brokerage}")
    lines.append(f"✅ आजचा Net नफा/तोटा: ₹{round(today_gross - today_brokerage, 2)}")
    lines.append(f"\n📈 (bot suru zalyapasunche) एकूण ट्रेड्स: {total_trades}")
    lines.append(f"📉 सरासरी नफा प्रति ट्रेड (gross): ₹{round(weekly_avg, 2)}")
    lines.append(f"\n⚠️ Brokerage हे fakt अंदाजित आहे (₹20/order gृhit dharlay) — actual आकडा तुमच्या Angel One च्या contract note मध्ये चेक करा.")
    lines.append("⚠️ ही आकडेवारी फक्त bot शेवटचा restart झाल्यापासूनची आहे (persistent storage नाही, त्यामुळे खरी 'monthly' history यात नाही).")

    return "\n".join(lines)


def check_signals_for_symbol(symbol_key, now, today_str, current_time_str):
    """Ek specific symbol (NIFTY ki BANKNIFTY) sathi signal check karto"""
    global last_error_msg, last_error_date
    cfg = SYMBOLS[symbol_key]
    s = state[symbol_key]
    ticker = cfg["ticker"]
    lot_size = cfg["lot_size"]
    strike_step = cfg["strike_step"]
    display_name = cfg["display"]

    if current_time_str >= "09:10" and current_time_str < "09:25" and s["last_levels_date"] != today_str:
        s1, r1, pivot = get_levels(ticker)
        if s1 and r1:
            s["s1"], s["r1"], s["pivot"] = s1, r1, pivot
            levels_msg = (
                f"📊 **{display_name} DAILY LEVELS** 📊\n"
                f"🗓️ दिनांक: {today_str}\n"
                f"🔺 Resistance (R1): {r1}\n"
                f"🎯 Pivot Point: {pivot}\n"
                f"🔻 Support (S1): {s1}\n"
            )
            send_telegram_message(levels_msg)
            s["last_levels_date"] = today_str

    is_mcx = cfg.get("source") == "MCX"

    if is_mcx:
        if not BROKER_AVAILABLE:
            err = f"{display_name}: broker.py load nahi zala, MCX data milat nahi"
            if last_error_msg != err or last_error_date != today_str:
                send_telegram_message(f"⚠️ Bot Warning: {err}")
                last_error_msg, last_error_date = err, today_str
            return
        df = broker.get_mcx_historical_df(symbol_key)
    else:
        df = yf.download(tickers=ticker, period="5d", interval="5m", progress=False)
        df = fix_multiindex(df)
        if df.empty or len(df) < 20:
            # yfinance kadhi kadhi temporary glitch deta - ekda parat try karto
            import time
            time.sleep(2)
            df = yf.download(tickers=ticker, period="5d", interval="5m", progress=False)
            df = fix_multiindex(df)

    if df is None or df.empty or len(df) < 20:
        err = f"{display_name}: data empty ahe kiva 20 peksha kami rows aahet"
        if last_error_msg != err or last_error_date != today_str:
            send_telegram_message(f"⚠️ Bot Warning: {err}")
            last_error_msg, last_error_date = err, today_str
        return

    st = ta.supertrend(df['High'], df['Low'], df['Close'], length=10, multiplier=2.5)
    st_col, dir_col = get_supertrend_columns(st)
    if st_col is None or dir_col is None:
        err = f"{display_name}: Supertrend column sapadla nahi. Available: {st.columns.tolist()}"
        print(f"Error: {err}")
        if last_error_msg != err or last_error_date != today_str:
            send_telegram_message(f"⚠️ Bot Warning: {err}")
            last_error_msg, last_error_date = err, today_str
        return

    df['ST'] = st[st_col]
    df['ST_DIR'] = st[dir_col]

    # --- Confirmation indicators: RSI + EMA(9,21) + ADX (trend strength filter) ---
    # VWAP kadhla - Index (Nifty/BankNifty) sathi Yahoo Finance volume denat nahi,
    # tyamule VWAP kayam NaN yet hota ani confirmation kadhich pass hot navhta.
    df['RSI'] = ta.rsi(df['Close'], length=14)
    df['EMA9'] = ta.ema(df['Close'], length=9)
    df['EMA21'] = ta.ema(df['Close'], length=21)

    adx_df = ta.adx(df['High'], df['Low'], df['Close'], length=14)
    adx_col = next((c for c in adx_df.columns if c.startswith('ADX_')), None)
    df['ADX'] = adx_df[adx_col] if adx_col else None

    latest_price = round(df['Close'].iloc[-1], 2)
    prev_dir = df['ST_DIR'].iloc[-2]
    curr_dir = df['ST_DIR'].iloc[-1]

    latest_rsi = df['RSI'].iloc[-1]
    latest_ema9 = df['EMA9'].iloc[-1]
    latest_ema21 = df['EMA21'].iloc[-1]
    latest_adx = df['ADX'].iloc[-1] if df['ADX'] is not None else None
    strong_trend = (latest_adx is not None) and (not pd.isna(latest_adx)) and latest_adx > 20

    # BUY confirm: RSI bullish zone, fast EMA slow EMA peksha var, ani trend मजबूत asel tarच
    buy_confirmed = latest_rsi > 50 and latest_ema9 > latest_ema21 and strong_trend
    # SELL confirm: ulta
    sell_confirmed = latest_rsi < 50 and latest_ema9 < latest_ema21 and strong_trend

    # --- ORB (Opening Range Breakout) sathi: divsachi pahili 5-min candle cha High/Low mark karto ---
    if s["or_date"] != today_str:
        day_candles = df[df.index.strftime('%Y-%m-%d') == today_str]
        first_candle_candles = day_candles[day_candles.index.strftime('%H:%M') == '09:15']
        if not first_candle_candles.empty:
            s["or_high"] = round(first_candle_candles['High'].iloc[0], 2)
            s["or_low"] = round(first_candle_candles['Low'].iloc[0], 2)
            s["or_date"] = today_str
            send_telegram_message(
                f"🔔 {display_name} Opening Range Set!\n"
                f"High: {s['or_high']} | Low: {s['or_low']}\n"
                f"(High च्या वर price गेली तर BUY सिग्नल येईल)"
            )

    ORB_BREAKOUT_BUFFER = 5  # High/Low pasun itke points jasta gele tarach signal - fake breakouts kami karnyasathi

    orb_buy_confirmed = (
        STRATEGY_MODE == "ORB"
        and s["or_high"] is not None
        and latest_price > (s["or_high"] + ORB_BREAKOUT_BUFFER)
        and latest_rsi > 50
        and strong_trend
    )
    orb_sell_confirmed = (
        STRATEGY_MODE == "ORB"
        and s["or_low"] is not None
        and latest_price < (s["or_low"] - ORB_BREAKOUT_BUFFER)
        and latest_rsi < 50
        and strong_trend
    )

    # /status command sathi latest values save karto
    s["last_status_price"] = latest_price
    s["last_status_dir"] = curr_dir
    s["last_status_time"] = now.strftime('%H:%M:%S')
    s["last_rsi"] = round(latest_rsi, 1) if not pd.isna(latest_rsi) else None
    s["last_adx"] = round(latest_adx, 1) if latest_adx is not None and not pd.isna(latest_adx) else None
    s["last_vwap"] = None  # ata vaparat nahi, EMA vaparto

    # Trade active असताना pratyek check la simple tick pathavto (channel style सारखं)
    if s["current_trade"] is not None and s["base_premium"] is not None:
        # Live premium suruvatila (entry la) milala hota, tyavaroon ATM delta
        # vaparun sध्याचा estimated premium kadhto ani fakt tोच number pathavto.
        spot_move = latest_price - s["entry_spot"]
        if s["option_type"] == 'CE':
            premium_change = spot_move * ATM_DELTA_ESTIMATE
        else:
            premium_change = -spot_move * ATM_DELTA_ESTIMATE
        current_premium = round(s["base_premium"] + premium_change, 1)
        send_telegram_message(f"{current_premium}")
    elif s["current_trade"] is not None:
        # Entry veli live premium milala navhta, tyamule honestly spot dakhavतो
        send_telegram_message(f"{display_name}: {latest_price}")

    trade_closed = False
    pnl_generated = 0
    exit_price_recorded = latest_price

    # SAFETY NET: jar konतahi karanamule (cron delay, market close overnight, etc.)
    # aajच्या aadhicha trade ajunही "open" rahila asel, tar to lagech force-close
    # karto - carry-forward kadhीच hou dyaycha nahi.
    if s["current_trade"] is not None and s["trade_date"] is not None and s["trade_date"] != today_str:
        if s["current_trade"] == 'BUY':
            pnl_generated = (latest_price - s["entry_price"]) * lot_size
        else:
            pnl_generated = (s["entry_price"] - latest_price) * lot_size
        send_telegram_message(
            f"🚨 {display_name} SAFETY SQUARE-OFF! (जुना ट्रेड carry-forward झाला होता, "
            f"आता force-close केला)\nExit Price: {latest_price}\nP&L: ₹{pnl_generated}"
        )
        s["daily_trades"].append({
            'date': s["trade_date"], 'type': s["current_trade"], 'strike': s["atm_strike"],
            'entry': s["entry_price"], 'exit': latest_price, 'pnl': pnl_generated,
        })
        s["current_trade"] = None
        s["atm_strike"] = None
        s["targets"] = None
        s["base_premium"] = None
        s["entry_spot"] = None
        s["option_type"] = None
        s["trade_date"] = None
        return

    if s["current_trade"] == 'BUY':
        new_sl = latest_price - 10
        if s["stop_loss"] == 0.0 or new_sl > s["stop_loss"]:
            s["stop_loss"] = round(new_sl, 2)
            send_telegram_message(f"🔁 {display_name} Stop Loss ट्रेल झाला! नवीन SL: {s['stop_loss']}")
        if latest_price <= s["stop_loss"]:
            pnl_generated = (latest_price - s["entry_price"]) * lot_size
            exit_price_recorded = latest_price
            send_telegram_message(f"🔴 {display_name} BUY EXIT! SL Hit\nExit Price: {latest_price}\nP&L: ₹{pnl_generated}")
            chart_path = generate_signal_chart(df, 'BUY_EXIT', latest_price, s["stop_loss"], symbol_key)
            if chart_path:
                send_telegram_chart(chart_path, f"{display_name} BUY EXIT | Exit: {latest_price} | P&L: ₹{pnl_generated}")
            trade_closed = True
        elif current_time_str >= "15:20":
            pnl_generated = (latest_price - s["entry_price"]) * lot_size
            exit_price_recorded = latest_price
            send_telegram_message(f"🌇 {display_name} DAY END SQUARE OFF (Carry Forward Nahi)\nExit Price: {latest_price}\nP&L: ₹{pnl_generated}")
            trade_closed = True

    elif s["current_trade"] == 'SELL':
        new_sl = latest_price + 10
        if s["stop_loss"] == 0.0 or new_sl < s["stop_loss"]:
            s["stop_loss"] = round(new_sl, 2)
            send_telegram_message(f"🔁 {display_name} Stop Loss ट्रेल झाला! नवीन SL: {s['stop_loss']}")
        if latest_price >= s["stop_loss"]:
            pnl_generated = (s["entry_price"] - latest_price) * lot_size
            exit_price_recorded = latest_price
            send_telegram_message(f"🔴 {display_name} SELL EXIT! SL Hit\nExit Price: {latest_price}\nP&L: ₹{pnl_generated}")
            chart_path = generate_signal_chart(df, 'SELL_EXIT', latest_price, s["stop_loss"], symbol_key)
            if chart_path:
                send_telegram_chart(chart_path, f"{display_name} SELL EXIT | Exit: {latest_price} | P&L: ₹{pnl_generated}")
            trade_closed = True
        elif current_time_str >= "15:20":
            pnl_generated = (s["entry_price"] - latest_price) * lot_size
            exit_price_recorded = latest_price
            send_telegram_message(f"🌇 {display_name} DAY END SQUARE OFF (Carry Forward Nahi)\nExit Price: {latest_price}\nP&L: ₹{pnl_generated}")
            trade_closed = True

    if trade_closed:
        s["daily_trades"].append({
            'date': today_str,
            'type': s["current_trade"],
            'strike': s["atm_strike"],
            'entry': s["entry_price"],
            'exit': exit_price_recorded,
            'pnl': pnl_generated,
        })
        s["current_trade"] = None
        s["atm_strike"] = None
        s["targets"] = None
        s["base_premium"] = None
        s["entry_spot"] = None
        s["option_type"] = None
        s["trade_date"] = None
        send_telegram_message(calculate_reports(symbol_key))

    # Market open zalyavar pahili 5 minitं khup volatile astat, tyamule navin trade
    # fakt 09:20 nantarach ghyaycha. AANI 15:15 nantar navin trade ghyaycha NAHI -
    # (aadhi hya condition la vartchi limit navhती, tyamule 3:33 sarkhya veli navin
    # trade ughadla jayacha ani carry-forward houn motha risk yayacha - ha fix tyasathich)
    if (
        s["current_trade"] is None
        and current_time_str >= "09:17" and current_time_str < "15:15"
        and lot_size > 0  # lot_size verify न झालेला (0) asel tar (MCX commodities) trade skip
    ):
        entry_condition = orb_buy_confirmed if STRATEGY_MODE == "ORB" else (prev_dir == -1 and curr_dir == 1 and buy_confirmed)
        if entry_condition:
            s["current_trade"] = 'BUY'
            s["entry_price"] = latest_price
            s["stop_loss"] = max(s["or_low"], latest_price - MAX_INITIAL_SL_POINTS) if (STRATEGY_MODE == "ORB" and s["or_low"]) else latest_price - 15
            s["trade_date"] = today_str
            strikes = get_option_strikes(latest_price, 'BUY', strike_step)
            targets = get_targets(latest_price, s["stop_loss"], 'BUY')
            premium_moves = get_estimated_premium_moves(latest_price, s["stop_loss"], targets)
            s["atm_strike"] = strikes['ATM']
            s["targets"] = targets

            atm_strike_num = round(latest_price / strike_step) * strike_step
            real_premium = try_get_real_premium(symbol_key, atm_strike_num, 'CE')
            s["entry_spot"] = latest_price
            s["option_type"] = 'CE'
            s["base_premium"] = real_premium  # None asel tar estimate न देता spot ticks dakhavtो
            if real_premium is not None:
                premium_line = f"💰 **Live Premium: ₹{real_premium}** (Angel One वरून)\n\n"
            else:
                premium_line = (
                    f"📊 अंदाजे Premium Movement (ATM, Delta~0.5):\n"
                    f"SL लागल्यास: सुमारे -{premium_moves['SL']} पॉइंट्स\n"
                    f"T1 ला: सुमारे +{premium_moves['T1']} पॉइंट्स\n"
                    f"T2 ला: सुमारे +{premium_moves['T2']} पॉइंट्स\n"
                    f"T3 ला: सुमारे +{premium_moves['T3']} पॉइंट्स\n"
                    f"⚠️ हा फक्त अंदाज आहे (live data उपलब्ध नाही), actual प्रीमियम वेगळा असू शकतो\n\n"
                )

            confirmation_text = (
                f"✅ Confirmation: ORB Breakout (High: {s['or_high']}) | RSI {round(latest_rsi,1)}\n\n"
                if STRATEGY_MODE == "ORB" else
                f"✅ Confirmation: RSI {round(latest_rsi,1)} | EMA9 > EMA21 (Uptrend) | ADX {round(latest_adx,1)} (Strong Trend)\n\n"
            )
            send_telegram_message(
                f"🟢 **{display_name} BUY CALL SIGNAL**\n\n"
                f"👉 **ACTION: BUY {strikes['ATM']}** 👈\n\n"
                f"Entry Price: {latest_price}\nInitial SL: {s['stop_loss']}\n\n"
                f"{confirmation_text}"
                f"🎯 Targets (Spot):\nT1: {targets['T1']}\nT2: {targets['T2']}\nT3: {targets['T3']}\n\n"
                f"{premium_line}"
                f"📌 इतर Strike Options:\n"
                f"ITM: {strikes['ITM']}\n"
                f"OTM: {strikes['OTM']}"
            )
            chart_path = generate_signal_chart(df, 'BUY', latest_price, s["stop_loss"], symbol_key)
            if chart_path:
                send_telegram_chart(chart_path, f"{display_name} BUY CALL | Entry: {latest_price} | SL: {s['stop_loss']} | ATM: {strikes['ATM']}")
        elif (
            (STRATEGY_MODE == "TREND" and prev_dir == 1 and curr_dir == -1 and sell_confirmed)
            or (STRATEGY_MODE == "ORB" and orb_sell_confirmed)
        ):
            s["current_trade"] = 'SELL'
            s["entry_price"] = latest_price
            s["stop_loss"] = min(s["or_high"], latest_price + MAX_INITIAL_SL_POINTS) if (STRATEGY_MODE == "ORB" and s["or_high"]) else latest_price + 15
            s["trade_date"] = today_str
            strikes = get_option_strikes(latest_price, 'SELL', strike_step)
            targets = get_targets(latest_price, s["stop_loss"], 'SELL')
            premium_moves = get_estimated_premium_moves(latest_price, s["stop_loss"], targets)
            s["atm_strike"] = strikes['ATM']
            s["targets"] = targets

            atm_strike_num = round(latest_price / strike_step) * strike_step
            real_premium = try_get_real_premium(symbol_key, atm_strike_num, 'PE')
            s["entry_spot"] = latest_price
            s["option_type"] = 'PE'
            s["base_premium"] = real_premium
            if real_premium is not None:
                premium_line = f"💰 **Live Premium: ₹{real_premium}** (Angel One वरून)\n\n"
            else:
                premium_line = (
                    f"📊 अंदाजे Premium Movement (ATM, Delta~0.5):\n"
                    f"SL लागल्यास: सुमारे -{premium_moves['SL']} पॉइंट्स\n"
                    f"T1 ला: सुमारे +{premium_moves['T1']} पॉइंट्स\n"
                    f"T2 ला: सुमारे +{premium_moves['T2']} पॉइंट्स\n"
                    f"T3 ला: सुमारे +{premium_moves['T3']} पॉइंट्स\n"
                    f"⚠️ हा फक्त अंदाज आहे (live data उपलब्ध नाही), actual प्रीमियम वेगळा असू शकतो\n\n"
                )

            sell_confirmation_text = (
                f"✅ Confirmation: ORB Breakdown (Low: {s['or_low']}) | RSI {round(latest_rsi,1)}\n\n"
                if STRATEGY_MODE == "ORB" else
                f"✅ Confirmation: RSI {round(latest_rsi,1)} | EMA9 < EMA21 (Downtrend) | ADX {round(latest_adx,1)} (Strong Trend)\n\n"
            )
            send_telegram_message(
                f"🔴 **{display_name} BUY PUT SIGNAL**\n\n"
                f"👉 **ACTION: BUY {strikes['ATM']}** 👈\n\n"
                f"Entry Price: {latest_price}\nInitial SL: {s['stop_loss']}\n\n"
                f"{sell_confirmation_text}"
                f"🎯 Targets (Spot):\nT1: {targets['T1']}\nT2: {targets['T2']}\nT3: {targets['T3']}\n\n"
                f"{premium_line}"
                f"📌 इतर Strike Options:\n"
                f"ITM: {strikes['ITM']}\n"
                f"OTM: {strikes['OTM']}"
            )
            chart_path = generate_signal_chart(df, 'SELL', latest_price, s["stop_loss"], symbol_key)
            if chart_path:
                send_telegram_chart(chart_path, f"{display_name} BUY PUT | Entry: {latest_price} | SL: {s['stop_loss']} | ATM: {strikes['ATM']}")


def check_signals():
    global last_gm_date, last_error_msg, last_error_date, last_daily_summary_date
    now = datetime.now(IST)
    today_str = now.strftime('%Y-%m-%d')
    current_time_str = now.strftime('%H:%M')
    weekday = now.weekday()  # 0=Monday ... 5=Saturday, 6=Sunday

    # Weekend kiva market vel sodun baki veli kahich karaycha nahi
    if weekday >= 5 or current_time_str < "09:00" or current_time_str > "15:35":
        return

    if current_time_str >= "09:00" and current_time_str < "09:15" and last_gm_date != today_str:
        send_telegram_message("Good Morning! Nifty & Bank Nifty Trading Bot आता सक्रिय (Active) झाला आहे.")
        last_gm_date = today_str

    for symbol_key in SYMBOLS:
        try:
            check_signals_for_symbol(symbol_key, now, today_str, current_time_str)
        except Exception as e:
            print(f"Error in check_signals for {symbol_key}: {e}")
            err_text = f"{symbol_key}: {e}"
            if last_error_msg != err_text or last_error_date != today_str:
                send_telegram_message(f"⚠️ Bot Error ({symbol_key}): {e}")
                last_error_msg, last_error_date = err_text, today_str

    # 3:30 nantar (sagle square-off zalyavar) ekach vela combined daily summary pathavto
    if current_time_str >= "15:30" and last_daily_summary_date != today_str:
        total_pnl = get_today_total_pnl(today_str)
        summary_lines = [f"🔔 **DAY END SUMMARY** ({today_str})\n"]
        for symbol_key in SYMBOLS:
            summary_lines.append(calculate_reports(symbol_key))
            summary_lines.append("")
        summary_lines.append(f"💰 **एकूण आजचा नफा/तोटा (दोन्ही मिळून): ₹{round(total_pnl, 2)}**")
        send_telegram_message("\n".join(summary_lines))
        last_daily_summary_date = today_str


@app.route('/')
def home():
    print("Cron-job ping received. Keeping server alive!")
    check_signals()
    return "Bot is running perfectly! Tata Bot is Active.", 200


@app.route('/test-broker')
def test_broker():
    """
    Shell access nasel (free plan var) tar hya URL var browser madhe javun
    Angel One connection test karता येते. Result Telegram var pathavla jato,
    ani browser var pan dakhavla jato.
    """
    if not BROKER_AVAILABLE:
        msg = "❌ broker.py load zala nahi (package install issue असू शकतो)."
        send_telegram_message(msg)
        return msg, 200

    try:
        session = broker.get_smart_api_session()
        if session:
            msg = "✅ Angel One session यशस्वी झाले! Connection working ahe."
        else:
            detail = broker.get_last_error() or "unknown error"
            msg = f"❌ Angel One session fail zala.\nकारण: {detail}"
        send_telegram_message(msg)
        return msg, 200
    except Exception as e:
        err_msg = f"❌ Broker test error: {e}"
        send_telegram_message(err_msg)
        return err_msg, 200


@app.route('/run-backtest')
def run_backtest_route():
    """
    Shell shivayही browser madhun backtest run karण्यasathi. Result Telegram
    var pathavla jato (magche 60 divasach - yfinance cha limit ahe).
    Data download + calculation la thoda vel (30-60 sec) lagू shakto.
    """
    try:
        import backtest as bt
        send_telegram_message("⏳ Backtest suru zala, thoda vel lagel (data download + calculation)...")
        for symbol_key in bt.SYMBOLS:
            trades = bt.run_backtest(symbol_key)
            report = bt.format_report(symbol_key, trades)
            send_telegram_message(report)
        return "Backtest complete, results pathavले Telegram var.", 200
    except Exception as e:
        err_msg = f"❌ Backtest error: {e}"
        send_telegram_message(err_msg)
        return err_msg, 200


@app.route('/check-lot-sizes')
def check_lot_sizes_route():
    """
    Manually Angel One app madhe check karnyaऐवजी, Angel One cha scrip master
    (जो broker.py आधीच download kartoy) vaparun sagळ्या symbols cha ACTUAL
    current lot_size ani strike_step automatically kadhto - Telegram var pathavto.
    """
    if not BROKER_AVAILABLE:
        msg = "❌ broker.py load zala nahi."
        send_telegram_message(msg)
        return msg, 200

    session = broker.get_smart_api_session()
    if session is None:
        msg = f"❌ Angel One session nahi. कारण: {broker.get_last_error()}"
        send_telegram_message(msg)
        return msg, 200

    send_telegram_message("⏳ Scrip master download hotoy, thoda vel lagel...")
    lines = ["🔍 **LOT SIZE / STRIKE STEP CHECK** (Angel One scrip master वरून)\n"]
    for symbol_key, cfg in SYMBOLS.items():
        result = broker.auto_discover_lot_and_strikes(symbol_key)
        if result and result["lot_size"]:
            match_icon = "✅" if result["lot_size"] == cfg["lot_size"] else "⚠️ MISMATCH"
            lines.append(
                f"{symbol_key}: Actual lot={result['lot_size']} (code madhे: {cfg['lot_size']}) {match_icon} | "
                f"Strike step: {result['strike_step']} (code madhे: {cfg['strike_step']})"
            )
        else:
            lines.append(f"{symbol_key}: Scrip master madhe sapadla nahi (verify manually)")

    report = "\n".join(lines)
    send_telegram_message(report)
    return "Lot size check complete.", 200


@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    try:
        update = request.get_json()
        if not update or "message" not in update or "text" not in update["message"]:
            return "OK", 200

        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"].lower().strip()

        if text == "/start":
            reply_message = "😊 Tata Bot Shuru Jhala Aahe!\nNifty ani Bank Nifty donhi cha live signal sathi /price, /report ani /status commands vapra."
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": reply_message})

        elif text == "/price":
            lines = ["📈 **Live Market Price**"]
            for symbol_key, cfg in SYMBOLS.items():
                data = yf.download(tickers=cfg["ticker"], period="1d", interval="1m", progress=False)
                data = fix_multiindex(data)
                if not data.empty:
                    latest_price = round(data['Close'].iloc[-1], 2)
                    lines.append(f"{cfg['display']}: {latest_price}")
                else:
                    lines.append(f"{cfg['display']}: ❌ data available nahi")
            reply_message = "\n".join(lines)
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": reply_message})

        elif text == "/report":
            report_message = "\n\n".join(calculate_reports(sym) for sym in SYMBOLS)
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": report_message})

        elif text == "/status":
            lines = ["🔍 **BOT STATUS**"]
            for symbol_key, cfg in SYMBOLS.items():
                s = state[symbol_key]
                dir_text = "माहीत नाही"
                if s["last_status_dir"] == 1:
                    dir_text = "🟢 UPTREND"
                elif s["last_status_dir"] == -1:
                    dir_text = "🔴 DOWNTREND"
                trade_text = s["current_trade"] if s["current_trade"] else "कोणताही ट्रेड ओपन नाही"
                lines.append(
                    f"\n**{cfg['display']}**\n"
                    f"⏱️ शेवटचा चेक: {s['last_status_time'] or 'अजून चेक झालेला नाही'}\n"
                    f"💹 शेवटची किंमत: {s['last_status_price'] or 'N/A'}\n"
                    f"📈 सध्याचा ट्रेंड: {dir_text}\n"
                    f"📌 सध्याचा ट्रेड: {trade_text}\n"
                    f"📐 RSI: {s['last_rsi'] or 'N/A'} | ADX: {s['last_adx'] or 'N/A'}"
                )
            if last_error_msg:
                lines.append(f"\n⚠️ शेवटची एरर: {last_error_msg}")

            status_message = "\n".join(lines)
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": status_message})

        return "OK", 200
    except Exception as e:
        print(f"Error: {e}")
        return "Error", 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
