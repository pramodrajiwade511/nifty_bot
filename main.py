import os
import requests
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from flask import Flask

app = Flask(__name__)

# Telegram settings (Render वरील Environment Variables मधून येतील)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

current_trade = None

def send_telegram_message(message):
    """Telegram वर मेसेज पाठवण्यासाठी फंक्शन"""
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram config missing: BOT_TOKEN or CHAT_ID not set.")
        return
    url = f"https://telegram.org{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send telegram message: {e}")

@app.route('/')
def home():
    """Render ची सर्व्हर लिंक जिवंत ठेवण्यासाठी होम रूट"""
    return "Bot is running perfectly!"

def get_levels():
    """पिव्होट आणि S1/R1 लेव्हल्स काढण्यासाठी फंक्शन"""
    try:
        df = yf.download(tickers='^NSEI', period='2d', interval='1d', progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if len(df) >= 2:
            prev_day = df.iloc[-2]
            high = prev_day['High']
            low = prev_day['Low']
            close = prev_day['Close']
            
            pivot = (high + low + close) / 3
            r1 = (2 * pivot) - low
            s1 = (2 * pivot) - high
            return round(s1, 2), round(r1, 2), round(pivot, 2)
    except Exception as e:
        print(f"Error in get_levels: {e}")
    return None, None, None

def check_signals():
    """सुपरट्रेंड सिग्नल्स आणि ट्रेडिंग लॉजिक तपासण्यासाठी फंक्शन"""
    try:
        global current_trade
        df = yf.download(tickers='^NSEI', period='5d', interval='5m', progress=False)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        if df.empty or len(df) < 20:
            return

        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=7, multiplier=3)
        df['ST'] = st['SUPERT_7_3_0']
        df['ST_DIR'] = st['SUPERTD_7_3_0']

        latest_price = round(df['Close'].iloc[-1], 2)
        prev_dir = df['ST_DIR'].iloc[-2]
        curr_dir = df['ST_DIR'].iloc[-1]

        s1, r1, pivot = get_levels()
    except Exception as e:
        print(f"Error in check_signals: {e}")
        return

    # जर आधीपासून ट्रेड चालू असेल तर तो क्लोज (Exit) करण्याचे लॉजिक
    if current_trade is not None:
        trade_type = current_trade['type']
        
        if trade_type == 'BUY' and (curr_dir == -1 or latest_price >= r1):
            send_telegram_message(f"🚨 EXIT BUY: Price {latest_price} (Target or Signal Change)")
            current_trade = None
        elif trade_type == 'SELL' and (curr_dir == 1 or latest_price <= s1):
            send_telegram_message(f"🚨 EXIT SELL: Price {latest_price} (Target or Signal Change)")
            current_trade = None
            
    # जर कोणताही ट्रेड चालू नसेल तर नवीन एंट्री (Entry) घेण्याचे लॉजिक
    else:
        if prev_dir == -1 and curr_dir == 1:
            send_telegram_message(f"🟢🟢 BUY SIGNAL: Entry Price {latest_price} | Target R1: {r1}")
            current_trade = {'type': 'BUY', 'entry_price': latest_price}
        elif prev_dir == 1 and curr_dir == -1:
            send_telegram_message(f"🔴🔴 SELL SIGNAL: Entry Price {latest_price} | Target S1: {s1}")
            current_trade = {'type': 'SELL', 'entry_price': latest_price}

@app.route('/run-bot')
def run_bot_cron():
    """Cron Job द्वारे बॉट दर ५ मिनिटांनी रन करण्यासाठी रूट"""
    check_signals()
    return "Bot check completed!"

if __name__ == "__main__":
    # Render साठी पोर्ट ऑटो-कॉन्फिगरेशन
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
