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
    # 4H bias from last 50 candles
    c4 = df4["Close"] if df4 is not None else close
    bias = "BEARISH" if float(c4.iloc[-1]) < float(c4.iloc[-20]) else "BULLISH"
    # Last swing high / low - last 40 candles
    last_high = float(high.iloc[-40:].max()); last_low = float(low.iloc[-40:].min())
    last_high_idx = high.iloc[-40:].idxmax(); last_low_idx = low.iloc[-40:].idxmin()
    # BOS check
    bos_down = price < float(low.iloc[-20:-1].min())
    bos_up = price > float(high.iloc[-20:-1].max())
    # OB = last swing that caused BOS
    if bias == "BEARISH":
        direction = "SELL"; ob_high = last_high; ob_low = last_high * 0.998
        trade_type = "TYPE A - BOS + OB" if bos_down else "TYPE B - Sweep On Return"
    else:
        direction = "BUY"; ob_low = last_low; ob_high = last_low * 1.002
        trade_type = "TYPE A - BOS + OB" if bos_up else "TYPE B - Sweep On Return"
    in_zone = (ob_low <= price <= ob_high)
    dist = abs(price - ob_high) / price * 100 if direction == "SELL" else abs(price - ob_low) / price * 100
    return {"direction": direction, "ob_high": ob_high, "ob_low": ob_low, "price": price,
            "in_zone": in_zone, "dist": dist, "bias": bias, "trade_type": trade_type,
            "bos_up": bos_up, "bos_down": bos_down, "last_high": last_high, "last_low": last_low}

def make_chart(df1, symbol, s):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(df1.index[-100:], df1["Close"].iloc[-100:], color="white", linewidth=1.5)
    # Draw OB box
    ax.axhspan(s["ob_low"], s["ob_high"], color="red" if s["direction"]=="SELL" else "green", alpha=0.35)
    ax.axhline(s["price"], color="yellow", linestyle="--", linewidth=1)
    ax.set_facecolor("#0e1117"); fig.patch.set_facecolor("#0e1117")
    ax.tick_params(colors="white"); ax.set_title(f"{symbol} 1H - {s['direction']} OB SETUP", color="white", fontsize=12, weight="bold")
    ax.grid(True, alpha=0.2)
    buf = io.BytesIO(); fig.savefig(buf, format="png", bbox_inches="tight"); plt.close(fig); buf.seek(0)
    return buf
    def send_photo(buf, caption):
        if not BOT or not CHAT: return False
        try:
            r = requests.post(f"https://api.telegram.org/bot{BOT}/sendPhoto", data={"chat_id": CHAT, "caption": caption, "parse_mode": "HTML"}, files={"photo": ("chart.png", buf, "image/png")}, timeout=30)
            return r.status_code == 200
        except: return False

def scan_all():
    results = []
    for symbol, ticker in SYMBOLS.items():
        df1 = get_data(ticker, "1h", "10d"); df4 = get_data(ticker, "4h", "30d")
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
    st.success("Done - Check Telegram for 3 charts!")

st.write("---")
st.write("This version uses **OB (Order Block)**, not EMA. Every scan sends all 3 charts with a possible setup.")
st.write("Auto-scan runs every 5 mins when app is open.")
# Auto-scan
if "last" not in st.session_state: st.session_state.last = 0
if time.time() - st.session_state.last > 300:
    st.session_state.last = time.time()
    scan_all()
