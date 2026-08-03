
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

# Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# ट्रेडिंग ट्रॅकिंग आणि मॉर्निंग स्टेटस फ्लॅग्ज
current_trade = None  
entry_price = 0.0
stop_loss = 0.0
daily_trades = []

# दररोज फक्त एकदाच मॉर्निंग मेसेज जाण्यासाठी ट्रॅकर्स
last_gm_date = ""
last_levels_date = ""

def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID: return
    url = f"https://telegram.org{BOT_TOKEN}/sendMessage"
    try: requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
    except Exception as e: print(f"Error sending message: {e}")

def send_telegram_chart(image_path, caption_text):
    if not BOT_TOKEN or not CHAT_ID: return
    url = f"https://telegram.org{BOT_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as photo:
        files = {'photo': photo}
        data = {'chat_id': CHAT_ID, 'caption': caption_text}
        try: requests.post(url, files=files, data=data, timeout=15)
        except Exception as e: print(f"Error sending chart: {e}")

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
    except Exception as e: print(f"Error in get_levels: {e}")
    return None, None, None

def calculate_reports():
    if not daily_trades: return "अजून कोणताही ट्रेड पूर्ण झालेला नाही."
    today_str = datetime.today().strftime('%Y-%m-%d')
    today_pnl = sum(t['pnl'] for t in daily_trades if t['date'] == today_str)
    total_pnl = sum(t['pnl'] for t in daily_trades)
    total_trades = len(daily_trades)
    weekly_avg = total_pnl / total_trades if total_trades > 0 else 0
    return (
        f"📊 **PERFORMANCE REPORT** 📊\n\n"
        f"📅 आजचा एकूण नफा/तोटा: ₹{round(today_pnl, 2)}\n"
        f"🔢 एकूण झालेले ट्रेड्स: {total_trades}\n"
        f"📈 चालू आठवड्याचा सरासरी नफा: ₹{round(weekly_avg, 2)} प्रति ट्रेड\n"
    )

# 🔔 टेलिग्राम मेसेजला उत्तर देणारा रस्ता (Webhook)
@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    update = request.get_json()
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "").lower().strip()
        
        if text == "/start" or text == "hi" or text == "hello":
            msg = "🟢 Nifty Trading Bot मध्ये आपले स्वागत आहे!\n\nहा बोट लाईव्ह配置 मार्केटमध्ये ऑटोमॅटिक सिग्नल्स आणि कॅन्डलस्टिक चार्ट पाठवेल.\n\n📊 निफ्टीची सध्याची किंमत पाहण्यासाठी **price** टाईप करा."
            requests.post(f"https://telegram.org{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": msg})
            
        elif text == "/price" or text == "price":
            try:
                ticker = yf.Ticker("^NSEI")
                todays_data = ticker.history(period='1d')
                if not todays_data.empty:
                    latest_price = round(todays_data['Close'].iloc[-1], 2)
                    msg = f"📊 **NIFTY 50 Live Price**\n\n💰 सध्याची किंमत: ₹{latest_price}\n🕒 वेळ: {datetime.now().strftime('%H:%M:%S')}\n\n*(टीप: मार्केट बंद असल्यास ही शेवटची बंद झालेली किंमत असेल)*"
                else:
                    msg = "❌ सध्या लाईव्ह डेटा उपलब्ध नाही. मार्केट उघडल्यावर पुन्हा प्रयत्न करा."
            except Exception as e: msg = f"❌ किंमत काढताना अडचण आली."
            requests.post(f"https://telegram.org{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": msg})
            
    return "OK", 200

# 🕒 दर ५ मिनिटांनी चालणारे मुख्य इंजिन (Cron Endpoint)
@app.route('/run-bot-cron')
def check_signals():
    global current_trade, entry_price, stop_loss, daily_trades, last_gm_date, last_levels_date
    try:
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        current_time_str = now.strftime('%H:%M')

        # 🌅 १. सकाळी ०९:०० चा Good Morning मेसेज लॉजिक
        if current_time_str >= "09:00" and current_time_str < "09:10" and last_gm_date != today_str:
            send_telegram_message("🌅 Good Morning!\nNifty Trading Bot आता सक्रिय (Active) झाला आहे आणि आजच्या मार्केटवर लक्ष ठेवण्यास तयार आहे! 👍")
            last_gm_date = today_str

        # 📊 २. सकाळी ०९:१४ चा प्री-मार्केट सपोर्ट/रेझिस्टन्स मेसेज लॉजिक
        s1, r1, pivot = get_levels()
        if current_time_str >= "09:10" and current_time_str < "09:20" and last_levels_date != today_str:
            if s1 and r1:
                levels_msg = (
                    f"📊 **NIFTY 50 DAILY LEVELS** 📊\n"
                    f"📅 दिनांक: {today_str}\n\n"
                    f"🚀 मार्केट सुरू होण्यापूर्वीच्या महत्त्वाच्या लेव्हल्स:\n"
                    f"📈 Resistance (R1): {r1}\n"
                    f"🎯 Pivot Point: {pivot}\n"
                    f"📉 Support (S1): {s1}\n\n"
                    f"💡 (टीप: हे आकडे मागील दिवसाच्या डेटावरून काढले आहेत. मार्केट ९:१५ ला सुरू होईल.)"
                )
                send_telegram_message(levels_msg)
                last_levels_date = today_str

        # ३. मुख्य ट्रेडिंग सिग्नल्स चेकिंग
        df = yf.download(tickers="^NSEI", period="5d", interval="5m", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty or len(df) < 20: return "Not enough data", 200

        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=7, multiplier=3)
        df['ST'] = st['SUPERT_7_3.0']
        df['ST_DIR'] = st['SUPERTD_7_3.0']

        latest_price = round(df['Close'].iloc[-1], 2)
        prev_dir = df['ST_DIR'].iloc[-2]
        curr_dir = df['ST_DIR'].iloc[-1]
        pnl_generated = 0.0
        trade_closed = False

        if current_trade == 'BUY':
            new_sl = latest_price - 10
            if new_sl > stop_loss: stop_loss = new_sl
            if latest_price <= stop_loss or curr_dir == -1:
                pnl_generated = (latest_price - entry_price) * 50
                trade_closed = True
                send_telegram_message(f"❌ EXIT CALL ALERT\nPrice: {latest_price}\nट्रेड PnL: ₹{round(pnl_generated, 2)}")
        elif current_trade == 'SELL':
            new_sl = latest_price + 10
            if stop_loss == 0 or new_sl < stop_loss: stop_loss = new_sl
            if latest_price >= stop_loss or curr_dir == 1:
                pnl_generated = (entry_price - latest_price) * 50
                trade_closed = True
                send_telegram_message(f"❌ EXIT PUT ALERT\nPrice: {latest_price}\nट्रेड PnL: ₹{round(pnl_generated, 2)}")

        if trade_closed:
            daily_trades.append({'date': today_str, 'pnl': pnl_generated})
            current_trade = None
            send_telegram_message(calculate_reports())

        if current_trade is None:
            signal_type = None
            if prev_dir == -1 and curr_dir == 1:
                current_trade = 'BUY'
                entry_price = latest_price
                stop_loss = latest_price - 10
                signal_type = "🟢 BUY CALL SIGNAL"
            elif prev_dir == 1 and curr_dir == -1:
                current_trade = 'SELL'
                entry_price = latest_price
                stop_loss = latest_price + 10
                signal_type = "🔴 BUY PUT SIGNAL"

            if signal_type and s1 and r1:
                plot_df = df.tail(30).copy()
                arrows = np.full(len(plot_df), np.nan)
                if current_trade == 'BUY':
                    arrows[-1] = plot_df['Low'].iloc[-1] - 5
                    arrow_marker = '^'; arrow_color = 'green'
                else:
                    arrows[-1] = plot_df['High'].iloc[-1] + 5
                    arrow_marker = 'v'; arrow_color = 'red'

                additional_plots = [
                    mpf.make_addplot([r1]*len(plot_df), color='blue', linestyle='--', width=1.2),
                    mpf.make_addplot([s1]*len(plot_df), color='orange', linestyle='--', width=1.2),
                    mpf.make_addplot(arrows, type='scatter', markersize=100, marker=arrow_marker, color=arrow_color)
                ]
                custom_style = mpf.make_mpf_style(base_mpf_style='charles', gridstyle=':', y_on_right=False)
                image_path = "chart.png"
                mpf.plot(plot_df, type='candle', style=custom_style, addplot=additional_plots, savefig=image_path, title=f"Nifty {signal_type}", volume=False)
                
                caption = f"{signal_type}\n📊 Entry Price: {entry_price}\n🛡️ Auto Trailing SL: {stop_loss}\n📉 S1: {s1} | 📈 R1: {r1}"
                send_telegram_chart(image_path, caption)

    except Exception as e: print(f"Error in check_signals: {e}")
    return "Bot checked signals successfully", 200

@app.route('/')
def home(): return "Bot is running perfectly!"

if __name__ == "__main__":
    try:
        send_telegram_message("🤖 टाटा बॉट सुरू झाला आहे! 🚀\nमार्केट सिग्नल्स मॉनिटर करणे सुरू केले आहे...")
    except Exception as e:
        print(f"Error sending welcome message: {e}")
        port = int(os.environ.get("PORT", 10000))
        app.run(host='0.0.0.0', port=port)
 
