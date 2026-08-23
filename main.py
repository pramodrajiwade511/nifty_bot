import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import broker

# १. फायरबेस सेटअप (जर आधीच नसेल तर)
if not firebase_admin._apps:
    cred = credentials.Certificate('firebase_key.json') # तुमच्या की फाईलचे नाव
    firebase_admin.initialize_app(cred)

db = firestore.client()

# २. ॲपचा मुख्य इंटरफेस (UI)
st.set_page_config(page_title="Nifty Bot Dashboard", page_icon="📈", layout="centered")

st.title("📈 Nifty Trading Bot")
st.subheader("तुमचा पर्सनल ट्रेडिंग डॅशबोर्ड")

# ३. ब्रोकर सेशन स्टेटस
st.sidebar.header("ब्रोकर सेटिंग्स")
if st.sidebar.button("Angel One लॉगिन तपासा"):
    session = broker.get_smart_api_session()
    if session:
        st.sidebar.success("✅ एंजेल वन कनेक्टेड आहे!")
    else:
        st.sidebar.error("❌ लॉगिन फेल! सेटिंग्स तपासा.")

# ४. लाईव्ह डेटा डिस्प्ले
st.divider()
st.columns(1)
st.metric(label="NIFTY LIVE LTP", value=f"₹ {broker.NSE_LIVE_LTP}")

# ५. मॅन्युअल ऑर्डर पॅनेल
st.write("### ⚡ मॅन्युअल ऑर्डर पॅनेल")
symbol = st.text_input("ट्रेडिंग सिम्बॉल (उदा. NIFTY24AUG24500CE)", "NIFTY")
qty = st.number_input("क्वांटिटी (Lots)", min_value=1, value=25, step=25)
price = st.number_input("प्राईज (मार्केटसाठी ० ठेवा)", min_value=0.0, value=0.0)

col1, col2 = st.columns(2)
with col1:
    if st.button("🟢 BUY ORDER", use_container_width=True):
        res = broker.place_order(symbol, "NFO", "BUY", qty, price)
        if res.get("status"):
            st.success(f"ऑर्डर सक्सेस! ID: {res.get('order_id')}")
        else:
            st.error(f"फेल: {res.get('message')}")

with col2:
    if st.button("🔴 SELL ORDER", use_container_width=True):
        res = broker.place_order(symbol, "NFO", "SELL", qty, price)
        if res.get("status"):
            st.success(f"ऑर्डर सक्सेस! ID: {res.get('order_id')}")
        else:
            st.error(f"फेल: {res.get('message')}")
