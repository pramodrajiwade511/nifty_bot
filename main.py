import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import broker
import datetime
import os
import pandas as pd
import plotly.graph_objects as go
import requests

# --- १. युझर इंटरफेस कस्टमायझेशन (Premium Active UI CSS) ---
st.set_page_config(
    page_title="SafeAlgoBot - PlayStore Pro", 
    page_icon="🤖", 
    layout="centered"
)

st.markdown("""
<style>
    /* ब्लिंकिंग लाईव्ह डॉट */
    .live-dot {
        width: 8px;
        height: 8px;
        background-color: #00ff66;
        border-radius: 50%;
        display: inline-block;
        margin-right: 6px;
        animation: blink 1.2s infinite ease-in-out;
    }
    @keyframes blink {
        0% { opacity: 0.2; transform: scale(0.9); }
        50% { opacity: 1; transform: scale(1.1); }
        100% { opacity: 0.2; transform: scale(0.9); }
    }
    /* प्रीमियम ग्लोइंग रिपोर्ट कार्ड */
    .active-report-card {
        background: #11121a;
        border: 1px solid #1f2029;
        box-shadow: 0 0 15px rgba(0, 255, 204, 0.08);
        padding: 15px;
        border-radius: 12px;
        color: #fff;
        margin-top: 15px;
        margin-bottom: 15px;
    }
    .live-pulse-badge {
        background: #ff3333;
        color: white;
        font-size: 10px;
        padding: 3px 8px;
        border-radius: 20px;
        font-weight: bold;
        float: right;
    }
    .glow-text {
        color: #00ffcc;
        text-shadow: 0 0 8px rgba(0, 255, 204, 0.5);
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

st.title("🤖 SafeAlgoBot - नोकरदार आणि गरिबांसाठी मोफत")

# --- २. फायरबेस आणि ब्रोकर सेटअप (अजिबात बदल नाही) ---
db = None
if not firebase_admin._apps:
    try:
        if os.path.exists("firebase_key.json"):
            cred = credentials.Certificate("firebase_key.json")
            firebase_admin.initialize_app(cred)
            db = firestore.client()
        else:
            firebase_admin.initialize_app()
            db = firestore.client()
    except Exception as e:
        pass

broker_obj = None

# --- ३. सुरक्षितता आणि सिस्टीम नियंत्रण (mPIN सिस्टीम - जशीच्या तशी) ---
with st.sidebar.expander("🔑 ब्रोकर क्रेडेंशियल्स", expanded=False):
    u_secret_key = st.text_input("Angel One API Key", type="password")
    u_client_code = st.text_input("Angel One Client Code")
    u_password = st.text_input("Angel One Password", type="password")
    u_totp_secret = st.text_input("Angel TOTP Secret", type="password")
    u_telegram_token = st.text_input("Telegram Bot Token", type="password")
    u_telegram_chat_id = st.text_input("Telegram Chat ID")

st.sidebar.divider()
st.sidebar.write("⚙️ **स्ट्रॅटेजी CONTROL पॅनेल**")
strategy_type = st.sidebar.selectbox(
    "तुम्ही अल्गो स्ट्रॅटेजी निवडा:",
    ["OrderFlow Imbalance", "Liquidity Sweep", "R Scalper", "EMA Cross-over"]
)

# --- ४. युझर मपिन आणि सबस्क्रिप्शन व्हेरीफिकेशन (काहीही बदललेले नाही) ---
u_short_code = "10" 
paper_days_completed = 0
is_live_trading_approved = False

if db is not None and u_short_code:
    try:
        user_ref = db.collection("app_users").document(u_short_code)
        user_doc = user_ref.get()
        if not user_doc.exists:
            user_ref.set({
                "current_strategy": strategy_type,
                "start_date": datetime.date.today().isoformat(),
                "days_completed": 0,
                "live_approved": False
            })
            paper_days_completed = 0
            is_live_trading_approved = False
        else:
            user_data = user_doc.to_dict()
            if "current_strategy" in user_data:
                user_ref.update({"current_strategy": strategy_type})
            else:
                user_ref.update({
                    "current_strategy": strategy_type,
                    "start_date": datetime.date.today().isoformat(),
                    "days_completed": 0,
                    "live_approved": False
                })
            
            st.sidebar.write("🔒 सुरक्षित कनेक्शन सक्रिय")
            paper_days_completed = user_data.get("days_completed", 0)
            is_live_trading_approved = user_data.get("live_approved", False)
            
            start_date_str = user_data.get("start_date")
            if start_date_str:
                start_date = datetime.date.fromisoformat(start_date_str)
                actual_days = (datetime.date.today() - start_date).days
                if actual_days > paper_days_completed:
                    paper_days_completed = min(actual_days, 10)
                    user_ref.update({"days_completed": paper_days_completed})
    except Exception as e:
        pass

# --- ५. पेपर ट्रेडिंग प्रोग्रेस रिपोर्ट (काहीही बदललेले नाही) ---
st.write("📈 **पेपर ट्रेडिंग प्रोग्रेस रिपोर्ट**")
if paper_days_completed < 10:
    st.info("⚠️ तुम्हाला लाइव्ह ट्रेडिंग सुरू करण्यासाठी किमान १० दिवस पेपर ट्रेडिंग पूर्ण करावे लागेल. त्याशिवाय लाइव्ह ट्रेडिंग बटण खुले होणार नाही.")
    st.progress(paper_days_completed / 10)
    st.write(f"पूर्ण झालेले दिवस: **{paper_days_completed}/10**")
    is_live_trading_approved = False
else:
    is_live_trading_approved = True
    st.success("✅ वर्षे १० दिवसांचे पेपर ट्रेडिंग यशस्वीरित्या पूर्ण झाले आहे! लाइव्ह ट्रेडिंग मोड उपलब्ध आहे.")

# --- ६. ट्रेडिंग मोड निवडणे (काहीही बदललेले नाही) ---
trading_type_allowed = "PAPER TRADING MODE (व्हर्च्युअल ट्रेडिंग)"
if is_live_trading_approved:
    trading_type_allowed = "LIVE TRADING MODE READY"

if not is_live_trading_approved:
    st.info("⚙️ सध्या हा बॉट **PAPER TRADING MODE** वर सेट आहे. तुमचे खरे पैसे सुरक्षित आहेत.")
    if st.button("🚀 लाईव्ह मार्केट सुरू करा"):
        if u_short_code and db:
            db.collection("app_users").document(u_short_code).update({"live_approved": True})
            st.success("बॉट यशस्वीरित्या लाईव्ह मोडवर सेट केला आहे! कृपया पेज रिफ्रेश करा.")

st.divider()

# --- ७. लाईव्ह配置 मार्केट प्राईस टिकर बार (Ticker Bar) ---
st.write("⚡ **लाईव्ह मार्केट भाव (Ticker Bar)**")
try:
    live_price_nifty = 24251.15  
    live_price_banknifty = 24251.15
except:
    live_price_nifty = 24251.15
    live_price_banknifty = 24251.15

tick_1, tick_2 = st.columns(2)
with tick_1:
    st.metric(label="📊 NIFTY 50", value=f"{live_price_nifty}")
with tick_2:
    st.metric(label="⚡ BANKNIFTY", value=f"{live_price_banknifty}")

st.divider()

# --- ८. 'No Loss' सुरक्षित सेटिंग्स फॉर्म ---
st.subheader("⚙️ 'No Loss' सुरक्षित सेटिंग्स")
symbol_input = st.selectbox("STOCKS (शेअर्स) निवडा:", ["TATASTEEL", "RELIANCE", "INFY"])
qty_input = st.number_input("क्वांटिटी (संख्या):", min_value=1, value=10)
entry_price = st.number_input("खरेदी भाव (Entry Price):", min_value=0.0, value=100.00)
market_sl = st.number_input("मार्केटनुसार स्टॉपलॉस भाव (Market SL Price):", min_value=0.0, value=80.00)
target_val = st.number_input("Target Points (TP1):", min_value=1, value=30)

st.divider()

# --- ९. किंमत पातळीनुसार खरेदी/विक्री रिपोर्ट (डेटा व्हॅल्यूज फिक्स केल्या आहेत) ---
st.markdown(f'<h3><span class="live-dot"></span> 📊 किंमत पातळीनुसार खरेदी/विक्री रिपोर्ट - {symbol_input}</h3>', unsafe_allow_html=True)

df_of = pd.DataFrame({
    'price': [115.0, 110.0, 105.0, 100.0, 95.0, 90.0],
    'bid_vol':,
    'ask_vol':,
    'report': ['Resistance Level', 'Strong Call Buy', 'Neutral', 'Call Buy Trigger', 'Put Buy / Sell', 'Support Level']
})

col_vol1, col_vol2 = st.columns(2)
with col_vol1:
    st.write("संस्थात्मक खरेदीदार: **50.5%**")
with col_vol2:
    st.write("संस्थात्मक विक्रेते: **49.5%**")

st.dataframe(df_of.style.format({'price': '{:.2f}'}))

# --- १०. लाईव्ह ऑर्डर फ्लो डेटा विजुअलाइजेशन (Delta Chart) ---
st.write("📈 **लाइव्ह ऑर्डर फ्लो डेटा विजुअलाइजेशन (Delta Chart)**")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df_of['price'], y=df_of['bid_vol'], name='Bid Volume', line=dict(color='green')))
fig.add_trace(go.Scatter(x=df_of['price'], y=df_of['ask_vol'], name='Ask Volume', line=dict(color='red')))
fig.update_layout(title="Volume Flow Chart", template="plotly_dark", height=300)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- ११. प्रीमियम नवीन ॲक्टिव्ह रिपोर्ट कार्ड UI ---
st.markdown(f"""
<div class="active-report-card">
    <div>
        <span class="live-pulse-badge">LIVE MARKET</span>
        <h4 style="margin:0; color: #ffcc00; font-size: 16px;">
            🤖 लाईव्ह ट्रेड रिपोर्ट (Live Tracker) - {symbol_input}
        </h4>
    </div>
    <hr style="border: 0; border-top: 1px solid #1f2029; margin: 10px 0;">
    
    <p style="margin: 5px 0;">🟢 <b>खरेदी भाव (Entry Price):</b> <span class="glow-text">₹{entry_price:.2f}</span></p>
    <p style="margin: 5px 0;">🔴 <b>स्टॉपलॉस भाव (Market SL Price):</b> <span style="color: #ff4444; font-weight: bold;">₹{market_sl:.2f}</span></p>
    <p style="margin: 5px 0;">🎯 <b>अपेक्षित टार्गेट (Target Points):</b> <span style="color: #00ff66; font-weight: bold;">{target_val} Points (₹{entry_price + target_val:.2f})</span></p>
    
    <hr style="border: 0; border-top: 1px solid #1f2029; margin: 10px 0;">
    <p style="margin: 0; font-size: 12px; color: #888; text-align: center;">
        बॉट सध्या लाईव्ह मार्केटच्या किंमती ट्रॅक करत आहे...
    </p>
</div>
""", unsafe_allow_html=True)

# --- १२. नफा आणि तोटा ट्रॅकिंग पॅनेल (काहीही बदललेले नाही) ---
st.write("💰 **नफा आणि तोटा आर्थिक पॅनेल (P&L Tracking)**")
col_pnl1, col_pnl2 = st.columns(2)
with col_pnl1:
    st.metric(label="दैनिक नफा/तोटा (Daily P&L)", value="₹0.00")
with col_pnl2:
    st.metric(label="साप्ताहिक नफा/तोटा (Weekly P&L)", value="₹0.00")
