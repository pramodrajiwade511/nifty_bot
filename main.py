import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import broker
import os
import requests
import datetime
import pandas as pd

# ⚠️ तुमची टेलिग्राम माहिती इथे भरा
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"

def send_telegram_alert(message):
    try:
        url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception: pass

# १. फायरबेस कनेक्शन
db = None
if not firebase_admin._apps:
    try:
        if os.path.exists('firebase_key.json'):
            cred = credentials.Certificate('firebase_key.json')
            firebase_admin.initialize_app(cred)
    except Exception: pass

db = firestore.client()
broker.db = db

st.set_page_config(page_title="SafeAlgoBot Public Pro", page_icon="📈", layout="centered")
st.title("📈 SafeAlgoBot - कामगार विशेष अल्गो")
st.subheader("🤖 गरजू आणि कष्टकरी भावांसाठी पूर्ण ऑटोमॅटिक ट्रेडिंग")

st.divider()

# २. मुख्य P&L आणि ब्रोकरेज डॅशबोर्ड
st.write("### 📊 आजचा चालू हिशोब (Account Summary)")
pnl_ref = db.collection('pnl_tracker').document('user_01')
pnl_data = pnl_ref.get().to_dict() or {"daily_pnl": 0.0, "weekly_pnl": 0.0, "total_brokerage": 0.0}

daily_pnl = pnl_data.get("daily_pnl", 0.0)
weekly_pnl = pnl_data.get("weekly_pnl", 0.0)
total_brokerage = pnl_data.get("total_brokerage", 0.0)
net_pnl = daily_pnl - total_brokerage

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="📅 ग्रॉस नफा/तोटा (Gross P&L)", value=f"₹ {daily_pnl:,.2f}")
with col2:
    st.metric(label="💸 एकूण ब्रोकरेज खर्च (Brokerage)", value=f"₹ {total_brokerage:,.2f}", delta=f"-₹{total_brokerage}", delta_color="inverse")
with col3:
    # खर्च वजा करून हातात आलेला निव्वळ नफा
    st.metric(label="💰 निव्वळ नफा (Net P&L)", value=f"₹ {net_pnl:,.2f}")

st.divider()

# ३. 📝 रोजच्या ट्रेड्सची लाईनशीर हिस्ट्री (Daily Trade Log)
st.write("### 📜 आजचे कॉल रेकॉर्ड्स (Daily Trade History)")

# फायरबेसमधून आजच्या तारखेचे ट्रेड्स आणणे
trades_ref = db.collection('trade_history').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10)
trades_docs = trades_ref.stream()

trade_list = []
for doc in trades_docs:
    t_data = doc.to_dict()
    trade_list.append({
        "वेळ (Time)": t_data.get("time"),
        "कॉल तपशील (Symbol)": t_data.get("symbol"),
        "प्रकार": t_data.get("type"),
        "एंट्री भाव": f"₹{t_data.get('entry')}",
        "एक्झिट भाव": f"₹{t_data.get('exit')}",
        "ब्रोकरेज": f"₹{t_data.get('brokerage')}",
        "निव्वळ P&L": f"₹{t_data.get('net_pnl')}"
    })

if trade_list:
    df = pd.DataFrame(trade_list)
    st.dataframe(df, use_container_width=True) # स्क्रीनवर सुंदर टेबल दिसेल
else:
    st.info("⏳ आज अजून कोणताही ट्रेड झालेला नाही. मार्केट उघडण्याची वाट पाहत आहे...")

st.divider()

# ४. रिस्क सेटिंग्स पॅनेल (बॅकएंड लॉजिक)
st.write("### 🛡️ अल्गो रिस्क सेटिंग्स")
entry_price = st.number_input("Entry Price", value=100)
sl_val = st.number_input("Initial Stop Loss (Points)", value=15)
tsl_val = st.number_input("Trailing Jump (Points)", value=10)
target_val = st.number_input("Target Points (TP1)", value=30)

symbol_input = st.text_input("सिम्बॉल डिटेल्स (उदा. NIFTY24SEP24500CE)", "NIFTY24SEP24500CE")
qty = st.number_input("क्वांटिटी (Lots)", min_value=1, value=25, step=25)

if st.button("🚀 चाचणी ट्रेड ट्रिगर करा", use_container_width=True):
    res = broker.place_algo_robo_order(symbol_input, "9992600", "BUY", qty, entry_price, target_val, sl_val, tsl_val)
    
    if res.get("status"):
        st.success("ऑर्डर यशस्वी!")
        
        # काल्पनिक एक्झिट डेटा (चाचणीसाठी टार्गेट हिट झाले असे गृहीत धरू)
        exit_price = entry_price + target_val
        gross_trade_pnl = float(target_val * qty)
        
        # एंजेल वननुसार ₹२० बाय + ₹२० सेल + टॅक्स = अंदाजे ₹४५ प्रति ट्रेड खर्च
        trade_brokerage = 45.0 
        trade_net = gross_trade_pnl - trade_brokerage
        
        now_time = datetime.datetime.now().strftime("%I:%M %p")
        
        # १. नवीन ट्रेड फायरबेस हिस्टरीमध्ये सेव्ह करणे
        db.collection('trade_history').add({
            "timestamp": firestore.SERVER_TIMESTAMP,
            "time": now_time,
            "symbol": symbol_input,
            "type": "🎯 BUY->EXIT",
            "entry": entry_price,
            "exit": exit_price,
            "brokerage": trade_brokerage,
            "net_pnl": trade_net
        })
        
        # २. एकूण डॅशबोर्डचे आकडे अपडेट करणे
        pnl_ref.update({
            "daily_pnl": daily_pnl + gross_trade_pnl,
            "total_brokerage": total_brokerage + trade_brokerage
        })
        
        # ३. कामगारांसाठी सोप्या भाषेत टेलिग्राम मेसेज पाठवणे
        report = (
            f"📊 *[SAFE ALGO BOT - कामगार विशेष रिपोर्ट]*\n"
            f"-------------------------------------\n"
            f"✅ *ट्रेड पूर्ण झाला:* {symbol_input}\n"
            f"🛫 *एंट्री प्राईज:* ₹{entry_price}\n"
            f"🛬 *एक्झिट प्राईज:* ₹{exit_price}\n"
            f"💸 *ब्रोकरेज खर्च:* ₹{trade_brokerage}\n"
            f"💰 *निव्वळ नफा (हातात आलेला):* ₹{trade_net}\n"
            f"-------------------------------------\n"
            f"📌 *एकूण आजची कमाई:* ₹{daily_pnl + gross_trade_pnl - total_brokerage - trade_brokerage}\n"
            f"-------------------------------------\n"
            f"🆔 *ऑर्डर ID:* {res.get('order_id')}"
        )
        send_telegram_alert(report)
        st.rerun()
    else:
        st.error(f"फेल: {res.get('message')}")
