"""
MAIN BOT SERVER - FINAL BUILT-IN UI EDITION
==================================================
Ha server TradingView che signals catch करतो, templates/ मधून 
तिन्ही मुख्य UI स्क्रीन्स (Login, Broker, Dashboard) दाखवतो, 
10-divasacha safety lock check karto, ani trailing logic chalavto.
"""

import os
import hashlib
import threading
import time
from datetime import datetime
# Flask चा render_template शब्द सुरक्षितपणे जोडला आहे
from flask import Flask, json, request, render_template
import requests

# broker.py madhun functions ani WebSocket data import karne
from broker import place_order, get_option_premium, init_nse_stream, NSE_LIVE_LTP

app = Flask(__name__)

# Render cha variables madhun Telegram details ghene
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 📊 सिम्युलेटेड डेटाबेस (10-Divasacha Safety Lock ani 4-Anki PIN Record)
user_database = {
    "user_01": {
        "user_name": "योगेश",
        "broker_name": "ANGEL_ONE",
        "account_status": "PAPER_LOCK",             # Suruvatila mandatory paper trade lock
        "strategy_updated_at": datetime.now(),      # Aaj navin strategy set zaali asa record
        "security_pin_hash": hashlib.sha256("1234".encode()).hexdigest() # Default 4-Anki pin '1234'
    }
}

# 📢 Telegram var SMS alert pathavne
def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram details missing in environment variables.")
        return
    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

# ==================================================================
# 📱 APP FRONTEND ROUTES (ॲपचे स्क्रीन्स दाखवणारे रस्ते - नवीन अपडेट)
# ==================================================================

# १. ॲप उघडल्यावर सर्वात आधी सुंदर डार्क लॉगिन स्क्रीन दिसण्यासाठी
@app.route('/')
def login_page():
    return render_template('login.html')

# २. लॉगिन यशस्वी झाल्यावर ब्रोकर खाते जोडण्याचा स्क्रीन दिसण्यासाठी
@app.route('/connect-broker')
def broker_page():
    return render_template('broker.html')

# ३. 📊 लाईव्ह नफा-तोटा काउंटर आणि प्रोग्रेस बार पाहण्यासाठी
@app.route('/dashboard')
def dashboard_page():
    return render_template('dashboard.html')

# ==================================================================
# 🔒 4-ANKI PIN VERIFICATION & LIVE ACTIVATION ROUTE
# ==================================================================
@app.route('/activate-live', methods=['POST'])
def activate_live():
    data = request.json
    user_id = data.get("user_id", "user_01")
    entered_pin = data.get("pin")
    user = user_database.get(user_id)

    if not user:
        return {"status": "error", "message": "User sapadla nahi!"}

    days_passed = (datetime.now() - user["strategy_updated_at"]).days
    if days_passed < 10:
        return {
            "status": "error", 
            "message": f"🔒 Ajun {10 - days_passed} दिवस paper trading karne mandatory ahe. Tya shivay live karta yenar nahi!"
        }

    entered_hash = hashlib.sha256(entered_pin.encode()).hexdigest()
    if entered_hash == user["security_pin_hash"]:
        user["account_status"] = "LIVE_ACTIVE"
        send_telegram_alert(f"🚀 *Live Mode Active!*\nUser *{user['user_name']}* ne 4-anki pin takun live trading sathi permission dili ahe.")
        return {"status": "success", "message": "Bot yashasviritya live zala ahe!"}
    
    return {"status": "error", "message": "❌ Chukicha security pin! Permission denied."}

# ==================================================================
# 📈 TRADINGVIEW WEBHOOK RECIEVER ROUTE
# ==================================================================
@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    global NSE_LIVE_LTP
    signal_data = request.json
    user = user_database["user_01"]
    
    action = signal_data.get("action") 
    strike = int(signal_data.get("strike", 24600)) 
    option_type = signal_data.get("option_type", "CE") 
    
    nifty_rate = NSE_LIVE_LTP if NSE_LIVE_LTP > 0 else float(signal_data.get("price", 24600))
    premium_price = get_option_premium("NIFTY", strike, option_type)
    if not premium_price:
        premium_price = 100.0 
        
    days_passed = (datetime.now() - user["strategy_updated_at"]).days

    if days_passed < 10 or user["account_status"] == "PAPER_LOCK":
        msg = (
            f"🗒️ *Paper Trade Alert!*\n"
            f"🎯 Instrument: NIFTY {strike} {option_type}\n"
            f"⚡ Action: {action} (Call Buy Simulation)\n"
            f"💰 Entry Premium: ₹{premium_price}\n"
            f"📊 Nifty Live: ₹{nifty_rate}\n"
            f"🔒 Safety Lock Remaining: {10 - days_passed} days"
        )
        send_telegram_alert(msg)
        threading.Thread(target=run_trailing_logic, args=("NIFTY", strike, option_type, premium_price, False)).start()

    elif user["account_status"] == "LIVE_ACTIVE":
        msg = (
            f"🚨 *Real Trade Alert! (Angel One)*\n"
            f"🎯 Instrument: NIFTY {strike} {option_type}\n"
            f"⚡ Action: {action}\n"
            f"💰 Premium Market Price: ₹{premium_price}"
        )
        send_telegram_alert(msg)
        
        from broker import find_option_instrument
        tsymbol, token = find_option_instrument("NIFTY", strike, option_type)
        if tsymbol and token:
            place_order("NIFTY", tsymbol, token, "BUY", 25)
            
        threading.Thread(target=run_trailing_logic, args=("NIFTY", strike, option_type, premium_price, True)).start()

    return {"status": "processed"}

# ==================================================================
# 📉 15-POINT SL & 10-POINT COST-TO-COST TRAILING LOGIC
# ==================================================================
def run_trailing_logic(name, strike, option_type, entry_price, is_live):
    stop_loss = entry_price - 15
    is_at_cost = False
    mode = "LIVE" if is_live else "PAPER"
    
    while True:
        current_premium = get_option_premium(name, strike, option_type)
        if not current_premium:
            current_premium = entry_price 
            
        if current_premium >= (entry_price + 10) and not is_at_cost:
            stop_loss = entry_price 
            is_at_cost = True
            send_telegram_alert(
                f"📈 *SL Cost-to-Cost Jhala ({mode})!*\n"
                f"🎯 NIFTY {strike} {option_type}\n"
                f"🔥 Current Premium: ₹{current_premium}\n"
                f"🔒 SL shifted to Entry Price: ₹{stop_loss}\n"
                f"🛡️ Ata ha trade 100% safe ahe!"
            )

        if current_premium <= stop_loss:
            exit_msg = (
                f"⚠️ *Stop Loss Hit ({mode})!*\n"
                f"🎯 NIFTY {strike} {option_type}\n"
                f"🚪 Square-off Price: ₹{current_premium}\n"
                f"📊 Result: " + ("Zero Loss / Cost-to-Cost" if is_at_cost else "-15 Pts Loss")
            )
            send_telegram_alert(exit_msg)
            
            if is_live:
                from broker import find_option_instrument
                tsymbol, token = find_option_instrument(name, strike, option_type)
                if tsymbol and token:
                    place_order(name, tsymbol, token, "SELL", 25)
            break
            
        time.sleep(0.5)

# ==================================================================
# SERVER STARTUP
# ==================================================================
if __name__ == "__main__":
    init_nse_stream()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
