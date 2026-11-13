import streamlit as st, yfinance as yf, pandas as pd, matplotlib.pyplot as plt, io, requests, time, json, os
from datetime import datetime

st.set_page_config(page_title="VOI V2 - OB Scanner", layout="centered", initial_sidebar_state="collapsed")

# ---------- APP STYLE ----------
st.markdown("""
<style>
.stApp { background:#0B0E11; color:#EAECEF; }
header, [data-testid="stHeader"] { display:none; }
.block-container { padding-top:12px !important; max-width:520px; }
.topbar { display:flex; justify-content:space-between; align-items:center; background:#1E2329; padding:12px 14px; border-radius:14px; margin-bottom:12px; }
.topbar b { font-size:19px; letter-spacing:0.5px; }
.live { color:#0ECB81; font-size:13px; font-weight:700; }
.sub { color:#848E9C; font-size:12px; margin-top:2px; }
.card { background:#1E2329; border-radius:14px; padding:14px; margin-bottom:10px; border:1px solid #2B3139; }
.card-top { display:flex; justify-content:space-between; align-items:center; }
.sym { font-size:17px; font-weight:800; }
.price { font-size:20px; font-weight:800; }
.badge-buy { background:#0ECB81; color:#000; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:800; }
.badge-sell { background:#F6465D; color:#fff; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:800; }
.badge-wait { background:#F0B90B; color:#000; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:800; }
.meta { color:#B7BDC6; font-size:12.5px; line-height:1.6; margin-top:8px; }
.state { color:#EAECEF; font-size:13px; font-weight:600; margin-top:6px; }
div.stButton > button { width:100%; height:52px; border-radius:12px; font-size:16px; font-weight:800; border:none; }
div.stButton:nth-of-type(1) > button { background:#0ECB81; color:#000; }
div.stButton:nth-of-type(2) > button { background:#2B3139; color:#fff; }
.statusbar { background:#1E2329; border-radius:12px; padding:10px 12px; font-size:12.5px; color:#B7BDC6; text-align:center; margin-top:12px; }
</style>
""", unsafe_allow_html=True)

BOT = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
CHAT = st.secrets.get("TELEGRAM_CHAT_ID", "")
SYMBOLS = {"BTCUSD": "BTC-USD", "EURUSD": "EURUSD=X", "XAUUSD": "GC=F"}
TIMEFRAMES = [("H1", "1h", "10d"), ("M15", "15m", "5d")]

def get_data(ticker, interval, period="10d"):
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=True)
        if df is None or df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df
    except: return None

def detect_choch_bos(df1, break_idx, direction):
    # Look back 40 candles before break: was trend opposite?
    # If price was making lower lows then breaks up = CHoCH (reversal)
    # If price was making higher highs then breaks up = BOS (continuation)
    try:
        look = df1.iloc[max(0,break_idx-40):break_idx]
        if len(look) < 10: return "BOS"
        first = float(look["Close"].iloc[0]); last = float(look["Close"].iloc[-1])
        if direction == "BUY":
            # Break up. If prior trend was down (last < first) = CHoCH, else BOS
            return "CHoCH" if last < first else "BOS"
        else:
            # Break down. If prior trend was up (last > first) = CHoCH, else BOS
            return "CHoCH" if last > first else "BOS"
    except: return "BOS"

def find_setup(df1, df4):
    if df1 is None or len(df1) < 50: return None
    close = df1["Close"]; high = df1["High"]; low = df1["Low"]
    price = float(close.iloc[-1])
    c4 = df4["Close"] if df4 is not None else close
    bias = "BEARISH" if float(c4.iloc[-1]) < float(c4.iloc[-50]) else "BULLISH"
    for i in range(len(df1)-2, 25, -1):
        swing_high = float(high.iloc[i-20:i].max())
        swing_low = float(low.iloc[i-20:i].min())
        swing_high_idx = int(high.iloc[i-20:i].values.argmax()) + (i-20)
        swing_low_idx = int(low.iloc[i-20:i].values.argmin()) + (i-20)
        if close.iloc[i] < swing_low:
            ob_idx = swing_high_idx
            ob_high = float(high.iloc[ob_idx]); ob_low = float(low.iloc[ob_idx])
            fvg_found = False; fvg_high = 0; fvg_low = 0
            for j in range(ob_idx+1, i-1):
                if float(low.iloc[j-1]) > float(high.iloc[j+1]):
                    fvg_found = True; fvg_high = float(low.iloc[j-1]); fvg_low = float(high.iloc[j+1]); break
            if not fvg_found: continue
            ob_touched = False
            for k in range(ob_idx+1, len(df1)):
                if float(high.iloc[k]) >= ob_low: ob_touched = True; break
            if ob_touched: continue
            fvg_touched = False
            for k in range(ob_idx+1, len(df1)):
                if float(high.iloc[k]) >= fvg_low and float(high.iloc[k]) < ob_low: fvg_touched = True; break
                if float(high.iloc[k]) >= ob_low: break
            state = "IDM / Liquidity - FVG Tapped, Waiting OB" if fvg_touched else "Fresh OB - Waiting Retest"
            struct = detect_choch_bos(df1, i, "SELL")
            ob_low_dist = abs(price - ob_low) / price * 100
            return {"direction": "SELL", "ob_high": ob_high, "ob_low": ob_low, "in_zone": (ob_low <= price <= ob_high), "dist": ob_low_dist, "bos_up": False, "bos_down": True, "trade_type": f"OB + FVG -> {struct} + IDM", "struct": struct, "fvg_high": fvg_high, "fvg_low": fvg_low, "price": price, "bias": bias, "state": state}
        if close.iloc[i] > swing_high:
            ob_idx = swing_low_idx
            ob_high = float(high.iloc[ob_idx]); ob_low = float(low.iloc[ob_idx])
            fvg_found = False; fvg_high = 0; fvg_low = 0
            for j in range(ob_idx+1, i-1):
                if float(high.iloc[j-1]) < float(low.iloc[j+1]):
                    fvg_found = True; fvg_high = float(low.iloc[j+1]); fvg_low = float(high.iloc[j-1]); break
            if not fvg_found: continue
            ob_touched = False
            for k in range(ob_idx+1, len(df1)):
                if float(low.iloc[k]) <= ob_high: ob_touched = True; break
            if ob_touched: continue
            fvg_touched = False
            for k in range(ob_idx+1, len(df1)):
                if float(low.iloc[k]) <= fvg_high and float(low.iloc[k]) > ob_high: fvg_touched = True; break
                if float(low.iloc[k]) <= ob_high: break
            state = "IDM / Liquidity - FVG Tapped, Waiting OB" if fvg_touched else "Fresh OB - Waiting Retest"
            struct = detect_choch_bos(df1, i, "BUY")
            ob_high_dist = abs(price - ob_high) / price * 100
            return {"direction": "BUY", "ob_high": ob_high, "ob_low": ob_low, "in_zone": (ob_low <= price <= ob_high), "dist": ob_high_dist, "bos_up": True, "bos_down": False, "trade_type": f"OB + FVG -> {struct} + IDM", "struct": struct, "fvg_high": fvg_high, "fvg_low": fvg_low, "price": price, "bias": bias, "state": state}
    return None

def make_chart(df1, symbol, s, tf_label="", liqs=None, entry_price=None):
    fig, ax = plt.subplots(figsize=(10, 5))
    data = df1.tail(100).reset_index(drop=True)
    for i, row in data.iterrows():
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
        color = "#26a69a" if c >= o else "#ef5350"
        ax.plot([i, i], [l, h], color=color, linewidth=1)
        ax.add_patch(plt.Rectangle((i-0.4, min(o, c)), 0.8, abs(c-o) if abs(c-o) > 0 else 0.0001, facecolor=color, edgecolor=color))
    # 1. OB = GREY BOX
    ax.axhspan(s["ob_low"], s["ob_high"], color="grey", alpha=0.35)
    # 2. LIQUIDITY / IDM = YELLOW LINE
        # --- ONLY 2 NEAREST LIQUIDITY ---
    if liqs:
        last_price = float(data["Close"].iloc[-1])
        liqs = sorted(liqs, key=lambda x: abs(float(x["price"]) - last_price))[:2]
    if liqs:
        for liq in liqs:
            ax.axhline(float(liq["price"]), color="yellow", linestyle="--", linewidth=1)
    # 3. ENTRY SETUP = LONG / SHORT
    if entry_price:
        is_long = s.get("direction", "") == "BUY"
        label = "LONG" if is_long else "SHORT"
        col = "#26a69a" if is_long else "#ef5350"
        ax.axhline(float(entry_price), color=col, linestyle="-", linewidth=2)
        ax.annotate(label, xy=(len(data)-1, float(entry_price)), xytext=(len(data)-15, float(entry_price)),
                    color="white", fontsize=12, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=col, edgecolor="white"),
                    arrowprops=dict(arrowstyle="->", color=col, lw=2))
    ax.axhline(s["price"], color="white", linestyle=":", linewidth=0.8)
    ax.set_title(f"{symbol} {tf_label} - Price {s['price']:.2f} - {s.get('struct','')}", color="white", fontsize=11, fontweight="bold")
    ax.set_facecolor("#0e1117"); fig.patch.set_facecolor("#0e1117")
    ax.tick_params(colors="white"); ax.grid(True, alpha=0.2)

        # --- ZOOM TO OB + PRICE ---
    recent = data.tail(50)
    lo_vals = [float(recent["Low"].min())]
    hi_vals = [float(recent["High"].max())]
    if liqs:
        for liq in liqs:
            lo_vals.append(float(liq["price"]))
            hi_vals.append(float(liq["price"]))
    lo = min(lo_vals)
    hi = max(hi_vals)
    pad = (hi - lo) * 0.15 if hi > lo else 0.001
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlim(-2, len(data) + 5)
    buf = io.BytesIO(); fig.savefig(buf, format="png", facecolor=fig.get_facecolor()); plt.close(fig)
    buf.seek(0); return buf

def send_photo(buf, caption):
    if not BOT or not CHAT: return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT}/sendPhoto", data={"chat_id": CHAT, "caption": caption, "parse_mode": "HTML"}, files={"photo": ("chart.png", buf, "image/png")}, timeout=20)
        return r.status_code == 200
    except: return False

SENT_FILE = "sent_alerts.json"
def load_sent():
    try:
        if os.path.exists(SENT_FILE):
            with open(SENT_FILE, "r") as f:
                return set(json.load(f))
    except: pass
    return set()
def already_sent(key):
    sent = load_sent()
    if key in sent: return True
    sent.add(key)
    try:
        with open(SENT_FILE, "w") as f:
            json.dump(list(sent)[-500:], f)
    except: pass
    return False

def send_text(msg):
    if not BOT or not CHAT: return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage", data={"chat_id": CHAT, "text": msg, "parse_mode": "HTML"})
        return r.status_code == 200
    except: return False

def find_failed_retracements(df, ob_low, ob_high):
    levels = []
    for i in range(max(2, len(df)-20), len(df)-1):
        high = float(df['High'].iloc[i]); low = float(df['Low'].iloc[i])
        prev_h = float(df['High'].iloc[i-1]); next_h = float(df['High'].iloc[i+1])
        prev_l = float(df['Low'].iloc[i-1]); next_l = float(df['Low'].iloc[i+1])
        if high > prev_h and high > next_h:
            if high < ob_low or high > ob_high: levels.append({'price': high, 'type': 'buyside'})
        if low < prev_l and low < next_l:
            if low < ob_low or low > ob_high: levels.append({'price': low, 'type': 'sellside'})
    return levels

def did_sweep(df, levels):
    if not levels: return False
    last_h = float(df['High'].iloc[-1]); last_l = float(df['Low'].iloc[-1])
    for l in levels:
        if l['type'] == 'buyside' and last_h > l['price']: return True
        if l['type'] == 'sellside' and last_l < l['price']: return True
    return False

def scan_all():
    results = []
    for symbol, ticker in SYMBOLS.items():
        df4 = get_data(ticker, "4h", "30d")
        for tf_label, tf_interval, tf_period in TIMEFRAMES:
            df1 = get_data(ticker, tf_interval, tf_period)
            s = find_setup(df1, df4)
            if s is None or df1 is None: continue
            label = f"{symbol} {tf_label}"
            ob_low = s['ob_low']; ob_high = s['ob_high']; ob_key = f"{label}-{ob_low:.4f}-{ob_high:.4f}"
            if not already_sent(f"OB-{ob_key}"):
                send_text(f"🟡 OB FORMED [{tf_label}]\n<b>{label}</b>\nZone: {ob_low:.4f} - {ob_high:.4f}\nDir: {s['direction']} | Bias: {s['bias']} | Structure: {s.get('struct','BOS')}")
            liqs = find_failed_retracements(df1, ob_low, ob_high)
            if liqs:
                liq = liqs[-1]
                liq_key = f"LIQ-{ob_key}"
                if not already_sent(liq_key):
                    send_text(f"🔵 LIQUIDITY FORMED [{tf_label}]\n<b>{label}</b>\nType: {liq['type']} - IDM / Failed Retracement\nPrice: {liq['price']:.4f}\nTotal levels: {len(liqs)}\nRule: Until price touches OB, all failed retracements = Liquidity")
            last_low = float(df1['Low'].iloc[-1]); last_high = float(df1['High'].iloc[-1])
            touched_ob = (last_low <= ob_high and last_high >= ob_low); swept = did_sweep(df1, liqs)
            buf = make_chart(df1, label, s, tf_label, liqs=liqs)
            zone_txt = "✅ IN OB ZONE - WAIT FOR..."
            cap = (f"<b>{label} - {s['direction']}</b>\nBias: {s['bias']} | {s['trade_type']}\nPrice: {s['price']:.4f}\nOB Zone: {s['ob_low']:.4f} - {s['ob_high']:.4f}\n{zone_txt}\nEntry: At OB | SL: Above OB\nTime: {datetime.now().strftime('%H:%M')}")
            if touched_ob and not liqs:
                if not already_sent(f"TRADE-A-{ob_key}"):
                    send_text(f"🟢 TRADE - MODEL A [{tf_label}]\n<b>{label}</b>\nOB Cleared Liquidity + FVG + {s.get('struct','BOS')} + Retracement to OB = ENTER")
                    buf_trade = make_chart(df1, label, s, tf_label, liqs=liqs, entry_price=float(df1['Close'].iloc[-1]))
                    ok = send_photo(buf_trade, cap)
            elif liqs and not touched_ob and not swept:
                if not already_sent(f"WAIT-B-{ob_key}"):
                    cap_wait = f"🟡 WAIT - MODEL B [{tf_label}]\n<b>{label} - {s['direction']}</b>\nBias: {s.get('bias','')}\nOB + FVG + BOS formed\nRetracement did NOT touch OB yet\nLiquidity still standing\nWaiting for SWEEP + TAP OB"
                    buf_wait = make_chart(df1, label, s, tf_label, liqs=liqs)
                    ok = send_photo(buf_wait, cap_wait)
                    if not ok:
                        send_text(cap_wait)
                
                    
            elif liqs and swept and touched_ob:
                if not already_sent(f"TRADE-B-{ob_key}"):
                    send_text(f"🟢 TRADE - MODEL B [{tf_label}]\n<b>{label}</b>\nSweep of Liquidity (Failed Retracement) + Tap OB = ENTER")
                    buf_trade = make_chart(df1, label, s, tf_label, liqs=liqs, entry_price=float(df1['Close'].iloc[-1]))
                    ok = send_photo(buf_trade, cap)
    return results

# ---------- APP UI ----------
now_str = datetime.now().strftime("%H:%M:%S")
st.markdown(f"""<div class="topbar"><div><b>VOI V2</b><div class="sub">OB Scanner • OB + FVG → CHoCH/BOS + IDM • H1 + M15</div></div><div style="text-align:right"><div class="live">● LIVE</div><div class="sub">{now_str}</div></div></div>""", unsafe_allow_html=True)

for symbol, ticker in SYMBOLS.items():
    df4 = get_data(ticker, "4h", "30d")
    for tf_label, tf_interval, tf_period in TIMEFRAMES:
        df1 = get_data(ticker, tf_interval, tf_period)
        s = find_setup(df1, df4)
        label = f"{symbol} {tf_label}"
        if s is None:
            st.markdown(f"""<div class="card"><div class="card-top"><span class="sym">{label}</span><span class="badge-wait">NO OB</span></div><div class="meta">No fresh OB found - All OBs already touched.</div></div>""", unsafe_allow_html=True)
            continue
        badge = "badge-buy" if s['direction']=="BUY" else "badge-sell"
        inzone = "✅ IN OB ZONE" if s['in_zone'] else f"⏳ {s['dist']:.2f}% away from OB"
        st.markdown(f"""<div class="card"><div class="card-top"><span class="sym">{label}</span><span class="{badge}">{s['direction']} • {s.get('struct','BOS')}</span></div><div class="price">{s['price']:.4f}</div><div class="state">{s['state']}</div><div class="meta">Bias: <b>{s['bias']}</b> • {inzone}<br>OB: {s['ob_low']:.4f} - {s['ob_high']:.4f}<br>FVG: {s['fvg_low']:.4f} - {s['fvg_high']:.4f}</div></div>""", unsafe_allow_html=True)

if st.button("🔍  RUN SCAN NOW"):
    with st.spinner("Scanning OB for all 6 (H1 + M15)..."):
        res = scan_all()
        for r in res: st.write(r)
        if len(res) == 0: st.warning("0 fresh OBs found - All OBs were already touched.")
        else: st.success(f"Done - Sent {len(res)} charts to Telegram!")
if st.button("🧪  TEST ALERTS"):
    send_text("🟡 OB FORMED [M15]\n<b>TEST - EURUSD M15</b>\nZone: 1.0850 - 1.0860\nDir: Bullish | Structure: CHoCH")
    send_text("🔵 LIQUIDITY FORMED [M15]\n<b>TEST - EURUSD M15</b>\nType: buyside - IDM / Failed Retracement\nPrice: 1.0900")
    send_text("🟡 WAIT - MODEL B [M15]\n<b>TEST - EURUSD M15</b>\nWaiting for SWEEP + TAP OB")
    st.success("Test sent - Check Telegram!")

st.markdown("""<div class="statusbar">Auto-scan: ON • Every 5 mins • UptimeRobot: Connected<br>OB (Order Block) • CHoCH + BOS • H1 + M15 • Telegram alerts active</div>""", unsafe_allow_html=True)

if "last" not in st.session_state: st.session_state.last = 0
if time.time() - st.session_state.last > 300:
    st.session_state.last = time.time()
    scan_all()
