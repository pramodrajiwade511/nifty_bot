# EMA_STRADDLE mode — FAKT ADD kara, kahihi existing code badalू naka

## 1. STRATEGY_MODE cha comment update kara (fakt he ek line badla)

FIND:
```python
STRATEGY_MODE = "COMBINED"
```

REPLACE WITH:
```python
STRATEGY_MODE = "EMA_STRADDLE"  # navीn mode - khali dilela function vaparto
```

(Agodar STRATEGY_MODE veगळं kahi asel — jase "EMA_CROSS" kiva "STRADDLE" — tar
fakt tyacha VALUE "EMA_STRADDLE" kara, baki tya line varchा comment jasach thevu shakता.)


## 2. Ha navीn function tumchya app.py/main.py cha shevटी paste kara
(existing kuthlyahi function la dhakka na lavता, fakt file cha शेवटी `if __name__ ==
"__main__":` cha AADHI paste kara)

```python
# ============================================================================
# EMA_STRADDLE mode - EMA9/EMA21 crossover zala ki CE+PE donhi ekaच वेळी BUY.
# Pratyek leg la swतंत्र 10-point SL + 10-point trailing SL (premium वर).
# Fakt Telegram sिgnal pathavto - actual order Angel One var TAKत नाही.
# ============================================================================
_ema_straddle_state = {}

def _get_ema_straddle_state(symbol_key):
    if symbol_key not in _ema_straddle_state:
        _ema_straddle_state[symbol_key] = {
            "ce_entry": None, "ce_sl": None, "ce_peak_pnl": 0.0,
            "pe_entry": None, "pe_sl": None, "pe_peak_pnl": 0.0,
            "active_strike": None,
        }
    return _ema_straddle_state[symbol_key]


EMA_STRADDLE_SL_POINTS = 10
EMA_STRADDLE_TRAIL_POINTS = 10


def check_ema_straddle_for_symbol(symbol_key, now, today_str, current_time_str):
    cfg = SYMBOLS[symbol_key]
    s = _get_ema_straddle_state(symbol_key)
    lot_size = cfg["lot_size"]
    strike_step = cfg["strike_step"]
    display_name = cfg["display"]

    if lot_size <= 0 or not BROKER_AVAILABLE:
        return

    if cfg.get("source") == "MCX":
        df = broker.get_mcx_historical_df(symbol_key)
    else:
        df = yf.download(tickers=cfg["ticker"], period="5d", interval="5m", progress=False)
        df = fix_multiindex(df)

    if df is None or df.empty or len(df) < 22:
        return

    df['EMA9'] = ta.ema(df['Close'], length=9)
    df['EMA21'] = ta.ema(df['Close'], length=21)

    latest_price = round(df['Close'].iloc[-1], 2)
    latest_ema9 = df['EMA9'].iloc[-1]
    latest_ema21 = df['EMA21'].iloc[-1]
    prev_ema9 = df['EMA9'].iloc[-2]
    prev_ema21 = df['EMA21'].iloc[-2]

    crossover_up = (not pd.isna(prev_ema9)) and (not pd.isna(prev_ema21)) and prev_ema9 <= prev_ema21 and latest_ema9 > latest_ema21
    crossover_down = (not pd.isna(prev_ema9)) and (not pd.isna(prev_ema21)) and prev_ema9 >= prev_ema21 and latest_ema9 < latest_ema21
    crossover_happened = crossover_up or crossover_down

    already_active = s["ce_entry"] is not None or s["pe_entry"] is not None

    if not already_active and crossover_happened and current_time_str >= "09:17" and current_time_str < "15:15":
        atm_strike = round(latest_price / strike_step) * strike_step
        ce_premium = try_get_real_premium(symbol_key, atm_strike, 'CE')
        pe_premium = try_get_real_premium(symbol_key, atm_strike, 'PE')
        if ce_premium is None or pe_premium is None:
            return

        s["ce_entry"] = ce_premium
        s["ce_sl"] = round(ce_premium - EMA_STRADDLE_SL_POINTS, 2)
        s["ce_peak_pnl"] = 0.0
        s["pe_entry"] = pe_premium
        s["pe_sl"] = round(pe_premium - EMA_STRADDLE_SL_POINTS, 2)
        s["pe_peak_pnl"] = 0.0
        s["active_strike"] = atm_strike

        direction = "Bullish (EMA9 वर क्रॉस)" if crossover_up else "Bearish (EMA9 खाली क्रॉस)"
        send_telegram_message(
            f"🟡 **{display_name} EMA CROSSOVER — CE+PE BUY**\n\n"
            f"Crossover: {direction}\nStrike (ATM): {atm_strike}\n"
            f"👉 BUY {atm_strike} CE | Entry: ₹{ce_premium} | SL: ₹{s['ce_sl']}\n"
            f"👉 BUY {atm_strike} PE | Entry: ₹{pe_premium} | SL: ₹{s['pe_sl']}\n\n"
            f"दोन्ही legs वर 10-point SL + 10-point Trailing SL."
        )
        return

    if s["ce_entry"] is not None:
        atm_strike = s["active_strike"]
        ce_ltp = try_get_real_premium(symbol_key, atm_strike, 'CE')
        if ce_ltp is not None:
            pnl = ce_ltp - s["ce_entry"]
            s["ce_peak_pnl"] = max(s["ce_peak_pnl"], pnl)
            trailing_hit = s["ce_peak_pnl"] > 0 and (s["ce_peak_pnl"] - pnl) >= EMA_STRADDLE_TRAIL_POINTS
            sl_hit = ce_ltp <= s["ce_sl"]
            if sl_hit or trailing_hit or current_time_str >= "15:20":
                reason = "SL Hit" if sl_hit else ("Trailing SL Hit" if trailing_hit else "Day End Square-off")
                send_telegram_message(f"🔴 {display_name} CE EXIT ({reason})\nExit: ₹{ce_ltp} | P&L: ₹{round(pnl*lot_size,2)}")
                s["ce_entry"] = None
                s["ce_sl"] = None
                s["ce_peak_pnl"] = 0.0
            else:
                new_sl = round(ce_ltp - EMA_STRADDLE_TRAIL_POINTS, 2)
                if new_sl > s["ce_sl"]:
                    s["ce_sl"] = new_sl

    if s["pe_entry"] is not None:
        atm_strike = s["active_strike"]
        pe_ltp = try_get_real_premium(symbol_key, atm_strike, 'PE')
        if pe_ltp is not None:
            pnl = pe_ltp - s["pe_entry"]
            s["pe_peak_pnl"] = max(s["pe_peak_pnl"], pnl)
            trailing_hit = s["pe_peak_pnl"] > 0 and (s["pe_peak_pnl"] - pnl) >= EMA_STRADDLE_TRAIL_POINTS
            sl_hit = pe_ltp <= s["pe_sl"]
            if sl_hit or trailing_hit or current_time_str >= "15:20":
                reason = "SL Hit" if sl_hit else ("Trailing SL Hit" if trailing_hit else "Day End Square-off")
                send_telegram_message(f"🔴 {display_name} PE EXIT ({reason})\nExit: ₹{pe_ltp} | P&L: ₹{round(pnl*lot_size,2)}")
                s["pe_entry"] = None
                s["pe_sl"] = None
                s["pe_peak_pnl"] = 0.0
            else:
                new_sl = round(pe_ltp - EMA_STRADDLE_TRAIL_POINTS, 2)
                if new_sl > s["pe_sl"]:
                    s["pe_sl"] = new_sl
```


## 3. check_signals() function madhे fakt routing jodा (existing loop badla naka, ovaल एक if jodा)

FIND (tumchya check_signals() function madhला symbol loop):
```python
    for symbol_key in SYMBOLS:
        try:
```

REPLACE WITH:
```python
    for symbol_key in SYMBOLS:
        try:
            if STRATEGY_MODE == "EMA_STRADDLE":
                check_ema_straddle_for_symbol(symbol_key, now, today_str, current_time_str)
                continue
```

(he existing check_signals_for_symbol() call skip karel jevha mode "EMA_STRADDLE"
asel, baki sagळे modes आधीसारखेच chaltील.)
