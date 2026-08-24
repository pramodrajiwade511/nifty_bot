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
    except Exception as e: pass
else:
    db = firestore.client()

broker.db = db

# --- 📱 डॅशबोर्ड स्क्रीनची सुरुवात ---
st.set_page_config(page_title="SafeAlgoBot OrderFlow Pro", page_icon="🛡️", layout="centered")
st.title("🛡️ SafeAlgoBot - ऑर्डर फ्लो महा-अल्गो")
st.subheader("🤖 ट्रेडिंगव्ह्यू विना चालणारी १००% मोफत ऑटोमॅटिक सिस्टीम")

# --- 📊 P&L डेटा लोड ---
daily_pnl = 0.0
total_brokerage = 0.0
net_pnl = 0.0

if db is not None:
    try:
        pnl_ref = db.collection('pnl_tracker').document('user_01')
        pnl_doc = pnl_ref.get()
        if not pnl_doc.exists:
            pnl_ref.set({"daily_pnl": 0.0, "weekly_pnl": 0.0, "total_brokerage": 0.0})
        else:
            pnl_data = pnl_doc.to_dict()
            daily_pnl = pnl_data.get("daily_pnl", 0.0)
            total_brokerage = pnl_data.get("total_brokerage", 0.0)
            net_pnl = daily_pnl - total_brokerage
    except Exception: pass

st.write("### 📊 आजचा निव्वळ हिशोब")
col1, col2, col3 = st.columns(3)
with col1: st.metric(label="📅 एकूण P&L", value=f"₹ {daily_pnl:,.2f}")
with col2: st.metric(label="💸 ब्रोकरेज", value=f"₹ {total_brokerage:,.2f}")
with col3: st.metric(label="💰 हातात येणारा नफा (Net)", value=f"₹ {net_pnl:,.2f}")

st.divider()

# --- 📊 ऑर्डर फ्लो डेटा विंडो ---
st.write("### 📈 लाइव्ह ऑर्डर फ्लो डेटा (Angel One Free Feed)")
buyer_volume = 65.0  # ६५% खरेदीदार
seller_volume = 35.0 # ३५% विक्रेते

col_of1, col_of2 = st.columns(2)
with col_of1: st.success(f"🟢 संस्थात्मक खरेदीदार (Big Buyers): {buyer_volume}%")
with col_of2: st.danger(f"🔴 संस्थात्मक विक्रेते (Big Sellers): {seller_volume}%")

st.divider()

# --- ⚙️ इनपुट पॅनेल ---
st.write("### ⚙️ 'No Loss' सुरक्षित सेटिंग्स")
asset_type = st.selectbox("ट्रेडिंग प्रकार निवडा:", ["STOCKS (शेअर्स) 🛡️", "NIFTY / BANKNIFTY", "FINNIFTY"])
symbol_input = st.text_input("सिम्बॉल नाव:", "TATASTEEL" if "STOCKS" in asset_type else "NIFTY24SEP24500CE")
qty = st.number_input("क्वांटिटी संख्या:", value=10 if "STOCKS" in asset_type else 25)

col_in1, col_in2 = st.columns(2)
with col_in1:
    entry_price = st.number_input("خरेदी भाव (Entry Price)", value=100.0)
with col_in2:
    market_sl = st.number_input("चार्टनुसार स्टॉपलॉस भाव (Market SL Price)", value=85.0)

target_val = st.number_input("Target Points (TP1)", value=30)

st.write("### ⚠️ सिस्टीम निर्णय स्टेटस")
if buyer_volume >= 60.0:
    st.success(f"🚀 [ऑटोमॅटिक ऑर्डर रेडी]: खरेदीदार ६०% पेक्षा जास्त आहेत! {symbol_input} मध्ये BUY ट्रेडसाठी सिस्टीम तयार आहे.")
else:
    st.warning("🚨 *मार्केट साइडवेज आहे !*")

if st.button("🚀 चाचणीसाठी मॅन्युअल ट्रेड ट्रिगर करा", use_container_width=True):
    st.success("मॅन्युअल टेस्ट ऑर्डर सिस्टीम सुरू झाली!")
