import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import broker
import os
import datetime
import pandas as pd

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
        st.error(f"फायरबेस एरर: {e}")
else:
    db = firestore.client()

broker.db = db

# --- डॅशबोर्ड स्क्रीनची सुरुवात ---
st.set_page_config(page_title="SafeAlgoBot Trailing Pro", page_icon="🛡️", layout="centered")
st.title("🛡️ SafeAlgoBot - 'नो लॉस' कामगार विशेष")

if db is None:
    st.error("❌ फायरबेस डेटाबेसशी कनेक्शन होऊ शकले नाही!")
    st.stop()

# --- 📊 P&L डेटा लोड लॉजिक ---
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
with col3: st.metric(label="💰 हातात येणारा नफा (Net)", value=f"₹ {net_pnl:,.2f}")

st.divider()

# --- 📡 ट्रेडिंगव्ह्यू सिग्नल इनपुट (Webhook Backend Bypass) ---
st.write("### ⚠️ चार्ट इंडिकेटर लाइव्ह स्टेटस")
# हा भाग ट्रेडिंगव्ह्यू कडून येणारा लाईव्ह सिग्नल रिसिव्ह करतो
query_params = st.query_params
if "signal" in query_params:
    tv_signal = query_params["signal"]
    tv_symbol = query_params.get("symbol", "NIFTY")
    st.success(f"🔔 [TradingView Signal Recieved]: {tv_symbol} -> {tv_signal}")
    
    # ऑटो-ट्रेड ट्रिगर लॉजिक
    if tv_signal in ["BUY", "SELL"]:
        broker.place_fast_trailing_order(tv_symbol, tv_signal, 25, 100.0, 80.0, 30, 10)
else:
    st.info("⏳ ट्रेडिंगव्ह्यू चार्ट कडून सिग्नलची वाट पाहत आहे... सिस्टीम रेडी आहे!")

st.divider()

# --- 📂 इनपुट पॅनेल ---
st.write("### ⚙️ 'No Loss' मॅन्युअल बॅकअप सेटिंग्स")
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
        st.rerun()
    else:
        st.error(f"फेल: {res.get('message')}")
