import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import broker  
import os
import datetime
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
    except Exception as e: pass
else:
    db = firestore.client()

broker.db = db

# --- ✈️ टेलिग्राम मेसेज कॉन्फिगरेशन ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

def send_telegram_sms(message):
    try:
        url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except Exception: pass

# --- ⏰ टाइमर शेड्यूलर्स ---
now_time = datetime.datetime.now().time()
if "morning_sent" not in st.session_state:
    if now_time >= datetime.time(9, 0) and now_time < datetime.time(9, 12):
        send_telegram_sms("Good Morning 🌄🌄🌄🌅🌅\nSafeAlgoBot ऑनलाईन झाला आहे. आजच्या ट्रेडिंगसाठी शुभेच्छा! 🛡️")
        st.session_state.morning_sent = True

if "sr_morning_sent" not in st.session_state:
    if now_time >= datetime.time(9, 12):
        sr_msg = f"📊 *SafeAlgoBot प्री-मार्केट अपडेट (९:१२ AM)*\n\n📈 Resistance: *₹115.00*\n📉 Support: *₹90.00*\n🛡️ सिस्टीम सज्ज आहे."
        send_telegram_sms(sr_msg)
        st.session_state.sr_morning_sent = True

# --- 📱 डॅशबोर्ड स्क्रीनची सुरुवात ---
st.set_page_config(page_title="SafeAlgoBot OrderFlow Pro", page_icon="🛡️", layout="centered")
st.title("🛡️ SafeAlgoBot -  ऑर्डर फ्लो महा-अल्गो")
st.subheader("🤖 ट्रेडिंगव्ह्यू विना चालणारी १००% मोफत ऑटोमॅतिक सिस्टीम")

now = datetime.datetime.now().strftime("%H:%M:%S")
st.caption(f"⚡ लाइव्ह डेटा फीड (Angel One Free Feed) | अपडेट वेळ: **{now}**")

st.divider()

# ==========================================
# ⚙️ १ ला कप्पा: 'No Loss' सुरक्षित सेटिंग्स (Input & Live Tracking)
# ==========================================
st.write("### ⚙️ 'No Loss' सुरक्षित सेटिंग्स")
asset_type = st.selectbox("ट्रेडिंग प्रकार निवडा:", ["STOCKS (शेअर्स) 🛡️", "NIFTY / BANKNIFTY", "FINNIFTY"])
symbol_input = st.text_input("सिम्बॉल नाव:", "TATASTEEL" if "STOCKS" in asset_type else "NIFTY24SEP24500CE")
qty = st.number_input("क्वांटिटी संख्या:", value=10 if "STOCKS" in asset_type else 25)

col_in1, col_in2 = st.columns(2)
with col_in1: entry_price = st.number_input("खरेदी भाव (Entry Price)", value=100.0)
with col_in2: market_sl = st.number_input("चार्टनुसार स्टॉपलॉस भाव (Market SL Price)", value=80.0)
target_val = st.number_input("Target Points (TP1)", value=30)

# 🔗 🆕 थेट Angel One वरून खऱ्या मार्केटची लाईव्ह किंमत (LTP) ओढणे
live_ltp = broker.angel_broker.get_live_market_price(symbol_input)
st.metric(label=f"📈 {symbol_input} लाइव्ह मार्केट किंमत (NSE LTP)", value=f"₹ {live_ltp:.2f}")

# 🛡️ ॲडव्हान्स ऑटो-ट्रेलिंग लॉजिक
active_sl = market_sl
trailing_status = "सुरुवातीचा स्टॉपलॉस ॲक्टिव्ह आहे."

if live_ltp >= entry_price + 10.0:
    active_sl = entry_price  # स्टॉपलॉस थेट १०० वर शिफ्ट (Break-Even)
    trailing_status = "🚀 ब्रेक-इव्हन ॲक्टिव्ह! स्टॉपलॉस खरेदी भावावर (₹100) सेव्ह झाला (No Loss झोन)."
    
    extra_points = live_ltp - (entry_price + 10.0)
    multiplier = int(extra_points // 10)
    if multiplier > 0:
        active_sl = entry_price + (multiplier * 10)
        trailing_status = f"🔥 मार्केट वर गेले! स्टॉपलॉस ट्रेल होऊन **₹{active_sl}** वर लॉक झाला."

st.info(f"📋 **सध्याचा सुरक्षित स्टॉपलॉस:** ₹{active_sl} | {trailing_status}")

st.divider()

# broker.py मधून ऑर्डर फ्लो डेटा ओढणे
df_of = broker.angel_broker.get_nse_order_flow(symbol_input)
df_of['signal'] = df_of['report'].apply(lambda x: "BUY" if "Buy" in str(x) else ("SELL" if "Sell" in str(x) else None))

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
with col_of1: st.success(f"🟢 संस्थात्मक खरेदीदार (Big Buyers): {buyer_volume}%")
with col_of2: st.danger(f"🔴 संस्थात्मक विक्रेते (Big Sellers): {seller_volume}%")

def style_of_rows(row):
    if "BUY" in str(row['बॉट सिग्नल']):
        return ["background-color: #d1fae5; color: #065f46; font-weight: bold;"] * len(row)
    elif "SELL" in str(row['बॉट सिग्नल']):
        return ["background-color: #fee2e2; color: #991b1b; font-weight: bold;"] * len(row)
    return [""] * len(row)

display_df = df_of.copy()
display_df.columns = ["किंमत (Price)", "विक्री (Bid Vol)", "खरेदी (Ask Vol)", "अहवाल (Report)", "बॉट सिग्नल"]
st.dataframe(display_df.style.apply(style_of_rows, axis=1), use_container_width=True)

st.divider()

# ==========================================
# 📈 ३ रा कप्पा: लाइव्ह ऑर्डर फ्लो चार्ट (अलर्ट आणि S/R लाईन्ससह)
# ==========================================
st.write("### 📈 लाइव्ह ऑर्डर फ्लो डेटा व्हिज्युअलायझेशन (Delta Chart)")
support_level, resistance_level = 90.0, 115.0
fig = go.Figure()
if not df_of.empty:
    fig.add_trace(go.Bar(y=df_of['price'], x=df_of['ask_vol'], name='Call Buy', orientation='h', marker=dict(color='#22c55e', opacity=0.7)))
    fig.add_trace(go.Bar(y=df_of['price'], x=-df_of['bid_vol'], name='Sell / Put', orientation='h', marker=dict(color='#ef4444', opacity=0.7)))
    
    # 🆕 चार्टवर रेझिस्टन्स आणि सपोर्ट लेव्हल अलर्ट लाईन्स मार्क करणे
    fig.add_hline(y=resistance_level, line_dash="dash", line_color="red", annotation_text="🔴 Resistance Alert Line (₹115)")
    fig.add_hline(y=support_level, line_dash="dash", line_color="green", annotation_text="🟢 Support Alert Line (₹90)")

    for idx, row in df_of.iterrows():
        if row['signal'] == "BUY":
            fig.add_annotation(x=row['ask_vol']+2000, y=row['price'], text="🟢 BUY SIGNAL", showarrow=False, font=dict(color="green", size=12, family="Arial Black"))
        elif row['signal'] == "SELL":
            fig.add_annotation(x=-row['bid_vol']-2000, y=row['price'], text="🔴 SELL SIGNAL", showarrow=False, font=dict(color="red", size=12, family="Arial Black"))

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
with col3: st.metric(label="📆 या महिन्याचा P&L (Monthly)", value=f"₹ {monthly_pnl:,.2f}")
st.write(f"ℹ️ एकूण ब्रोकरेज: ₹{total_brokerage:,.2f} | **निव्वळ नफा (Net): ₹{net_pnl:,.2f}**")

st.divider()

# --- ⚠️ सिस्टीम निर्णय स्टेटस ---
st.write("### ⚠️ सिस्टीम निर्णय स्टेटस")
if buyer_volume >= 60.0:
    st.success(f"🚀 [ऑटोमॅतिक ORDER READY]: खरेदीदार ६०% पेक्षा जास्त आहेत! {symbol_input} मध्ये BUY ट्रेडसाठी सिस्टीम तयार आहे.")
else:
    st.warning("🚨 *मार्केट साइडवेज आहे !*")

if st.button("🚀 चाचणीसाठी मॅन्युअल ट्रेड ट्रिगर करा", use_container_width=True):
    st.success("मॅन्युअल टेस्ट ORDER सिस्टीम सुरू झाली!")
    trade_sms = f"🔔 *SafeAlgoBot - ट्रेड अलर्ट* 🚀\n\n📦 सिम्बॉल: `{symbol_input}`\n🟢 एन्ट्री भाव: *₹{entry_price}*\n🛡️ स्टॉपलॉस: *₹{market_sl}*\n🎯 टार्गेट: *₹{entry_price + target_val}*\n📈 रेजिस्टेंस: ₹{resistance_level} | 📉 सपोर्ट: ₹{support_level}"
    send_telegram_sms(trade_sms)
    st.toast("ट्रेडची संपूर्ण माहिती टेलिग्रामवर पाठवली आहे! ✅")
