import os
import requests
import pandas as pd
import pandas_ta as ta
import mplfinance as mpf
from flask import Flask, request
import yfinance as yf
from datetime import datetime
import numpy as np

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

current_trade = None
entry_price = 0.0
stop_loss = 0.0
daily_trades = []

last_gm_date = ""
last_levels_date = ""

def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID: return
    url = f"https://telegram.org{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")

def send_telegram_chart(image_path, caption_text):
    if not BOT_TOKEN or not CHAT_ID: return
    url = f"https://telegram.org{BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': CHAT_ID, 'caption': caption_text}
            requests.post(url, files=files, data=data, timeout=15)
    except Exception as e:
        print(f"Error sending chart: {e}")

def get_levels():
    try:
        df = yf.download(tickers="^NSEI", period="2d", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if len(df) >= 2:
            prev_day = df.iloc[-2]
            pivot = (prev_day['High'] + prev_day['Low'] + prev_day['Close']) / 3
            r1 = (2 * pivot) - prev_day['Low']
            s1 = (2 * pivot) - prev_day['High']
            return round(s1, 2), round(r1, 2), round(pivot, 2)
    except Exception as e:
        print(f"Error in get_levels: {e}")
    return None, None, None

def calculate_reports():
    if not daily_trades:
        return "अजून कोणताही ट्रेड पूर्ण झालेला नाही."
    today_str = datetime.today().strftime('%Y-%m-%d')
    today_pnl = sum(t['pnl'] for t in daily_trades if t['date'] == today_str)
    total_pnl = sum(t['pnl'] for t in daily_trades)
    total_trades = len(daily_trades)
    weekly_avg = total_pnl / total_trades if total_trades > 0 else 0
    
    return (
        f"📊 **PERFORMANCE REPORT** 📊\n\n"
        f"💰 आजचा एकूण नफा/तोटा: ₹{round(today_pnl, 2)}\n"
        f"📈 एकूण झालेले ट्रेड्स: {total_trades}\n"
        f"🔄 चालू आठवड्याचा सरासरी नफा: ₹{round(weekly_avg, 2)}"
    )

def check_signals():
    global current_trade, entry_price, stop_loss, daily_trades, last_gm_date, last_levels_date
    try:
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        current_time_str = now.strftime('%H:%M')
        
        if current_time_str >= "09:00" and current_time_str < "09:15" and last_gm_date != today_str:
            send_telegram_message("Good Morning! Nifty Trading Bot आता सक्रिय (Active) झाला आहे.")
            last_gm_date = today_str
            
        if current_time_str >= "09:10" and current_time_str < "09:25" and last_levels_date != today_str:
            s1, r1, pivot = get_levels()
            if s1 and r1:
                levels_msg = (
                    f"📊 **NIFTY DAILY LEVELS** 📊\n"
                    f"📅 दिनांक: {today_str}\n"
                    f"🚀 Resistance (R1): {r1}\n"
                    f"🎯 Pivot Point: {pivot}\n"
                    f"📉 Support (S1): {s1}"
                )
                send_telegram_message(levels_msg)
                last_levels_date = today_str
                
        df = yf.download(tickers="^NSEI", period="5d", interval="5m", progress=False)
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
        trade_closed = False
        
        if current_trade == 'BUY':
            new_sl = latest_price - 10
            if new_sl > stop_loss:
                stop_loss = round(new_sl, 2)
                send_telegram_message(f"🔄 Stop Loss ट्रेल झाला! नवीन SL: {stop_loss}")
            if latest_price <= stop_loss:
                pnl_generated = (latest_price - entry_price) * 50
                send_telegram_message(f"🚨 BUY EXIT! SL Hit\nExit Price: {latest_price}\nP&L: ₹{pnl_generated}")
                trade_closed = True
                
        elif current_trade == 'SELL':
            new_sl = latest_price + 10
            if stop_loss == 0.0 or new_sl < stop_loss:
                stop_loss = round(new_sl, 2)
                send_telegram_message(f"🔄 Stop Loss ट्रेल झाला! नवीन SL: {stop_loss}")
            if latest_price >= stop_loss:
                pnl_generated = (entry_price - latest_price) * 50
                send_telegram_message(f"🚨 SELL EXIT! SL Hit\nExit Price: {latest_price}\nP&L: ₹{pnl_generated}")
                trade_closed = True
                
        if trade_closed:
            daily_trades.append({'date': today_str, 'pnl': pnl_generated})
            current_trade = None
            send_telegram_message(calculate_reports())
            
        if current_trade is None:
            if prev_dir == -1 and curr_dir == 1:
                current_trade = 'BUY'
                entry_price = latest_price
                stop_loss = entry_price - 15
                send_telegram_message(f"🚀 **BUY CALL SIGNAL**\nEntry Price: {entry_price}\nInitial SL: {stop_loss}")
            elif prev_dir == 1 and curr_dir == -1:
                current_trade = 'SELL'
                entry_price = latest_price
                stop_loss = entry_price + 15
                send_telegram_message(f"📉 **BUY PUT SIGNAL**\nEntry Price: {entry_price}\nInitial SL: {stop_loss}")
                
    except Exception as e:
        print(f"Error in check_signals: {e}")

@app.route('/')
def home():
    print("Cron-job ping received. Keeping server alive!")
    check_signals()
    return "Bot is running perfectly! Tata Bot is Active.", 200

@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    try:
        update = request.get_json()
        if update and "message" in update and "text" in update["message"]:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"]["text"].lower().strip()
            
            if text == "/start":
                reply_message = "😊 Tata Bot Shuru Jhala Aahe! \nLive market signals, /price ani /report sathi ha bot tayar ahe."
                requests.post(f"https://telegram.org{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": reply_message})
                
            elif text == "/price":
                data = yf.download(tickers="^NSEI", period="1d", interval="1m", progress=False)
                if not data.empty:
                    latest_price = round(data['Close'].iloc[-1], 2)
                    reply_message = f"📈 Live Market Price: **InNifty 50: {latest_price}**"
                else:
                    reply_message = "❌ Sadhya market data available nahi."
                requests.post(f"https://telegram.org{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": reply_message})
                
            elif text == "/report":
                report_message = calculate_reports()
                requests.post(f"https://telegram.org{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": report_message})
                
        return "OK", 200
    except Exception as e:
        print(f"Error: {e}")
        return "Error", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
