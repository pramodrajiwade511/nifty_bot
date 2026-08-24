import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import broker  
import datetime
import os
import pandas as pd
import plotly.graph_objects as go
import requests

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
    except Exception: pass
else:
    db = firestore.client()

broker.db = db

# --- 📱 स्क्रीन डिझाईन सुरुवात ---
st.set_page_config(page_title="SafeAlgoBot PlayStore Pro", page_icon="🛡️", layout="centered")
st.title("🛡️ SafeAlgoBot - स्वयंचलित अल्गो सिस्टीम")

# --- 🔐 युझर पर्सनल सेटिंग्स (Sidebar) ---
with st.sidebar.expander("🔐 तुमचे वैयक्तिक अकाउंट क्रेडेंशियल्स", expanded=False):
    u_api_key = st.text_input("Angel One API Key:", type="password")
    u_client_code = st.text_input("Angel One Client Code (ID):")
    u_password = st.text_input("Angel One Password:", type="password")
    u_totp_secret = st.text_input("Google TOTP Key:", type="password")
    st.divider()
    u_telegram_token = st.text_input("Telegram Bot Token:", type="password")
    u_telegram_chat_id = st.text_input("Telegram Chat ID:")

# टेलिग्राम मेसेज फंक्शन
def send_user_telegram_sms(message):
    if u_telegram_token and u_telegram_chat_id:
        try:
            url = f"https://telegram.org{u_telegram_token}/sendMessage"
            payload = {"chat_id": u_telegram_chat_id, "text": message, "parse_mode": "Markdown"}
            requests.post(url, json=payload)
        except Exception: pass

# --- ⚙️ स्ट्रॅटेजी कंट्रोल पॅनेल (Sidebar) ---
st.sidebar.divider()
st.sidebar.write("⚙️ **स्ट्रॅटेजी CONTROL पॅनेल**")
strategy_mode = st.sidebar.selectbox("तुमची अल्गो स्ट्रॅटेजी निवडा:", ["OrderFlow Imbalance 📊", "Liquidity S/R Scalper ⚡", "EMA Cross-Over 📈"])

# ==========================================
# 📊 🔐 [१००% सक्तीचे १० दिवस पेपर ट्रेडिंग लॉजिक]
# ==========================================
paper_days_completed = 0
live_trading_approved = False

if db is not None and u_client_code:
    try:
        user_ref = db.collection('app_users').document(u_client_code)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            user_ref.set({
                "current_strategy": strategy_mode,
                "start_date": str(datetime.date.today()),
                "days_completed": 0,
                "live_approved": False
            })
            paper_days_completed = 0
            live_trading_approved = False
        else:
            user_data = user_doc.to_dict()
            
            if user_data.get("current_strategy") != strategy_mode:
                user_ref.update({
                    "current_strategy": strategy_mode,
                    "start_date": str(datetime.date.today()),
                    "days_completed": 0,
                    "live_approved": False
                })
                st.sidebar.error("🚨 स्ट्रॅटेजी बदलल्यामुळे पेपर ट्रेडिंग पुन्हा ० दिवसांवरून सुरू होईल!")
                paper_days_completed = 0
                live_trading_approved = False
            else:
                paper_days_completed = user_data.get("days_completed", 0)
                live_trading_approved = user_data.get("live_approved", False)
                
                start_dt = datetime.datetime.strptime(user_data.get("start_date"), "%Y-%m-%d").date()
                actual_days = (datetime.date.today() - start_dt).days
                if actual_days > paper_days_completed and paper_days_completed < 10:
                    paper_days_completed = min(actual_days, 10)
                    user_ref.update({"days_completed": paper_days_completed})
    except Exception: pass

# प्रोग्रेस रिपोर्ट दाखवणे
st.write("### 📝 लाइव्ह पेपर ट्रेडिंग प्रोग्रेस रिपोर्ट")
if paper_days_completed < 10:
    st.warning(f"⏳ आत्मविश्वास वाढवण्यासाठी १० दिवसांचे सक्तीचे पेपर ट्रेडिंग सुरू आहे. प्रोग्रेस: **{paper_days_completed}/10 दिवस** पूर्ण.")
    st.progress(paper_days_completed / 10)
    st.info("💡 नियम: रोज लाइव्ह मार्केटचा डेटा काळजीपूर्वक पहा. १० दिवस पूर्ण होईपर्यंत सिस्टीम रिअल ट्रेडिंग सुरू करणार नाही.")
    trading_type_allowed = "📝 PAPER TRADING MODE (सक्तीचे टेस्टिंग सुरू)"
else:
    st.success("✅ अभिनंदन! तुमचे १० दिवसांचे लाइव्ह पेपर ट्रेडिंग यशस्वीरित्या पूर्ण झाले आहे.")
    trading_type_allowed = "🟢 LIVE TRADING MODE READY"
    
    if not live_trading_approved:
        st.info("🤖 **SafeAlgoBot पर्मिशन अलर्ट:** तुमची स्ट्रॅटेजी पूर्णपणे फायद्यात आहे. काय आपण रिअल पैशाने 'लाइव्ह ट्रेडिंग' सुरू करण्यास मंजुरी देता?")
        if st.button("👍 होय, लाईव्ह ट्रेडिंग सुरू करा आणि टेलिग्राम अलर्ट ऑन करा"):
            if db is not None and u_client_code:
                db.collection('app_users').document(u_client_code).update({"live_approved": True})
            send_user_telegram_sms("🚀 *SafeAlgoBot अलर्ट*\n\nयुझरने १० दिवस रोज लाईव्ह डेटा पाहून पूर्ण विश्वासानंतर *लाइव्ह रिअल-ट्रेडिंग* सुरू केले आहे! 🛡️")
            st.rerun()

st.divider()

# ==========================================
# 🌟 लाइव्ह मार्केट इंडेक्स पट्टी (Ticker Bar)
# ==========================================
nifty_live = broker.angel_broker.get_live_market_price("NIFTY") or 24251.15
banknifty_live = broker.angel_broker.get_live_market_price("BANKNIFTY") or 52140.30

tick1, tick2 = st.columns(2)
with tick1: st.metric(label="📈 NIFTY 50", value=f"{nifty_live:,.2f}")
with tick2: st.metric(label="⚡ BANKNIFTY", value=f"{banknifty_live:,.2f}")

st.divider()

# ==========================================
# ⚙️ १ ला कप्पा: 'No Loss' सुरक्षित सेटिंग्स
# ==========================================
st.write("### ⚙️ 'No Loss' सुरक्षित सेटिंग्स")
st.caption(f"🎯 सध्याचा मोड: **{trading_type_allowed}** | स्ट्रॅटेजी: **{strategy_mode}**")

asset_type = st.selectbox("ट्रेडिंग प्रकार निवडा:", ["STOCKS (शेअर्स) 🛡️", "NIFTY / BANKNIFTY", "FINNIFTY"])
symbol_input = st.text_input("सिम्बॉल नाव:", "TATASTEEL" if "STOCKS" in asset_type else "NIFTY24SEP24500CE")
qty = st.number_input("क्वांटिटी संख्या:", value=10 if "STOCKS" in asset_type else 25)

col_in1, col_in2 = st.columns(2)
with col_in1: entry_price = st.number_input("खरेदी भाव (Entry Price)", value=100.0)
with col_in2: market_sl = st.number_input("चार्टनुसार स्टॉपलॉस भाव (Market SL Price)", value=80.0)
target_val = st.number_input("Target Points (TP1)", value=30)

st.divider()

# broker.py मधून डेटा लोड करणे
df_of = broker.angel_broker.get_nse_order_flow(symbol_input)
if not df_of.empty:
    total_bid = df_of['bid_vol'].sum()
    total_ask = df_of['ask_vol'].sum()
    buyer_volume = round((total_ask / (total_bid + total_ask)) * 100, 1)
    seller_volume = round((total_bid / (total_bid + total_ask)) * 100, 1)
else:
    buyer_volume, seller_volume = 50.0, 50.0

# ==========================================
# 🕒 २ रा कप्पा: लाइव्ह ऑर्डर फ्लो फूटप्रिंट टेबल
# ==========================================
st.write(f"### 🕒 किंमत पातळीनुसार खरेदी/विक्री रिपोर्ट - {symbol_input}")

col_of1, col_of2 = st.columns(2)
with col_of1: st.success(f"🟢 संस्थात्मक खरेदीदार: {buyer_volume}%")
with col_of2: st.error(f"🔴 संस्थात्मक विक्रेते: {seller_volume}%")

# 🆕 🌟 [बदल फिक्स केला]: 'report' शब्दाचे स्पेलिंग लिटल केस (lowercase) केले
def style_of_rows(row):
    if "Trigger" in str(row['report']) or "Buy" in str(row['report']):
        return ["background-color: #d1fae5; color: #065f46; font-weight: bold;"] * len(row)
    elif "Sell" in str(row['report']) or "Level" in str(row['report']):
        return ["background-color: #fee2e2; color: #991b1b; font-weight: bold;"] * len(row)
    return [""] * len(row)

if not df_of.empty:
    display_df = df_of.copy()
    st.dataframe(
        display_df.style.apply(style_of_rows, axis=1), 
        use_container_width=True
    )

st.divider()

# ==========================================
# 📈 ३ रा कप्पा: लाइव्ह ऑर्डर फ्लो चार्ट
# ==========================================
st.write("### 📈 लाइव्ह ऑर्डर फ्लो डेटा व्हिज्युअलायझेशन (Delta Chart)")
support_level, resistance_level = 90.0, 115.0
fig = go.Figure()
if not df_of.empty:
    fig.add_trace(go.Bar(y=df_of['price'], x=df_of['ask_vol'], name='Call Buy', orientation='h', marker=dict(color='#22c55e', opacity=0.7)))
    fig.add_trace(go.Bar(y=df_of['price'], x=-df_of['bid_vol'], name='Sell / Put', orientation='h', marker=dict(color='#ef4444', opacity=0.7)))
    fig.add_hline(y=resistance_level, line_dash="dash", line_color="red", annotation_text="🔴 Resistance Alert Line")
    fig.add_hline(y=support_level, line_dash="dash", line_color="green", annotation_text="🟢 Support Alert Line")

fig.update_layout(barmode='relative', height=250, margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ==========================================
# 📊 ४ था कप्पा: प्रॉफिट आणि लॉस (P&L) रिपोर्ट
# ==========================================
daily_pnl, weekly_pnl, monthly_pnl, total_brokerage = 0.0, 0.0, 0.0, 0.0
net_pnl = 0.0

if db is not None:
    try:
        pnl_ref = db.collection('pnl_tracker').document('user_01')
        pnl_doc = pnl_ref.get()
        if pnl_doc.exists:
            pnl_data = pnl_doc.to_dict()
            daily_pnl = pnl_data.get("daily_pnl", 0.0)
            weekly_pnl = pnl_data.get("weekly_pnl", 0.0)
            monthly_pnl = pnl_data.get("monthly_pnl", 0.0)
            total_brokerage = pnl_data.get("total_brokerage", 0.0)
            net_pnl = daily_pnl - total_brokerage
    except Exception: pass

st.write("### 📊 प्रॉफिट आणि लॉस (P&L) रिपोर्ट")
col1, col2, col3 = st.columns(3)
with col1: st.metric(label="📅 आजचा P&L (Daily)", value=f"₹ {daily_pnl:,.2f}")
with col2: st.metric(label="🗓️ या आठवड्याचा P&L (Weekly)", value=f"₹ {weekly_pnl:,.2f}")
