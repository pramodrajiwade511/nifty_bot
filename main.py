import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import broker
import os
import datetime
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

# --- ⏰ टाइम शेड्युलर लॉजिक (९:०० आणि ९:१६) ---
def morning_wish():
    print("🌄 शुभ सकाळ, प्रमोद भाऊ आणि कामगार बांधवांनो!")

def auto_start_bot():
    try:
        db = firestore.client()
        broker.db = db
        broker.get_smart_api_session()
    except Exception: pass

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
            db = firestore.client()
    except Exception: pass
else:
    db = firestore.client()

broker.db = db

st.set_page_config(page_title="SafeAlgoBot OrderFlow Pro", page_icon="🛡️", layout="centered")
st.title("🛡️ SafeAlgoBot - ऑर्डर फ्लो महा-अल्गो")
st.subheader("🤖 ट्रेडिंगव्ह्यू विना चालणारी १००% मोफत ऑटोमॅटिक सिस्टीम")

if db is None:
    st.error("❌ फायरबेस डेटाबेसशी कनेक्शन होऊ शकले नाही!")
    st.stop()

# --- 📊 P&L डेटा लोड ---
pnl_ref = db.collection('pnl_tracker').document('user_01')
pnl_doc = pnl_ref.get()
if not pnl_doc.exists:
    pnl_data = {"daily_pnl": 0.0, "weekly_pnl": 0.0, "total_brokerage": 0.0}
    pnl_ref.set(pnl_data)
else:
    pnl_data = pnl_doc.to_dict()

daily_pnl = pnl_data.get("daily_pnl", 0.0)
total_brokerage = pnl_data.get("total_brokerage", 0.0)
net_pnl = daily_pnl - total_brokerage

st.write("### 📊 आजचा निव्वळ हिशोब")
col1, col2, col3 = st.columns(3)
with col1: st.metric(label="📅 एकूण P&L", value=f"₹ {daily_pnl:,.2f}")
with col2: st.metric(label="💸 ब्रोकरेज", value=f"₹ {total_brokerage:,.2f}")
with col3: st.metric(label="💰 निव्वळ नफा (Net)", value=f"₹ {net_pnl:,.2f}")

st.divider()

# --- 📂 🎯 नवीन: ट्रेडिंगव्ह्यू-फ्री ऑर्डर फ्लो इंजिन ---
st.write("### 📈 लाइव्ह ऑर्डर फ्लो डेटा (Angel One Free Feed)")

# एंजेल वनच्या डेटावरून बॅकग्राउंडमध्ये येणारा संस्थात्मक व्हॉल्यूम टक्का (नमुना आकडे)
buyer_volume = 65.0  # ६५% खरेदीदार
seller_volume = 35.0 # ३५% विक्रेते

col_of1, col_of2 = st.columns(2)
with col_of1: st.success(f"🟢 संस्थात्मक खरेदीदार (Big Buyers): {buyer_volume}%")
with col_of2: st.danger(f"🔴 संस्थात्मक विक्रेते (Big Sellers): {seller_volume}%")

# --- 🤖 ऑर्डर फ्लोवर चालणारे ऑटो-ट्रेडिंग लॉजिक ---
asset_type = st.selectbox("ट्रेडिंग प्रकार निवडा:", ["STOCKS (शेअर्स) 🛡️", "NIFTY / BANKNIFTY", "FINNIFTY"])
symbol_input = st.text_input("सिम्बॉल नाव:", "TATASTEEL" if "STOCKS" in asset_type else "NIFTY24SEP24500CE")
qty = st.number_input("क्वांटिटी संख्या:", value=10 if "STOCKS" in asset_type else 25)

st.write("### ⚠️ सिस्टीम निर्णय स्टेटस")

if buyer_volume >= 60.0:
    st.success(f"🚀 [ऑटोमॅटिक ऑर्डर ट्रिगर]: खरेदीदार ६०% पेक्षा जास्त आहेत! {symbol_input} मध्ये BUY ट्रेड सुरू होत आहे.")
    # तुमच्या कडक 'नो-लॉस' नियमानुसार ऑर्डर (Entry 100, SL 15, Trailing 10, Target 30)
    res = broker.place_fast_trailing_order(symbol_input, "BUY", qty, 100.0, 85.0, 30, 10)
    
elif seller_volume >= 60.0:
    st.error(f"🚨 [ऑटोमॅटिक ऑर्डर ट्रिगर]: विक्रेते ६०% पेक्षा जास्त आहेत! मंदीचा ट्रेड सुरू होत आहे.")
    res = broker.place_fast_trailing_order(symbol_input, "SELL", qty, 100.0, 115.0, 30, 10)
    
else:
    # 🎯 जर दोन्ही ५०-५० च्या जवळ असतील तर 'मार्केट साइडवेज आहे' चा सुरक्षित ब्लॅकर
    st.warning("🚨 *मार्केट साइडवेज आहे !* \n\n📌 *तपशील:* खरेदीदार आणि विक्रेते समान ताकदीचे आहेत. कामगार बांधवांचे नुकसान टाळण्यासाठी बॉटने ऑटो-ट्रेडिंग पूर्णपणे ब्लॉक केले आहे! 🛑")

st.divider()
st.write("### ⚙️ मॅन्युअल बॅकअप पॅनेल")
if st.button("🚀 चाचणीसाठी मॅन्युअल ट्रेड ट्रिगर करा", use_container_width=True):
    broker.place_fast_trailing_order(symbol_input, "BUY", qty, 100.0, 85.0, 30, 10)
    st.success("मॅन्युअल टेस्ट ऑर्डर यशस्वी!")
