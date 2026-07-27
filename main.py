import os
import time
import schedule
import requests
import telebot

# Telegram Configuration
BOT_TOKEN = "8931528579:AAGyObQKqUUPnQ5jO3oxMB7EF0zvfK7Lzno"
CHAT_ID = "5685619801"

bot = telebot.TeleBot(BOT_TOKEN)

def get_nifty_live_price():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/^NSEI"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        data = response.json()
        price = data['chart']['result'][0]['meta']['regularMarketPrice']
        return round(price, 2)
    except Exception as e:
        print(f"Error fetching price: {e}")
        return None

def morning_start():
    bot.send_message(CHAT_ID, "🌅 Good Morning! Nifty Paper Trading Bot Active.")

def send_signal():
    price = get_nifty_live_price() or 24500
    msg = f"📈 **BUY CALL SIGNAL (NIFTY)**\n\n🎯 Nifty Live Price: {price}\n💡 Paper Trading Signal Triggered!"
    bot.send_message(CHAT_ID, msg, parse_mode="Markdown")

def market_close():
    bot.send_message(CHAT_ID, "⏰ 3:15 PM: Market closing soon. Paper Trading session ended.")

# Schedule Timings
schedule.every().day.at("09:10").do(morning_start)
schedule.every().day.at("09:30").do(send_signal)
schedule.every().day.at("15:15").do(market_close)

print("Bot is running...")
bot.send_message(CHAT_ID, "🚀 Nifty Bot deployed successfully on Render!")

while True:
    schedule.run_pending()
    time.sleep(1)
  
