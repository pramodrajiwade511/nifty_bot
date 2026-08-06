import os
import requests
import pandas as pd
import pandas_ta as ta
import mplfinance as mpf
from flask import Flask, request
import yfinance as yf
from datetime import datetime
import numpy as np

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

current_trade = None
entry_price = 0.0
stop_loss = 0.0
daily_trades = []

last_gm_date = ""
last_levels_date = ""
current_s1 = None
current_r1 = None
current_pivot = None


def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"Error sending message: {e}")


def send_telegram_chart(image_path, caption_text):
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, 'rb') as photo:
            files = {'photo': photo}
            data = {'chat_id': CHAT_ID, 'caption': caption_text}
            requests.post(url, files=files, data=data, timeout=15)
    except Exception as e:
        print(f"Error sending chart: {e}")


def fix_multiindex(df):
    """yfinance kadhi kadhi MultiIndex columns deta - te fix karnyasathi helper"""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def get_supertrend_columns(st_df):
    """pandas_ta version pramane SUPERT column names badaltat, tyamule dynamic shodhto"""
    st_col = None
    dir_col = None
    for c in st_df.columns:
        if c.startswith('SUPERTd_'):
            dir_col = c
        elif c.startswith('SUPERT_'):
            st_col = c
    return st_col, dir_col


def get_option_strikes(price, signal_type):
    """
    Nifty spot pricevaroon ATM, ITM, OTM strikes kadhto.
    signal_type 'BUY' -> Call (CE) options, 'SELL' -> Put (PE) options
    Strikes 50 chya multiples madhe round kartat.
    """
    atm = round(price / 50) * 50
    option_type = "CE" if signal_type == "BUY" else "PE"

    if option_type == "CE":
        itm = atm - 50   # kami strike call sathi ITM
        otm = atm + 50   # jasta strike call sathi OTM
    else:
        itm = atm + 50   # jasta strike put sathi ITM
        otm = atm - 50   # kami strike put sathi OTM

    return {
        "ATM": f"{atm} {option_type}",
        "ITM": f"{itm} {option_type}",
        "OTM": f"{otm} {option_type}",
    }


def get_targets(entry_price, sl_price, signal_type):
    """
    Risk-Reward vaparun T1, T2, T3 target kadhto.
    Risk = entry ani SL madhla farak. T1=1x risk, T2=2x risk, T3=3x risk.
    """
    risk = abs(entry_price - sl_price)
    if signal_type == 'BUY':
        t1 = round(entry_price + risk * 1, 2)
        t2 = round(entry_price + risk * 2, 2)
        t3 = round(entry_price + risk * 3, 2)
    else:
        t1 = round(entry_price - risk * 1, 2)
        t2 = round(entry_price - risk * 2, 2)
        t3 = round(entry_price - risk * 3, 2)
    return {"T1": t1, "T2": t2, "T3": t3}


def generate_signal_chart(df, signal_type, price_level, sl_price):
    """
    Trading app sarkha professional dark-theme candlestick chart banवतो.
    signal_type: 'BUY', 'SELL', 'BUY_EXIT', 'SELL_EXIT'
    price_level: entry/exit price jithe arrow dakhvaycha
    sl_price: stop loss line
    """
    try:
        chart_df = df.tail(60).copy()
        chart_df.index.name = 'Date'

        is_entry = signal_type in ('BUY', 'SELL')
        is_up = signal_type in ('BUY', 'SELL_EXIT')

        marker_series = [np.nan] * len(chart_df)
        marker_series[-1] = price_level
        arrow_marker = '^' if is_up else 'v'
        arrow_color = '#00e676' if is_up else '#ff1744'

        apds = [
            mpf.make_addplot(marker_series, type='scatter', markersize=220,
                              marker=arrow_marker, color=arrow_color)
        ]

        hlines_list = [sl_price]
        hlines_colors = ['#ffab00']
        if current_s1:
            hlines_list.append(current_s1)
            hlines_colors.append('#2979ff')
        if current_r1:
            hlines_list.append(current_r1)
            hlines_colors.append('#d500f9')

        mc = mpf.make_marketcolors(
            up='#26a69a', down='#ef5350', edge='inherit', wick='inherit', volume='in'
        )
        style = mpf.make_mpf_style(
            base_mpf_style='nightclouds',
            marketcolors=mc,
            facecolor='#131722',
            edgecolor='#131722',
            gridcolor='#2a2e39',
            gridstyle='--',
            figcolor='#131722',
            rc={'axes.labelcolor': 'white', 'xtick.color': 'white', 'ytick.color': 'white'}
        )

        title_map = {
            'BUY': 'NIFTY 50 — BUY CALL SIGNAL',
            'SELL': 'NIFTY 50 — BUY PUT SIGNAL',
            'BUY_EXIT': 'NIFTY 50 — BUY EXIT (SL HIT)',
            'SELL_EXIT': 'NIFTY 50 — SELL EXIT (SL HIT)',
        }

        image_path = f"/tmp/chart_{signal_type}_{datetime.now().strftime('%H%M%S')}.png"

        mpf.plot(
            chart_df,
            type='candle',
            style=style,
            addplot=apds,
            hlines=dict(hlines=hlines_list, colors=hlines_colors, linestyle='-.', linewidths=1.2),
            title=title_map.get(signal_type, 'NIFTY 50'),
            ylabel='Price',
            figsize=(10, 6),
            savefig=dict(fname=image_path, dpi=150, bbox_inches='tight')
        )
        return image_path
    except Exception as e:
        print(f"Error generating chart: {e}")
        return None


def get_levels():
    try:
        df = yf.download(tickers="^NSEI", period="2d", interval="1d", progress=False)
        df = fix_multiindex(df)
        if len(df) >= 2:
            prev_day = df.iloc[-2]
            pivot = (prev_day['High'] + prev_day['Low'] + prev_day['Close']) / 3
            r1 = (2 * pivot) - prev_day['Low']
            s1 = (2 * pivot) - prev_day['High']
            return round(s1, 2), round(r1, 2), round(pivot, 2)
    except Exception as e:
        print(f"Error in get_levels: {e}")
    return None, None, None


def calculate_reports():
    if not daily_trades:
        return "अजून कोणताही ट्रेड पूर्ण झाला नाही."
    today_str = datetime.today().strftime('%Y-%m-%d')
    today_pnl = sum(t['pnl'] for t in daily_trades if t['date'] == today_str)
    total_pnl = sum(t['pnl'] for t in daily_trades)
    total_trades = len(daily_trades)
    weekly_avg = total_pnl / total_trades if total_trades > 0 else 0

    return (
        f"📊 **PERFORMANCE REPORT** 📊\n\n"
        f"🗓️ आजचा नफा/तोटा: ₹{round(today_pnl, 2)}\n"
        f"📈 एकूण झालेले ट्रेड्स: {total_trades}\n"
        f"📉 चालू आठवड्याचा सरासरी नफा: ₹{round(weekly_avg, 2)}"
    )


def check_signals():
    global current_trade, entry_price, stop_loss, daily_trades, last_gm_date, last_levels_date
    global current_s1, current_r1, current_pivot
    try:
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        current_time_str = now.strftime('%H:%M')
        weekday = now.weekday()  # 0=Monday ... 5=Saturday, 6=Sunday

        # Weekend kiva market vel sodun baki veli kahich karaycha nahi
        if weekday >= 5 or current_time_str < "09:00" or current_time_str > "15:35":
            return

        if current_time_str >= "09:00" and current_time_str < "09:15" and last_gm_date != today_str:
            send_telegram_message("Good Morning! Nifty Trading Bot आता सक्रिय (Active) झाला आहे.")
            last_gm_date = today_str

        if current_time_str >= "09:10" and current_time_str < "09:25" and last_levels_date != today_str:
            s1, r1, pivot = get_levels()
            if s1 and r1:
                current_s1, current_r1, current_pivot = s1, r1, pivot
                levels_msg = (
                    f"📊 **NIFTY DAILY LEVELS** 📊\n"
                    f"🗓️ दिनांक: {today_str}\n"
                    f"🔺 Resistance (R1): {r1}\n"
                    f"🎯 Pivot Point: {pivot}\n"
                    f"🔻 Support (S1): {s1}\n"
                )
                send_telegram_message(levels_msg)
                last_levels_date = today_str

        df = yf.download(tickers="^NSEI", period="5d", interval="5m", progress=False)
        df = fix_multiindex(df)
        if df.empty or len(df) < 20:
            return

        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=7, multiplier=3)
        st_col, dir_col = get_supertrend_columns(st)
        if st_col is None or dir_col is None:
            print(f"Error: Supertrend columns not found. Available columns: {st.columns.tolist()}")
            return

        df['ST'] = st[st_col]
        df['ST_DIR'] = st[dir_col]

        latest_price = round(df['Close'].iloc[-1], 2)
        prev_dir = df['ST_DIR'].iloc[-2]
        curr_dir = df['ST_DIR'].iloc[-1]

        trade_closed = False

        if current_trade == 'BUY':
            new_sl = latest_price - 10
            if stop_loss == 0.0 or new_sl > stop_loss:
                stop_loss = round(new_sl, 2)
                send_telegram_message(f"🔁 Stop Loss ट्रेल झाला! नवीन SL: {stop_loss}")
            if latest_price <= stop_loss:
                pnl_generated = (latest_price - entry_price) * 50
                send_telegram_message(f"🔴 BUY EXIT! SL Hit\nExit Price: {latest_price}\nP&L: ₹{pnl_generated}")
                chart_path = generate_signal_chart(df, 'BUY_EXIT', latest_price, stop_loss)
                if chart_path:
                    send_telegram_chart(chart_path, f"BUY EXIT | Exit: {latest_price} | P&L: ₹{pnl_generated}")
                trade_closed = True

        elif current_trade == 'SELL':
            new_sl = latest_price + 10
            if stop_loss == 0.0 or new_sl < stop_loss:
                stop_loss = round(new_sl, 2)
                send_telegram_message(f"🔁 Stop Loss ट्रेल झाला! नवीन SL: {stop_loss}")
            if latest_price >= stop_loss:
                pnl_generated = (entry_price - latest_price) * 50
                send_telegram_message(f"🔴 SELL EXIT! SL Hit\nExit Price: {latest_price}\nP&L: ₹{pnl_generated}")
                chart_path = generate_signal_chart(df, 'SELL_EXIT', latest_price, stop_loss)
                if chart_path:
                    send_telegram_chart(chart_path, f"SELL EXIT | Exit: {latest_price} | P&L: ₹{pnl_generated}")
                trade_closed = True

        if trade_closed:
            daily_trades.append({'date': today_str, 'pnl': pnl_generated})
            current_trade = None
            send_telegram_message(calculate_reports())

        if current_trade is None:
            if prev_dir == -1 and curr_dir == 1:
                current_trade = 'BUY'
                entry_price = latest_price
                stop_loss = entry_price - 15
                strikes = get_option_strikes(entry_price, 'BUY')
                targets = get_targets(entry_price, stop_loss, 'BUY')
                send_telegram_message(
                    f"🟢 **BUY CALL SIGNAL**\nEntry Price: {entry_price}\nInitial SL: {stop_loss}\n\n"
                    f"🎯 Targets:\nT1: {targets['T1']}\nT2: {targets['T2']}\nT3: {targets['T3']}\n\n"
                    f"📌 Option Strikes:\n"
                    f"ATM: {strikes['ATM']}\n"
                    f"ITM: {strikes['ITM']}\n"
                    f"OTM: {strikes['OTM']}"
                )
                chart_path = generate_signal_chart(df, 'BUY', entry_price, stop_loss)
                if chart_path:
                    send_telegram_chart(chart_path, f"BUY CALL | Entry: {entry_price} | SL: {stop_loss} | ATM: {strikes['ATM']}")
            elif prev_dir == 1 and curr_dir == -1:
                current_trade = 'SELL'
                entry_price = latest_price
                stop_loss = entry_price + 15
                strikes = get_option_strikes(entry_price, 'SELL')
                targets = get_targets(entry_price, stop_loss, 'SELL')
                send_telegram_message(
                    f"🔴 **BUY PUT SIGNAL**\nEntry Price: {entry_price}\nInitial SL: {stop_loss}\n\n"
                    f"🎯 Targets:\nT1: {targets['T1']}\nT2: {targets['T2']}\nT3: {targets['T3']}\n\n"
                    f"📌 Option Strikes:\n"
                    f"ATM: {strikes['ATM']}\n"
                    f"ITM: {strikes['ITM']}\n"
                    f"OTM: {strikes['OTM']}"
                )
                chart_path = generate_signal_chart(df, 'SELL', entry_price, stop_loss)
                if chart_path:
                    send_telegram_chart(chart_path, f"BUY PUT | Entry: {entry_price} | SL: {stop_loss} | ATM: {strikes['ATM']}")

    except Exception as e:
        print(f"Error in check_signals: {e}")


@app.route('/')
def home():
    print("Cron-job ping received. Keeping server alive!")
    check_signals()
    return "Bot is running perfectly! Tata Bot is Active.", 200


@app.route('/telegram', methods=['POST'])
def telegram_webhook():
    try:
        update = request.get_json()
        if not update or "message" not in update or "text" not in update["message"]:
            return "OK", 200

        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"].lower().strip()

        if text == "/start":
            reply_message = "😊 Tata Bot Shuru Jhala Aahe!\nLive market signals, /price ani /report sathi ha bot tayar aahe."
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": reply_message})

        elif text == "/price":
            data = yf.download(tickers="^NSEI", period="1d", interval="1m", progress=False)
            data = fix_multiindex(data)
            if not data.empty:
                latest_price = round(data['Close'].iloc[-1], 2)
                reply_message = f"📈 Live Market Price: **Nifty 50: {latest_price}**"
            else:
                reply_message = "❌ Sadhya market data available nahi."
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": reply_message})

        elif text == "/report":
            report_message = calculate_reports()
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={"chat_id": chat_id, "text": report_message})

        return "OK", 200
    except Exception as e:
        print(f"Error: {e}")
        return "Error", 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
