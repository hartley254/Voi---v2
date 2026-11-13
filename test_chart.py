import os, io, requests, yfinance as yf
import matplotlib.pyplot as plt
from main import make_chart

TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")

df = yf.download("BTC-USD", period="5d", interval="15m")
df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
df = df.reset_index(drop=True)

price = float(df["Close"].iloc[-1])
s = {"ob_low": price*0.99, "ob_high": price*1.01, "price": price, "direction": "SELL", "struct": "TEST"}
liqs = [{"price": price*1.005}]

buf = make_chart(df, "BTCUSD TEST", s, "M15", liqs=liqs, entry_price=price)
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data={"chat_id": CHAT_ID, "caption": "TEST - Grey OB + Yellow Liquidity + SHORT"}, files={"photo": ("test.png", buf)})
print("sent")
