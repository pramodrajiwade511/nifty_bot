"""
MAIN BOT SERVER - FINAL FIREBASE DATABASE EDITION
==================================================
Ha server TradingView che signals catch करतो, Google Firebase Database dware
प्रत्येक युजरचा ४-अंकी गुप्त पिन, ब्रोकर डिटेल्स आणि 10-divasacha safety lock अचूक ट्रॅक करतो.
"""

import os
import hashlib
import threading
import time
from datetime import datetime
from flask import Flask, json, request, render_template, jsonify
import requests

# Google Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore

# broker.py madhun functions ani WebSocket data import karne
from broker import place_order, get_option_premium, init_nse_stream, NSE_LIVE_LTP

app = Flask(__name__)

# Render cha variables madhun Details ghene
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FIREBASE_CONFIG = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

# ==================================================================
# 🛡️ FIREBASE DATABASE INITIALIZATION
# ==================================================================
db = None
try:
    if FIREBASE_CONFIG:
        cred_json = json.loads(FIREBASE_CONFIG)
        cred = credentials.Certificate(cred_json)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Google Firebase Database Connected Successfully!")
    else:
        print("⚠️ FIREBASE_SERVICE_ACCOUNT variable Render वर सापडला नाही!")
except Exception as e:
    print(f"❌ Firebase Connection Error: {e}")

# 📢 Telegram var SMS alert pathavne
def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload)
    except Exception as e: print(f"Telegram Error: {e}")

# ==================================================================
# 📱 APP FRONTEND ROUTES
# ==================================================================
@app.route('/')
def login_page(): return render_template('login.html')

@app.route('/connect-broker')
def broker_page(): return render_template('broker.html')

@app.route('/dashboard')
def dashboard_page(): return render_template('dashboard.html')

# ==================================================================
# 🔒 ॲपवरून येणारा ब्रोकर डेटा थेट खऱ्या डेटाबेसमध्ये सेव्ह करणे (नवीन API)
# ==================================================================
@app.route('/save-broker-details', methods=['POST'])
def save_broker_details():
    if db is None: return jsonify({"status": "error", "message": "Database कनेक्ट नाही!"}), 500
    
    data = request.json
    user_id = data.get("user_id", "user_01")
    broker_name = data.get("broker_name")
    client_id = data.get("client_id")
    mpin = data.get("mpin")
    api_key = data.get("api_key")
    totp_secret = data.get("totp_secret")
    
    try:
        user_ref = db.collection('users').document(user_id)
        
        # आधीचा डेटा असेल तर तो सुरक्षित ठेवून नवीन ब्रोकर डिटेल्स अपडेट करणे
        user_ref.set({
            "user_name": "योगेश",
            "broker_name": broker_name,
            "broker_client_id": client_id,
            "broker_mpin": mpin,  # खऱ्या डेटाबेसमध्ये सुरक्षितपणे लॉक होईल
            "broker_api_key": api_key,
            "broker_totp_secret": totp_secret,
            "account_status": "PAPER_LOCK", # सुरुवातीला सक्तीचा पेपर लॉक
            "strategy_updated_at": datetime.now().isoformat() if not user_ref.get().exists else user_ref.get().to_dict().get("strategy_updated_at", datetime.now().isoformat())
        }, merge=True)
        
        send_telegram_alert(f"🔗 *Broker Connected!*\nयुजरने त्याचे *{broker_name}* खाते यशस्वीरित्या डेटाबेसशी जोडले आहे.")
        return jsonify({"status": "success", "message": "ब्रोकर डिटेल्स डेटाबेसमध्ये सुरक्षितपणे सेव्ह झाले आहेत!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================================================================
# 🔓 खऱ्या डेटाबेससह 4-ANKI PIN VERIFICATION & LIVE ACTIVATION
# ==================================================================
@app.route('/activate-live', methods=['POST'])
def activate_live():
    if db is None: return {"status": "error", "message": "Database कनेक्ट नाही!"}
    
    data = request.json
    user_id = data.get("user_id", "user_01")
    entered_pin = data.get("pin")
    
    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return {"status": "error", "message": "User सापडला नाही!"}
            
        user_data = user_doc.to_dict()
        
        # १० दिवस झाले आहेत का ते तपासणे
        saved_time = datetime.fromisoformat(user_data['strategy_updated_at'])
        days_passed = (datetime.now() - saved_time).days
        
        if days_passed < 10:
            return {
                "status": "error", 
                "message": f"🔒 अजून {10 - days_passed} दिवस पेपर ट्रेडिंग करणे बंधनकारक आहे!"
            }
            
        # डेटाबेसमधील सुरक्षित 'broker_mpin' टाकून युजरचे लाईव्ह ट्रेडिंग व्हेरिफाय करणे
        if entered_pin == user_data.get("broker_mpin"):
            user_ref.update({"account_status": "LIVE_ACTIVE"})
            send_telegram_alert(f"🚀 *Live Mode Active!*\nयुजर *{user_data['user_name']}* ने खऱ्या डेटाबेसमध्ये पिन व्हेरिफाय करून लाईव्ह ट्रेडिंग सुरू केले आहे.")
            return {"status": "success", "message": "बॉट यशस्वीरित्या लाईव्ह झाला आहे!"}
            
        return {"status": "error", "message": "❌ चुकीचा सिक्युरिटी पिन!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==================================================================
# 📈 TRADINGVIEW WEBHOOK RECIEVER ROUTE (खऱ्या डेटाबेसवर आधारित)
# ==================================================================
@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    global NSE_LIVE_LTP
    signal_data = request.json
    user_id = "user_01"
    
    action = signal_data.get("action") 
    strike = int(signal_data.get("strike", 24600)) 
    option_type = signal_data.get("option_type", "CE") 
    
    nifty_rate = NSE_LIVE_LTP if NSE_LIVE_LTP > 0 else float(signal_data.get("price", 24600))
    premium_price = get_option_premium("NIFTY", strike, option_type)
    if not premium_price: premium_price = 100.0 
    
    # डेटाबेसमधून युजरचा मोड चेक करणे
    account_status = "PAPER_LOCK"
    days_passed = 0
    if db:
        try:
            user_doc = db.collection('users').document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                account_status = user_data.get("account_status", "PAPER_LOCK")
                saved_time = datetime.fromisoformat(user_data['strategy_updated_at'])
                days_passed = (datetime.now() - saved_time).days
        except: pass

    # 🛑 PAPER TRADING MODE
    if days_passed < 10 or account_status == "PAPER_LOCK":
        msg = f"🗒️ *Paper Trade Alert!*\n🎯 NIFTY {strike} {option_type}\n⚡ Action: {action}\n💰 Premium: ₹{premium_price}\n🔒 सेफ्टी लॉकचे बाकी दिवस: {10 - days_passed}"
        send_telegram_alert(msg)
        threading.Thread(target=run_trailing_logic, args=("NIFTY", strike, option_type, premium_price, False)).start()

    # 🚀 REAL TRADING MODE
    elif account_status == "LIVE_ACTIVE":
        msg = f"🚨 *Real Trade Alert! (Angel One)*\n🎯 NIFTY {strike} {option_type}\n⚡ Action: {action}\n💰 Premium: ₹{premium_price}"
        send_telegram_alert(msg)
        
        from broker import find_option_instrument
        tsymbol, token = find_option_instrument("NIFTY", strike, option_type)
        if tsymbol and token:
            place_order("NIFTY", tsymbol, token, "BUY", 25)
            
        threading.Thread(target=run_trailing_logic, args=("NIFTY", strike, option_type, premium_price, True)).start()

    return {"status": "processed"}

# 📉 15-POINT SL & 10-POINT COST-TO-COST TRAILING
def run_trailing_logic(name, strike, option_type, entry_price, is_live):
    stop_loss = entry_price - 15
    is_at_cost = False
    mode = "LIVE" if is_live else "PAPER"
    
    while True:
        current_premium = get_option_premium(name, strike, option_type)
        if not current_premium: current_premium = entry_price 
            
        if current_premium >= (entry_price + 10) and not is_at_cost:
            stop_loss = entry_price 
            is_at_cost = True
            send_telegram_alert(f"📈 *SL Cost-to-Cost Jhala ({mode})!*\n🎯 NIFTY {strike} {option_type}\n🔒 SL shifted to Entry Price: ₹{stop_loss}")

        if current_premium <= stop_loss:
            exit_msg = f"⚠️ *Stop Loss Hit ({mode})!*\n🎯 NIFTY {strike} {option_type}\n🚪 Square-off Price: ₹{current_premium}"
            send_telegram_alert(exit_msg)
            
            if is_live:
                from broker import find_option_instrument
                tsymbol, token = find_option_instrument(name, strike, option_type)
                if tsymbol and token: place_order(name, tsymbol, token, "SELL", 25)
            break
        time.sleep(0.5)

if __name__ == "__main__":
    init_nse_stream()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
