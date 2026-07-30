from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=10000)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.start()

    while True:
        schedule.run_pending()
        time.sleep(1)
import os
import time
import requests
import pandas as pd

import yfinance as yf
import schedule
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Updated Bot Token and Chat ID
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8931528579:AAGyObQKqUUPnQ5jO3oxMB7EF0zvfK7Lzno")
CHAT_ID = os.environ.get("CHAT_ID", "5685619801")

current_trade = None

def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

def send_telegram_photo(photo_path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, 'rb') as photo:
            payload = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
            files = {"photo": photo}
            requests.post(url, data=payload, files=files)
    except Exception as e:
        print(f"Error sending photo: {e}")

def generate_chart_image(df, signal_type, s1, r1):
    file_path = "chart.png"
    plt.figure(figsize=(10, 6))
    recent_df = df.tail(35)
    plt.plot(recent_df.index, recent_df['Close'], label='Nifty 5m Price', color='#1f77b4', linewidth=2)
    plt.plot(recent_df.index, recent_df['ST'], label='Supertrend (7,3)', color='#ff7f0e', linestyle='--', linewidth=1.5)
    plt.axhline(y=s1, color='green', linestyle=':', label=f'Support (S1): {s1}')
    plt.axhline(y=r1, color='red', linestyle=':', label=f'Resistance (R1): {r1}')
    plt.title(f"📊 NIFTY 5M CHART - {signal_type} SIGNAL", fontsize=12, fontweight='bold')
    plt.xlabel("Time")
    plt.ylabel("Nifty Spot Price")
    plt.legend(loc='upper left')
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.savefig(file_path, dpi=150)
    plt.close()
    return file_path

def get_levels():
    df = yf.download(tickers='^NSEI', period='2d', interval='1d', progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    prev_day = df.iloc[-2]
    high, low, close = prev_day['High'], prev_day['Low'], prev_day['Close']
    pivot = (high + low + close) / 3
    r1 = (2 * pivot) - low
    s1 = (2 * pivot) - high
    return round(s1, 2), round(r1, 2), round(pivot, 2)

def send_morning_levels():
    try:
        s1, r1, pivot = get_levels()
        msg = (
            f"🌅 *GOOD MORNING! TODAY'S NIFTY SR LEVELS*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *Pivot Point:* `{pivot}`\n"
            f"🟢 *Strong Support (S1):* `{s1}`\n"
            f"🔴 *Strong Resistance (R1):* `{r1}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 *Supertrend Algo Strategy Active!*"
        )
        send_telegram_msg(msg)
    except Exception as e:
        print(f"Error: {e}")

def check_signals():
    global current_trade
    try:
        df = yf.download(tickers='^NSEI', period='5d', interval='5m', progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        if df.empty or len(df) < 20:
            return

        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=7, multiplier=3)
        df['ST'] = st['SUPERT_7_3.0']
        df['ST_DIR'] = st['SUPERTd_7_3.0']

        latest_price = round(df['Close'].iloc[-1], 2)
        prev_dir = df['ST_DIR'].iloc[-2]
        curr_dir = df['ST_DIR'].iloc[-1]
        
        s1, r1, pivot = get_levels()

        if current_trade is not None:
            trade_type = current_trade['type']
            entry, sl, t1, t2, t3 = current_trade['entry'], current_trade['sl'], current_trade['t1'], current_trade['t2'], current_trade['t3']

            if not current_trade['t1_hit']:
                if (trade_type == 'CE' and latest_price >= t1) or (trade_type == 'PE' and latest_price <= t1):
                    current_trade['t1_hit'] = True
                    current_trade['sl'] = entry
                    send_telegram_msg(f"🎯 *TARGET 1 ACHIEVED (1:2)* 🎯\n\nPrice: `{latest_price}`\n🔄 *Trailing SL moved to Entry:* `{entry}`")

            elif not current_trade['t2_hit']:
                if (trade_type == 'CE' and latest_price >= t2) or (trade_type == 'PE' and latest_price <= t2):
                    current_trade['t2_hit'] = True
                    current_trade['sl'] = t1
                    send_telegram_msg(f"🚀 *TARGET 2 ACHIEVED (1:3)* 🚀\n\nPrice: `{latest_price}`\n🔄 *Trailing SL moved to T1:* `{t1}`")

            elif (trade_type == 'CE' and latest_price >= t3) or (trade_type == 'PE' and latest_price <= t3):
                send_telegram_msg(f"🏆 *TARGET 3 ACHIEVED (1:4) - FULL EXIT!* 🏆\n\nPrice: `{latest_price}`")
                current_trade = None
                return

            if (trade_type == 'CE' and latest_price <= current_trade['sl']) or (trade_type == 'PE' and latest_price >= current_trade['sl']):
                reason = "Trailing SL Hit" if current_trade['t1_hit'] else "Stop Loss Hit"
                send_telegram_msg(f"🛑 *{reason}!* 🛑\n\nExit Price: `{latest_price}`")
                current_trade = None
                return

        if current_trade is None:
            risk = 10

            if prev_dir == -1 and curr_dir == 1:
                sl = latest_price - risk
                t1, t2, t3 = latest_price + (risk*2), latest_price + (risk*3), latest_price + (risk*4)
                current_trade = {'type': 'CE', 'entry': latest_price, 'sl': sl, 't1': t1, 't2': t2, 't3': t3, 't1_hit': False, 't2_hit': False}

msg = "🟢 BUY CALL SIGNAL | Entry: " + str(latest_price) + " | SL: " + str(sl) + " | Target: " + str(t1) + " | Trailing SL: Active"

 

      chart_path = generate_chart_image(df, "BUY CALL", s1, r1)
                send_telegram_photo(chart_path, msg)

            elif prev_dir == 1 and curr_dir == -1:
                sl = latest_price + risk
                t1, t2, t3 = latest_price - (risk*2), latest_price - (risk*3), latest_price - (risk*4)
                current_trade = {'type': 'PE', 'entry': latest_price, 'sl': sl, 't1': t1, 't2': t2, 't3': t3, 't1_hit': False, 't2_hit': False}

 msg = f""'🔴 *BUY PUT (PE) SIGNAL* ⬇️⬇️\n"
       f ━━━━━━━━━━━━━━━━━━━━━━                  f📍 *Resistance Level Marked:* `{r1}`\         f📊 *Nifty Entry Price:* `{latest_price}`\n\n"
f 🛑 *Stop Loss:* `{sl}` (+10 pts)\n"
f 🎯 *Target 1 (1:2):* `{t1}` (-20 pts)\n"
f 🎯 *Target 2 (1:3):* `{t2}` (-30 pts)\n"
f 🎯 *Target 3 (1:4):* `{t3}` (-40 pts)\n\n"
f ⚡ *Trailing SL:* Auto-Active on T1"""
# ==========================================
# टेलिग्राम /price कमांडसाठी नवीन कोड (एकदम शेवटी टाका)
# ==========================================

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if update and "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        
        # जर तुम्ही टेलिग्रामवर /price टाइप केले तर
        if text.lower() == '/price':
            try:
                # yfinance कडून निफ्टीची लेटेस्ट प्राईस काढणे
                nifty_data = yf.Ticker("^NSEI")
                todays_data = nifty_data.history(period='1d', interval='1m')
                current_price = todays_data['Close'].iloc[-1]
                
                message = f"🟢 Bot is Active & Running!\n📊 Current Nifty Price: {current_price:.2f}"
            except Exception as e:
                message = f"🟢 Bot is Active, but error fetching price: {str(e)}"
            
            # टेलिग्रामवर मेसेज पाठवणे
            send_telegram_message(chat_id, message)
            
    

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def send_telegram_message(chat_id, text):
    TOKEN = "8931528579:AAGyObQKqUUPnQ5jO3oxMB7EF0zvfK7Lzno"
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)
import requests

@app.route('/set-webhook')
def set_webhook():
    TOKEN = "8931528579:AAGyObQKqUUPnQ5j03oxMB7EF0zvfK7Lzno"
    WEBHOOK_URL = "https://nifty-bot-3ega.onrender.com/telegram-webhook"
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={WEBHOOK_URL}"
    response = requests.get(url)
    return response.json()

