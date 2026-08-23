import streamlit as st
import broker

# ॲपचा मुख्य इंटरफेस (UI) सेटअप
st.set_page_config(page_title="Nifty Bot Dashboard", page_icon="📈", layout="centered")

st.title("📈 Nifty Trading Bot")
st.subheader("तुमचा पर्सनल ट्रेडिंग डॅशबोर्ड")

# १. ब्रोकर सेशन स्टेटस (डाव्या बाजूचा मेन्यू)
st.sidebar.header("ब्रोकर सेटिंग्स")
api_key = st.sidebar.text_input("Angel One API Key", type="password")
client_id = st.sidebar.text_input("Client ID")
mpin = st.sidebar.text_input("MPIN (4 Digit)", type="password")
totp_secret = st.sidebar.text_input("TOTP Secret Key", type="password")

if st.sidebar.button("Angel One लॉगिन करा"):
    if not all([api_key, client_id, mpin, totp_secret]):
        st.sidebar.error("कृपया सर्व माहिती भरा!")
    else:
        session = broker.get_smart_api_session(api_key, client_id, mpin, totp_secret)
        if session:
            st.sidebar.success("✅ लॉगिन यशस्वी झाले!")
        else:
            st.sidebar.error("❌ लॉगिन फेल! क्रेडेंशियल्स तपासा.")

# २. मॅन्युअल ऑर्डर पॅनेल (मुख्य स्क्रीन)
st.write("### ⚡ मॅन्युअल ऑर्डर पॅनेल")
symbol = st.text_input("ट्रेडिंग सिम्बॉल (उदा. NIFTY)", "NIFTY")
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
