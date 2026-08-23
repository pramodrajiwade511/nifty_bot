import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import broker
import os
import datetime
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

# --- ⏰ टाइम शेड्युलर लॉजिक (९:०० आणि ९:१十六) ---
def morning_wish():
    print("🌄 शुभ सकाळ, प्रमोद भाऊ आणि कामगार बांधवांनो!")

def auto_start_bot():
    try:
        db = firestore.client()
        broker.db = db
        session = broker.get_smart_api_session()
        if session:
            print("🚀 SafeAlgoBot अपडेट: ऑटो-लॉगिन पूर्ण झाले आहे!")
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
        else:
            firebase_admin.initialize_app()
            db = firestore.client()
    except Exception as e:
        st.error(f"फायरबेस कनेक्शन एरर: {e}")
else:
    db = firestore.client()

broker.db = db

# --- डॅशबोर्ड स्क्रीनची सुरुवात ---
st.set_page_config(page_title="SafeAlgoBot No Loss", page_icon="🛡️", layout="centered")
st.title("🛡️ SafeAlgoBot - 'नो लॉस' कामगार विशेष")

# जर डेटाबेस कनेक्ट नसेल तर युझरला सावध करणे
if db is None:
    st.error("❌ फायरबेस डेटाबेसशी कनेक्शन होऊ शकले नाही! कृपया 'firebase_key.json' तत्या सांगा.")
    st.stop()

# --- 📊 P&L डॅशबोर्ड ---
pnl_ref = db.collection('pnl_tracker').document('user_01')
pnl_data = pnl_ref.get().to_dict() or {"daily_pnl": 0.0, "weekly_pnl": 0.0, "total_brokerage": 0.0}
daily_pnl = pnl_data.get("daily_pnl", 0.0)
total_brokerage = pnl_data.get("total_brokerage", 0.0)
net_pnl = daily_pnl - total_brokerage

st.write("### 📊 आजचा निव्वळ हिशोब")
col1, col2, col3 = st.columns(3)
with col1: st.metric(label="📅 एकूण P&L", value=f"₹ {daily_pnl:,.2f}")
with col2: st.metric(label="💸 ब्रोकरेज", value=f"₹ {total_brokerage:,.2f}")
with col3: st.metric(label="💰 हातात येणारा नफा (Net)", value=f"₹ {net_pnl:,.2f}")

st.divider()

# --- 📂 इनपुट पॅनेल ---
st.write("### ⚙️ 'No Loss' फास्ट ट्रेलिंग सेटिंग्स")
asset_type = st.selectbox("ट्रेडिंग प्रकार:", ["STOCKS (शेअर्स) 🛡️", "NIFTY / BANKNIFTY", "FINNIFTY"])
symbol_input = st.text_input("सिम्बॉल नाव:", "TATASTEEL" if "STOCKS" in asset_type else "NIFTY24SEP24500CE")
qty = st.number_input("क्वांटिटी संख्या:", value=10 if "STOCKS" in asset_type else 25)

col_in1, col_in2 = st.columns(2)
with col_in1:
    entry_price = st.number_input("खरेदी भाव (Entry Price)", value=100.0)
with col_in2:
    market_sl = st.number_input("चार्टनुसार स्टॉपलॉस भाव (Market SL Price)", value=80.0)

target_val = st.number_input("Target Points (TP1)", value=30)
trailing_fixed = 10 

if st.button("🚀 'नो लॉस' अल्गो ट्रेड TRIGER करा", use_container_width=True):
    res = broker.place_fast_trailing_order(symbol_input, "BUY", qty, entry_price, market_sl, target_val, trailing_fixed)
    
    if res.get("status"):
        st.success("ऑर्डर यशस्वी!")
        calculated_sl_pts = res.get("calculated_sl")
        exit_price = entry_price + target_val
        gross_trade_pnl = float(target_val * qty)
        trade_brokerage = 15.0 if "STOCKS" in asset_type else 45.0
        
        # हिस्टरी सेव्ह
        db.collection('trade_history').add({
            "timestamp": firestore.SERVER_TIMESTAMP,
            "time": datetime.datetime.now().strftime("%I:%M %p"),
            "symbol": symbol_input.upper(),
            "type": f"🎯 {asset_type} BUY",
            "entry": entry_price,
            "exit": exit_price,
            "brokerage": trade_brokerage,
            "net_pnl": gross_trade_pnl - trade_brokerage
        })
        
        pnl_ref.update({"daily_pnl": daily_pnl + gross_trade_pnl, "total_brokerage": total_brokerage + trade_brokerage})
        st.rerun()
    else:
        st.error(f"फेल: {res.get('message')}")
