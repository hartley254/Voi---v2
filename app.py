import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import io, time, requests, datetime

st.set_page_config(page_title="VOI V2 Scanner", layout="wide")
st.title("VOI V2 Scanner - BTCUSD / EURUSD / XAUUSD")

# --- SECRETS ---
TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
CHAT_ID = st.secrets.get("TELEGRAM_CHAT_ID", "")

SYMBOLS = {
    "BTCUSD": "BTC-USD",
    "EURUSD": "EURUSD=X",
    "XAUUSD": "GC=F",
}

def send_photo(img_bytes, caption):
    if not TOKEN or not CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        files = {"photo": ("chart.png", img_bytes)}
        data = {"chat_id": str(CHAT_ID), "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, files=files, data=data, timeout=30)
        return r.status_code == 200
    except Exception as e:
        st.error(f"Telegram error: {e}")
        return False

def get_data(ticker):
    try:
        df4 = yf.download(ticker, period="60d", interval="4h", progress=False, auto_adjust=True)
        df1 = yf.download(ticker, period="10d", interval="1h", progress=False, auto_adjust=True)
        if isinstance(df4.columns, pd.MultiIndex):
            df4.columns = df4.columns.get_level_values(0)
        if isinstance(df1.columns, pd.MultiIndex):
            df1.columns = df1.columns.get_level_values(0)
        return df4, df1
    except Exception:
        return None, None

def bias_4h(df):
    if df is None or len(df) < 50:
        return "NO DATA", 0
    close = df["Close"]
    ema50 = close.ewm(span=50).mean().iloc[-1]
    ema200 = close.ewm(span=200).mean().iloc[-1] if len(df) >= 200 else close.mean()
    price = close.iloc[-1]
    if price > ema50 and ema50 > ema200:
        return "BULLISH", price
    if price < ema50 and ema50 < ema200:
        return "BEARISH", price
    return "RANGING", price

def make_chart(df1, symbol, bias, price):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df1.index[-100:], df1["Close"].tail(100), color="white", linewidth=1.5)
    ax.set_facecolor("#0e1117")
    fig.patch.set_facecolor("#0e1117")
    ax.tick_params(colors="white")
    ax.set_title(f"{symbol} 1H - 4H Bias: {bias} | Price: {price:.2f}", color="white", fontsize=12)
    ax.grid(True, alpha=0.2)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
  # --- UI ---
auto = st.toggle("Auto-scan ON (sends to Telegram)", value=False)
if st.button("Test Telegram - Send Test Photo"):
    # quick test using BTCUSD
    df4, df1 = get_data("BTC-USD")
    b, p = bias_4h(df4)
    img = make_chart(df1, "BTCUSD", b, p)
    ok = send_photo(img, f"✅ Test from your VOI V2 scanner - BTCUSD {b}")
    st.success("Sent! Check your VOI V2 Scanner bot." if ok else "Failed - Check Secrets / Did you press START on new bot?")

st.divider()
st.subheader("Live Scan")

for name, ticker in SYMBOLS.items():
    df4, df1 = get_data(ticker)
    bias, price = bias_4h(df4)
    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric(name, f"{price:.2f}", bias)
    with col2:
        if df1 is not None:
            st.line_chart(df1["Close"].tail(100))

    # Simple setup: price near 50 EMA on 1H + 4H bias agrees
    if df1 is not None and len(df1) > 20:
        ema50_1h = df1["Close"].ewm(span=50).mean().iloc[-1]
        dist = abs(price - ema50_1h) / price * 100
        if dist < 0.3 and bias in ["BULLISH", "BEARISH"]:
            st.warning(f"🔥 SETUP on {name} - {bias} near 50 EMA")
            if auto:
                img = make_chart(df1, name, bias, price)
                cap = f"🔥 <b>VOI V2 SETUP - {name}</b>\n4H Bias: {bias}\nPrice: {price:.2f}\nNear 50 EMA 1H"
                send_photo(img, cap)
                st.info(f"Alert sent for {name}")
                time.sleep(2)

st.caption("V2 keeps running while this tab is open. Keep Auto-scan ON.")
