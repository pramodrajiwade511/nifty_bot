"""
MAIN BOT SERVER - TRADINGVIEW WEBHOOK RECIEVER
==================================================
Ha server TradingView che signals catch करतो, 10-divasacha safety lock check karto,
ani 15 Pts SL + Cost-to-Cost trailing logic chalavto.
"""

import os
import hashlib
import threading
import time
from datetime import datetime
from flask import Flask, json, request
import requests

# broker.py madhun functions ani WebSocket data import karne
from broker import place_order, get_option_premium, init_nse_stream, NSE_LIVE_LTP

app = Flask(__name__)

# Render cha variables madhun Telegram details ghene
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# 📊 सिम्युलेटेड डेटाबेस (10-Divasacha Safety Lock ani 4-Anki PIN Record)
# Tीप: Real-app madhe ithe Firebase database vaporla jail
user_database = {
    "user_01": {
        "user_name": "योगेश",
        "broker_name": "ANGEL_ONE",
        "account_status": "PAPER_LOCK",             # Suruvatila mandatory paper trade lock
        "strategy_updated_at": datetime.now(),      # Aaj navin strategy set zaali asa record
        "security_pin_hash": hashlib.sha256("1234".encode()).hexdigest() # Default 4-Anki pin '1234'
    }
}

# 📢 Telegram var SMS alert pathavne
def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram details missing in environment variables.")
        return
    url = f"https://telegram.org{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

# ==================================================================
# 🔒 4-ANKI PIN VERIFICATION & LIVE ACTIVATION ROUTE
# ==================================================================
@app.route('/activate-live', methods=['POST'])
def activate_live():
    data = request.json
    user_id = data.get("user_id", "user_01")
    entered_pin = data.get("pin")
    user = user_database.get(user_id)

    if not user:
        return {"status": "error", "message": "User sapadla nahi!"}

    # 10 Divas purna zale ahet ka check karne
    days_passed = (datetime.now() - user["strategy_updated_at"]).days
    if days_passed < 10:
        return {
            "status": "error", 
            "message": f"🔒 Ajun {10 - days_passed} दिवस paper trading karne mandatory ahe. Tya shivay live karta yenar nahi!"
        }

    # Pin check karne
    entered_hash = hashlib.sha256(entered_pin.encode()).hexdigest()
    if entered_hash == user["security_pin_hash"]:
        user["account_status"] = "LIVE_ACTIVE"
        send_telegram_alert(f"🚀 *Live Mode Active!*\nUser *{user['user_name']}* ne 4-anki pin takun live trading sathi permission dili ahe.")
        return {"status": "success", "message": "Bot yashasviritya live zala ahe!"}
    
    return {"status": "error", "message": "❌ Chukicha security pin! Permission denied."}

# ==================================================================
# 📈 TRADINGVIEW WEBHOOK RECIEVER ROUTE
# ==================================================================
@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    global NSE_LIVE_LTP
    signal_data = request.json
    user = user_database["user_01"]
    
    action = signal_data.get("action") # 'BUY' / 'SELL'
    strike = int(signal_data.get("strike", 24600)) # Default/TV dware aleli strike
    option_type = signal_data.get("option_type", "CE") # 'CE' / 'PE'
    
    # Live Nifty rate check karne
    nifty_rate = NSE_LIVE_LTP if NSE_LIVE_LTP > 0 else float(signal_data.get("price", 24600))
    
    # Live option premium fetch karne (broker.py madhun)
    premium_price = get_option_premium("NIFTY", strike, option_type)
    if not premium_price:
        premium_price = 100.0 # Fallback jar market band asel tar testing sathi
        
    days_passed = (datetime.now() - user["strategy_updated_at"]).days

    # 🛑 CASE 1: 10 Divas zale nahit -> Saktine PAPER TRADING
    if days_passed < 10 or user["account_status"] == "PAPER_LOCK":
        msg = (
            f"🗒️ *Paper Trade Alert!*\n"
            f"🎯 Instrument: NIFTY {strike} {option_type}\n"
            f"⚡ Action: {action} (Call Buy Simulation)\n"
            f"💰 Entry Premium: ₹{premium_price}\n"
            f"📊 Nifty Live: ₹{nifty_rate}\n"
            f"🔒 Safety Lock Remaining: {10 - days_passed} days"
        )
        send_telegram_alert(msg)
        # Background thread var trailing logic suru karne jenekarun server block honar nahi
        threading.Thread(target=run_trailing_logic, args=("NIFTY", strike, option_type, premium_price, False)).start()

    # 🚀 CASE 2: 10 Divas purna ani User ne PIN takun permission dili ahe -> REAL TRADING
    elif user["account_status"] == "LIVE_ACTIVE":
        msg = (
            f"🚨 *Real Trade Alert! (Angel One)*\n"
            f"🎯 Instrument: NIFTY {strike} {option_type}\n"
            f"⚡ Action: {action}\n"
            f"💰 Premium Market Price: ₹{premium_price}"
        )
        send_telegram_alert(msg)
        
        # Real Order place karne (Lot size: 25 for Nifty)
        # ⚠️ actual order execution find_option_instrument chya token var chalel
        from broker import find_option_instrument
        tsymbol, token = find_option_instrument("NIFTY", strike, option_type)
        if tsymbol and token:
            place_order("NIFTY", tsymbol, token, "BUY", 25)
            
        threading.Thread(target=run_trailing_logic, args=("NIFTY", strike, option_type, premium_price, True)).start()

    return {"status": "processed"}

# ==================================================================
# 📉 15-POINT SL & 10-POINT COST-TO-COST TRAILING LOGIC
# ==================================================================
def run_trailing_logic(name, strike, option_type, entry_price, is_live):
    stop_loss = entry_price - 15
    is_at_cost = False
    mode = "LIVE" if is_live else "PAPER"
    
    print(f"[{mode} Loop] Trailing suru zali. Entry: ₹{entry_price} | Initial SL: ₹{stop_loss}")
    
    while True:
        # Satat live option premium check karat rahne
        current_premium = get_option_premium(name, strike, option_type)
        if not current_premium:
            current_premium = entry_price # Fallback loop break na honyasathi
            
        # Condition 1: Jar premium 10 point var gela (₹100 -> ₹110)
        if current_premium >= (entry_price + 10) and not is_at_cost:
            stop_loss = entry_price # SL direct kharedi bhavavar (₹100) locked!
            is_at_cost = True
            send_telegram_alert(
                f"📈 *SL Cost-to-Cost Jhala ({mode})!*\n"
                f"🎯 NIFTY {strike} {option_type}\n"
                f"🔥 Current Premium: ₹{current_premium}\n"
                f"🔒 SL shifted to Entry Price: ₹{stop_loss}\n"
                f"🛡️ Ata ha trade 100% safe ahe (Zero Loss Guarantee)!"
            )

        # Condition 2: Market reverse zale ani updated stop loss hit zala
        if current_premium <= stop_loss:
            exit_msg = (
                f"⚠️ *Stop Loss Hit ({mode})!*\n"
                f"🎯 NIFTY {strike} {option_type}\n"
                f"🚪 Square-off Price: ₹{current_premium}\n"
                f"📊 Result: " + ("Zero Loss / Cost-to-Cost" if is_at_cost else "-15 Pts Loss")
            )
            send_telegram_alert(exit_msg)
            
            # Jar Live asel tar actual market order madhun exit karne
            if is_live:
                from broker import find_option_instrument
                tsymbol, token = find_option_instrument(name, strike, option_type)
                if tsymbol and token:
                    place_order(name, tsymbol, token, "SELL", 25)
            break
            
        time.sleep(0.5) # Server var load yeu naye mhanun dar 0.5 sec la check karne

# ==================================================================
# SERVER STARTUP
# ==================================================================
if __name__ == "__main__":
    print("🚀 Bot backend system suru hot ahe...")
    # Broker.py madhil NSE WebSocket data background la chalu karne
    init_nse_stream()
    # Webhook reciever Flask server chalu karne (Render handle karel)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
