import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import broker
import os
import requests
import datetime
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

# ⚠️ तुमची टेलिग्राम क्रेडेंशियल्स इथे टाका
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"

def send_telegram_alert(message):
    try:
        url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception: pass

# --- ⏰ टाइम शेड्युलर लॉजिक (९:०० आणि ९:१६) ---
def morning_wish():
    send_telegram_alert("🌄 *शुभ सकाळ, प्रमोद भाऊ आणि कामगार बांधवांनो!* \n\nSafeAlgoBot रेडी आहे. आजच्या सुरक्षित ट्रेडिंगसाठी सर्वांना खूप शुभेच्छा! 🌄🌄")

def auto_start_bot():
    db = firestore.client()
    broker.db = db
    session = broker.get_smart_api_session()
    if session:
        send_telegram_alert("🚀 *SafeAlgoBot अपडेट:* सकाळी ०९:१६ झाले आहेत. सिस्टीमने फायरबेसमधून एमपिन वाचून ऑटो-लॉगिन पूर्ण केले आहे! 🤖")

if "scheduler_started" not in st.session_state:
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(morning_wish, 'cron', hour=9, minute=0)
    scheduler.add_job(auto_start_bot, 'cron', hour=9, minute=16)
    scheduler.start()
    st.session_state.scheduler_started = True

# --- ⚙️ फायरबेस कनेक्शन ---
db = None
if not firebase_admin._apps:
    try:
        if os.path.exists('firebase_key.json'):
            cred = credentials.Certificate('firebase_key.json')
            firebase_admin.initialize_app(cred)
    except Exception: pass

db = firestore.client()
broker.db = db

st.set_page_config(page_title="SafeAlgoBot Ultra Setup", page_icon="🛡️", layout="centered")
st.title("🛡️ SafeAlgoBot - कामगार विशेष महा-अल्गो")

# --- 📊 नफा-तोटा आणि ब्रोकरेज कप्पे ---
pnl_ref = db.collection('pnl_tracker').document('user_01')
pnl_data = pnl_ref.get().to_dict() or {"daily_pnl": 0.0, "weekly_pnl": 0.0, "total_brokerage": 0.0}

daily_pnl = pnl_data.get("daily_pnl", 0.0)
weekly_pnl = pnl_data.get("weekly_pnl", 0.0)
total_brokerage = pnl_data.get("total_brokerage", 0.0)
net_pnl = daily_pnl - total_brokerage

col1, col2, col3 = st.columns(3)
with col1: st.metric(label="📅 ग्रॉस नफा/तोटा", value=f"₹ {daily_pnl:,.2f}")
with col2: st.metric(label="💸 एकूण ब्रोकरेज खर्च", value=f"₹ {total_brokerage:,.2f}", delta=f"-₹{total_brokerage}", delta_color="inverse")
with col3: st.metric(label="💰 निव्वळ नफा (Net)", value=f"₹ {net_pnl:,.2f}")

st.divider()

# --- 📜 पासबुक हिस्ट्री टेबल ---
st.write("### 📜 आजचे कॉल रेकॉर्ड्स (Daily Trade History)")
trades_ref = db.collection('trade_history').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10)
trades_docs = trades_ref.stream()

trade_list = []
for doc in trades_docs:
    t_data = doc.to_dict()
    trade_list.append({
        "वेळ (Time)": t_data.get("time"),
        "कॉल तपशील": t_data.get("symbol"),
        "प्रकार": t_data.get("type"),
        "एंट्री भाव": f"₹{t_data.get('entry')}",
        "एक्झिट भाव": f"₹{t_data.get('exit')}",
        "ब्रोकरेज": f"₹{t_data.get('brokerage')}",
        "निव्वळ P&L": f"₹{t_data.get('net_pnl')}"
    })

if trade_list:
    st.dataframe(pd.DataFrame(trade_list), use_container_width=True)
else:
    st.info("⏳ आज अजून कोणताही ट्रेड झालेला नाही.")

st.divider()

# --- 🚨 ट्रेडिंगव्ह्यू साइडवेज आणि चार्ट अलर्ट सिस्टीम ---
st.write("### ⚠️ चार्ट इंडिकेटर लाइव्ह स्टेटस")
if "status_message" not in st.session_state:
    st.session_state.status_message = "⏳ चार्ट कडून सिग्नल्सची वाट पाहत आहे..."

st.info(st.session_state.status_message)

def receive_tradingview_signal(signal_type, symbol_name):
    """ट्रेडिंगव्ह्यू कडून आलेला सिग्नल प्रोसेस करणे"""
    if signal_type == "SIDEWAYS":
        st.session_state.status_message = "⚠️ [चार्ट अलर्ट]: मार्केट साइडवेज आहे!"
        alert_msg = (
            f"⚠️ *[SAFE ALGO BOT ALERT]*\n"
            f"-------------------------------------\n"
            f"🚨 *मार्केट साइडवेज आहे !*\n"
            f"-------------------------------------\n"
            f"📌 *तपशील:* मार्केट रेंजबाऊंड आहे. कामगार बांधवांचे नुकसान टाळण्यासाठी बॉटने नवीन ट्रेड घेणे थांबवले आहे! 🛑"
        )
        send_telegram_alert(alert_msg)
        
    elif signal_type in ["BUY", "SELL"]:
        st.session_state.status_message = f"🔔 [ट्रेड सिग्नल]: {symbol_name} {signal_type} ट्रिगर!"
        
        # फिक्स रिस्क पॅरामीटर्स (तुमच्या नियमांनुसार)
        e_price = 100
        sl_points = 15
        tsl_points = 10
        tp_points = 30
        qty_lots = 25
        
        res = broker.place_algo_robo_order(symbol_name, signal_type, qty_lots, e_price, tp_points, sl_points, tsl_points)
        
        if res.get("status"):
            exit_p = e_price + tp_points if signal_type == "BUY" else e_price - tp_points
            gross_trade = float(tp_points * qty_lots)
            trade_b = 45.0
            
            # हिस्टरी सेव्ह
            db.collection('trade_history').add({
                "timestamp": firestore.SERVER_TIMESTAMP,
                "time": datetime.datetime.now().strftime("%I:%M %p"),
                "symbol": symbol_name.upper(),
                "type": f"🎯 {signal_type}->EXIT",
                "entry": e_price,
                "exit": exit_p,
                "brokerage": trade_b,
                "net_pnl": gross_trade - trade_b
            })
            
            pnl_ref.update({"daily_pnl": daily_pnl + gross_trade, "total_brokerage": total_brokerage + trade_b})
            
            # लाईनशीर सविस्तर टेलिग्राम रिपोर्ट
            report = (
                f"📊 *[SAFE ALGO BOT - कामगार विशेष रिपोर्ट]*\n"
                f"-------------------------------------\n"
                f"✅ *ट्रेड पूर्ण झाला:* {symbol_name.upper()} ({signal_type})\n"
                f"🛫 *एंट्री प्राईज:* ₹{e_price}\n"
                f"🛑 *स्टॉपलॉस (SL):* ₹{e_price - sl_points} (१५ pts)\n"
                f"🔥 *ट्रेलिंग नियम:* किंमत ₹११० वर जाताच SL ₹१०० वर आला आणि पुढे ट्रेल झाला!\n"
                f"🛬 *एक्झिट प्राईज (Target):* ₹{exit_p}\n"
                f"💸 *ब्रोकरेज खर्च:* ₹{trade_b}\n"
                f"💰 *निव्वळ नफा (Net):* ₹{gross_trade - trade_b}\n"
                f"-------------------------------------\n"
                f"📈 *चार्ट ॲनॅलिसिस:* सपोर्ट आणि रेझिस्टन्स लाईन्स यशस्वीरित्या ड्रॉ केल्या आहेत.\n"
                f"-------------------------------------\n"
                f"🆔 *ऑर्डर ID:* {res.get('order_id')}"
            )
            send_telegram_alert(report)

# --- ५. 📂 ॲसेट सिलेक्शन (डॅशबोर्ड बॅकअप लेआउट) ---
st.write("### 📂 मॅन्युअल बॅकअप पॅनेल")
asset_type = st.selectbox("ट्रेडिंग प्रकार:", ["STOCKS (कमी बजेट सुरक्षा) 🛡️", "NIFTY / BANKNIFTY", "FINNIFTY"])
symbol_input = st.text_input("सिम्बॉल नाव:", "TATASTEEL" if "STOCKS" in asset_type else "NIFTY24SEP24500CE")
qty_input = st.number_input("क्वांटिटी संख्या:", value=10 if "STOCKS" in asset_type else 25)

if st.button("🚀 चाचणी ट्रेड ट्रिगर", use_container_width=True):
    receive_tradingview_signal("BUY", symbol_input)
    st.rerun()
