import streamlit as st, yfinance as yf, pandas as pd, matplotlib.pyplot as plt, io, requests, time
from datetime import datetime

st.set_page_config(page_title="VOI V2 - OB Scanner", layout="centered")
st.title("VOI V2 - OB Scanner")

BOT = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
CHAT = st.secrets.get("TELEGRAM_CHAT_ID", "")

SYMBOLS = {"BTCUSD": "BTC-USD", "EURUSD": "EURUSD=X", "XAUUSD": "GC=F"}

def get_data(ticker, interval, period="10d"):
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=True)
        if df is None or df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df
    except: return None

def find_setup(df1, df4):
    if df1 is None or len(df1) < 50: return None
    close = df1["Close"]; high = df1["High"]; low = df1["Low"]
    price = float(close.iloc[-1])

    c4 = df4["Close"] if df4 is not None else close
    bias = "BEARISH" if float(c4.iloc[-1]) < float(c4.iloc[-50]) else "BULLISH"

    # YOUR UPGRADED RULE: OB + FVG -> BOS -> FVG Retest (IDM) -> OB Touch
    # If OB filled -> skip to next OB
    # If FVG touched but OB not -> IDM / Liquidity = BEST setup

    for i in range(len(df1)-2, 25, -1):
        swing_high = float(high.iloc[i-20:i].max())
        swing_low = float(low.iloc[i-20:i].min())
        swing_high_idx = int(high.iloc[i-20:i].values.argmax()) + (i-20)
        swing_low_idx = int(low.iloc[i-20:i].values.argmin()) + (i-20)

        # --- BEARISH ---
        if close.iloc[i] < swing_low:
            ob_idx = swing_high_idx
            ob_high = float(high.iloc[ob_idx])
            ob_low = float(low.iloc[ob_idx])

            # FVG check
            fvg_found = False; fvg_high = 0; fvg_low = 0
            for j in range(ob_idx+1, i-1):
                if float(low.iloc[j-1]) > float(high.iloc[j+1]):
                    fvg_found = True; fvg_high = float(low.iloc[j-1]); fvg_low = float(high.iloc[j+1]); break
            if not fvg_found: continue

            # UPGRADE 1: If OB is FILLED -> skip, look for next OB
            ob_touched = False
            for k in range(ob_idx+1, len(df1)):
                if float(high.iloc[k]) >= ob_low: # price entered OB
                    ob_touched = True; break
            if ob_touched: continue # OB used, find next OB

            # UPGRADE 2: Check FVG Retest = IDM / Liquidity
            # Did price come back up, touch FVG, but NOT touch OB?
            fvg_touched = False
            for k in range(ob_idx+1, len(df1)):
                if float(high.iloc[k]) >= fvg_low and float(high.iloc[k]) < ob_low:
                    fvg_touched = True; break
                if float(high.iloc[k]) >= ob_low: break # hit OB first, not IDM

            # State: FRESH OB + (IDM if FVG touched)
            state = "IDM / Liquidity - FVG Tapped, Waiting OB" if fvg_touched else "Fresh OB - Waiting Retest"

            ob_low_dist = abs(price - ob_low) / price * 100
            return {"direction": "SELL", "ob_high": ob_high, "ob_low": ob_low,
                    "in_zone": (ob_low <= price <= ob_high), "dist": ob_low_dist,
                    "bos_up": False, "bos_down": True, "trade_type": "OB + FVG -> BOS + IDM",
                    "fvg_high": fvg_high, "fvg_low": fvg_low, "price": price, "bias": bias, "state": state}

        # --- BULLISH ---
        if close.iloc[i] > swing_high:
            ob_idx = swing_low_idx
            ob_high = float(high.iloc[ob_idx])
            ob_low = float(low.iloc[ob_idx])

            fvg_found = False; fvg_high = 0; fvg_low = 0
            for j in range(ob_idx+1, i-1):
                if float(high.iloc[j-1]) < float(low.iloc[j+1]):
                    fvg_found = True; fvg_high = float(low.iloc[j+1]); fvg_low = float(high.iloc[j-1]); break
            if not fvg_found: continue

            # UPGRADE 1: If OB FILLED -> skip to next
            ob_touched = False
            for k in range(ob_idx+1, len(df1)):
                if float(low.iloc[k]) <= ob_high:
                    ob_touched = True; break
            if ob_touched: continue

            # UPGRADE 2: FVG Retest = IDM
            fvg_touched = False
            for k in range(ob_idx+1, len(df1)):
                if float(low.iloc[k]) <= fvg_high and float(low.iloc[k]) > ob_high:
                    fvg_touched = True; break
                if float(low.iloc[k]) <= ob_high: break

            state = "IDM / Liquidity - FVG Tapped, Waiting OB" if fvg_touched else "Fresh OB - Waiting Retest"

            ob_high_dist = abs(price - ob_high) / price * 100
            return {"direction": "BUY", "ob_high": ob_high, "ob_low": ob_low,
                    "in_zone": (ob_low <= price <= ob_high), "dist": ob_high_dist,
                    "bos_up": True, "bos_down": False, "trade_type": "OB + FVG -> BOS + IDM",
                    "fvg_high": fvg_high, "fvg_low": fvg_low, "price": price, "bias": bias, "state": state}

    return None

def make_chart(df1, symbol, s):
    fig, ax = plt.subplots(figsize=(10, 5))
    data = df1.tail(100).reset_index(drop=True)
    for i, row in data.iterrows():
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
        color = "#26a69a" if c >= o else "#ef5350"
        ax.plot([i, i], [l, h], color=color, linewidth=1)
        ax.add_patch(plt.Rectangle((i-0.4, min(o, c)), 0.8, abs(c-o) if abs(c-o) > 0 else 0.0001, facecolor=color, edgecolor=color))
    # Draw OB box
    ax.axhspan(s["ob_low"], s["ob_high"], color="red", alpha=0.25)
    ax.axhline(s["price"], color="yellow", linestyle="--", linewidth=1)
    ax.set_title(f"{symbol} - Price {s['price']:.2f}", color="white", fontsize=11, fontweight="bold")
    ax.set_facecolor("#0e1117"); fig.patch.set_facecolor("#0e1117")
    ax.tick_params(colors="white"); ax.grid(True, alpha=0.2)
    buf = io.BytesIO(); fig.savefig(buf, format="png", facecolor=fig.get_facecolor()); plt.close(fig)
    buf.seek(0)
    return buf
    
def send_photo(buf, caption):
    if not BOT or not CHAT:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT}/sendPhoto", data={"chat_id": CHAT, "caption": caption, "parse_mode": "HTML"}, files={"photo": ("chart.png", buf, "image/png")}, timeout=20)
        return r.status_code == 200
    except:
        return False

def scan_all():
    results = []
    for symbol, ticker in SYMBOLS.items():
        df1 = get_data(ticker, "1h", "10d")
        df4 = get_data(ticker, "4h", "30d")
        s = find_setup(df1, df4)
        if s is None or df1 is None: continue
        buf = make_chart(df1, symbol, s)
        zone_txt = "✅ IN OB ZONE - WAIT FOR CONFIRMATION" if s["in_zone"] else f"⏳ {s['dist']:.2f}% away from OB - Wait for price to reach OB"
        cap = (f"<b>{symbol} - {s['direction']} SETUP</b>\n"
               f"Bias: {s['bias']} | {s['trade_type']}\n"
               f"Price: {s['price']:.4f}\n"
               f"OB Zone: {s['ob_low']:.4f} - {s['ob_high']:.4f}\n"
               f"{zone_txt}\n"
               f"Entry: At OB | SL: Above OB (SELL) / Below OB (BUY)\n"
               f"Time: {datetime.now().strftime('%H:%M')}")
        ok = send_photo(buf, cap)
        results.append(f"{symbol}: {'Sent ✅' if ok else 'Failed ❌'} - {s['direction']} OB {s['ob_low']:.2f}-{s['ob_high']:.2f}")
    return results

if st.button("🔍 Run Scan Now - Send All 3 OB Setups"):
    with st.spinner("Scanning OB for all 3..."):
        res = scan_all()
        for r in res: st.write(r)
        if len(res) == 0:
             st.warning("0 fresh OBs found - All OBs were already touched.")
        else:
             st.success(f"Done - Sent {len(res)} charts to Telegram!")

st.write("---")
st.write("This version uses **OB (Order Block)**, not EMA. Every scan sends all 3 charts with a possible setup.")
st.write("Auto-scan runs every 5 mins when app is open.")
# Auto-scan
if "last" not in st.session_state: st.session_state.last = 0
if time.time() - st.session_state.last > 300:
    st.session_state.last = time.time()
    scan_all()
