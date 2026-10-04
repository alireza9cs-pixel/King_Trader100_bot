# -*- coding: utf-8 -*-
import os
import io
import asyncio
import logging

import numpy as np
import pandas as pd
import ccxt.async_support as ccxt
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from aiohttp import web

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("bot")

TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("BOT_TOKEN env var not set")
bot = Bot(token=TOKEN, parse_mode=ParseMode.MARKDOWN)
dp = Dispatcher()

# ---------------- Exchange ----------------
exchange = ccxt.mexc({
    "enableRateLimit": True,
    "timeout": 10000,
    "options": {"defaultType": "swap"},
})

TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]

# ---------------- Keyboards ----------------
def get_symbols_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTC/USDT", callback_data="sym:BTC/USDT"),
         InlineKeyboardButton(text="ETH/USDT", callback_data="sym:ETH/USDT")],
        [InlineKeyboardButton(text="SOL/USDT", callback_data="sym:SOL/USDT"),
         InlineKeyboardButton(text="PEPE/USDT", callback_data="sym:PEPE/USDT")],
        [InlineKeyboardButton(text="AKE/USDT (MEXC)", callback_data="sym:AKE/USDT:USDT")],
    ])

def get_timeframe_keyboard(symbol: str):
    rows, row = [], []
    for tf in TIMEFRAMES:
        row.append(InlineKeyboardButton(text=tf.upper() if tf == "1d" else tf,
                                        callback_data=f"tf:{tf}:{symbol}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="📊 Volume Profile",
                                      callback_data=f"vp:1h:{symbol}")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به لیست ارزها", callback_data="back_symbols")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ---------------- Indicators ----------------
def calculate_rsi(df, period=14):
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def calculate_macd(df, fast=12, slow=26, signal=9):
    macd_line = (df["close"].ewm(span=fast, adjust=False).mean()
                 - df["close"].ewm(span=slow, adjust=False).mean())
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1]

def calculate_volume_profile(df, bins=50, value_area=0.70):
    lo, hi = float(df["low"].min()), float(df["high"].max())
    if hi <= lo:
        return float(df["close"].iloc[-1]), hi, lo
    bin_edges = np.linspace(lo, hi, bins + 1)
    vol = np.zeros(bins)
    for _, r in df.iterrows():
        b0 = int(np.searchsorted(bin_edges, r["low"], "right") - 1)
        b1 = int(np.searchsorted(bin_edges, r["high"], "left"))
        b0, b1 = max(0, b0), min(bins, max(b1, b0 + 1))
        vol[b0:b1] += float(r["volume"]) / (b1 - b0)
    total = vol.sum()
    poc_i = int(vol.argmax())
    lo_i, hi_i = poc_i, poc_i
    acc = vol[poc_i]
    while acc < value_area * total and (lo_i > 0 or hi_i < bins - 1):
        left = vol[lo_i - 1] if lo_i > 0 else -1
        right = vol[hi_i + 1] if hi_i < bins - 1 else -1
        if right >= left:
            hi_i += 1; acc += max(right, 0)
        else:
            lo_i -= 1; acc += max(left, 0)
    poc = (bin_edges[poc_i] + bin_edges[poc_i + 1]) / 2
    vah = (bin_edges[hi_i] + bin_edges[min(hi_i + 1, bins)]) / 2
    val = (bin_edges[lo_i] + bin_edges[lo_i + 1]) / 2
    return poc, vah, val

# ---------------- Volume Profile Chart ----------------
def render_vp_chart(df, symbol, timeframe, poc, vah, val) -> bytes:
    plt.style.use("dark_background")
    fig = plt.figure(figsize=(11, 6), facecolor="#11131a")
    ax = fig.add_axes([0.08, 0.1, 0.68, 0.82])
    axp = ax.twinx()
    x = pd.to_datetime(df["timestamp"], unit="ms")

    up = df["close"] >= df["open"]
    ax.vlines(x, df["low"], df["high"], color="#26a69a", lw=0.7, alpha=0.85)
    ax.vlines(x[up], df["open"][up], df["close"][up], color="#26a69a", lw=2.4)
    ax.vlines(x[~up], df["open"][~up], df["close"][~up], color="#ef5350", lw=2.4)

    axp.hist(df["volume"], bins=40, orientation="horizontal",
             color="#3a4a6b", alpha=0.5, height=0.9)
    axp.set_yticks([])
    axp.set_ylim(ax.get_ylim())

    for price, color, label in ((vah, "#f0b90b", "VAH"),
                                (poc, "#00e676", "POC"),
                                (val, "#f0b90b", "VAL")):
        ax.axhline(price, color=color, lw=1.5, ls="--", alpha=0.95)
        ax.text(x.iloc[0], price, f" {label}: {price:g}",
                color=color, fontsize=9, va="bottom", fontweight="bold")

    ax.axhspan(val, vah, color="#f0b90b", alpha=0.08)

    ax.set_facecolor("#11131a")
    ax.set_title(f"Volume Profile (250 Candles) | {symbol} | {timeframe}",
                 color="white", fontsize=13, fontweight="bold", pad=10)
    ax.tick_params(colors="#9aa3b5")
    ax.grid(color="#23283a", lw=0.5, alpha=0.5)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.text(0.78, 0.03, "70% Value Area", color="#f0b90b", fontsize=9)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

async def send_volume_profile(message: types.Message, symbol: str, timeframe: str):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=250)
        if not ohlcv:
            await message.answer("❌ داده‌ای برای این جفت‌ارز یافت نشد.")
            return
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        poc, vah, val = calculate_volume_profile(df, bins=50, value_area=0.70)
        png = render_vp_chart(df, symbol, timeframe, poc, vah, val)
        photo = types.BufferedInputFile(png, filename="volume_profile.png")
        caption = (f"📊 *Volume Profile* — `{symbol}` ({timeframe})\n\n"
                   f"🎯 POC: `{poc:.6g}`\n"
                   f"⬆️ VAH: `{vah:.6g}`\n"
                   f"⬇️ VAL: `{val:.6g}`\n"
                   f"🧮 Value Area: 70% (250 کندل)")
        await message.answer_photo(photo, caption=caption)
    except Exception as e:
        log.exception("VP error")
        await message.answer(f"❌ خطا در رسم Volume Profile: `{e}`")

# ---------------- Full SMC/ICT Analysis ----------------
async def analyze_market(symbol: str, timeframe: str):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if not ohlcv:
            return "❌ خطا: داده‌ای برای ارز یافت نشد.", None
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        last = df.iloc[-1]
        price = float(last["close"])
        high_24h = float(df["high"].max())
        low_24h = float(df["low"].min())
        rsi = float(calculate_rsi(df).iloc[-1])
        macd, sig = calculate_macd(df)
        poc, vah, val = calculate_volume_profile(df, bins=30, value_area=0.70)

        # SMC: FVG & Order Block
        fvg = "✅ فعال (Bullish FVG)" if last["low"] > df["high"].iloc[-3] \
              else "✅ فعال (Bearish FVG)" if last["high"] < df["low"].iloc[-3] \
              else "❌ غیرفعال"
        ob = f"`{df['low'].tail(5).min():.4f} - {df['high'].tail(5).max():.4f}`"

        # AMD Phase
        rng = high_24h - low_24h
        if price < low_24h + rng * 0.25:
            amd = "Accumulation (انباشت)"
        elif price < low_24h + rng * 0.75:
            amd = "Manipulation (دستکاری)"
        else:
            amd = "Distribution (توزیع)"

        bullish = rsi > 50 and macd > sig
        sentiment = "🟢 صعودی (Bullish)" if bullish else "🔴 نزولی (Bearish)"
        direction = "LONG 📈" if bullish else "SHORT 📉"

        fib_0618 = high_24h - 0.618 * rng
        entry = price
        sl = entry * 0.985 if bullish else entry * 1.015
        tps = [entry * m for m in ((1.01, 1.022, 1.035, 1.05) if bullish else (0.99, 0.978, 0.965, 0.95))]
        lev = "10x - 20x" if rsi < 68 else "3x - 5x (احتیاط)"

        report = (
            f"👑 *تحلیل جامع {symbol} - {timeframe}* 👑\n\n"
            f"💰 قیمت لحظه‌ای: `{price:.6f}`\n"
            f"📈 ۲۴ساعت (High/Low): `{high_24h:.4f}` / `{low_24h:.4f}`\n\n"
            f"📊 *تکنیکال:*\n"
            f"• RSI: `{rsi:.2f}`\n"
            f"• MACD: `{'🟢 مثبت' if macd > sig else '🔴 منفی'}`\n"
            f"• POC: `{poc:.4f}` | VAH: `{vah:.4f}` | VAL: `{val:.4f}`\n"
            f"• فیبوناچی (0.618): `{fib_0618:.4f}`\n\n"
            f"🧠 *پرایس‌اکشن & SMC:*\n"
            f"• FVG: {fvg}\n"
            f"• Order Block: {ob}\n"
            f"• چرخه AMD: {amd}\n"
            f"• نظر کلی: {sentiment}\n"
            f"• جهت: {direction}\n\n"
            f"🔥 *سیگنال پیشنهادی:*\n"
            f"• Leverage: `{lev}`\n"
            f"• Entry Price: `{entry:.6f}`\n"
            f"• Stop Loss: `{sl:.6f}`\n"
            f"• TP 1: `{tps[0]:.6f}`\n"
            f"• TP 2: `{tps[1]:.6f}`\n"
            f"• TP 3: `{tps[2]:.6f}`\n"
            f"• TP 4: `{tps[3]:.6f}`"
        )
        return report, None
    except Exception as e:
        log.exception("analysis error")
        return f"❌ خطا: {e}", None

# ---------------- Handlers ----------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام! 👑 ارز مورد نظر رو انتخاب کن یا اسمش رو بنویس (مثلا BTC یا AKE):",
        reply_markup=get_symbols_keyboard(),
    )

@dp.message()
async def handle_search(message: types.Message):
    text = (message.text or "").strip().upper()
    if "/" not in text:
        text += "/USDT"
    await message.answer(
        f"جفت‌ارز `{text}` انتخاب شد. تایم‌فریم رو انتخاب کن:",
        reply_markup=get_timeframe_keyboard(text),
    )

@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    data = callback.data or ""
    try:
        if data == "back_symbols":
            await callback.message.edit_text("انتخاب ارز:", reply_markup=get_symbols_keyboard())
        elif data.startswith("sym:"):
            symbol = data[len("sym:"):]
            await callback.message.edit_text(
                f"جفت‌ارز `{symbol}` انتخاب شد. تایم‌فریم رو انتخاب کن:",
                reply_markup=get_timeframe_keyboard(symbol))
        elif data.startswith("tf:"):
            # tf:<tf>:<symbol>
            _, rest = data.split(":", 1)
            tf, symbol = rest.split(":", 1)
            await callback.answer("⏳ در حال تحلیل...")
            report, _ = await analyze_market(symbol, tf)
            await callback.message.edit_text(report, reply_markup=get_timeframe_keyboard(symbol))
            return
        elif data.startswith("vp:"):
            # vp:<tf>:<symbol>
            _, rest = data.split(":", 1)
            tf, symbol = rest.split(":", 1)
            await callback.answer("⏳ در حال رسم چارت Volume Profile...")
            await send_volume_profile(callback.message, symbol, tf)
            return
        await callback.answer()
    except Exception as e:
        log.exception("callback error")
        try:
            await callback.answer(f"❌ خطا: {e}", show_alert=True)
        except Exception:
            pass

# ---------------- Web server (Render keepalive) ----------------
async def health(request):
    return web.json_response({"status": "ok", "bot": "running"})

async def start_web_server(port=10000):
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"Web server started on 0.0.0.0:{port}")
    return runner

async def main():
    port = int(os.environ.get("PORT", 10000))
    runner = await start_web_server(port)
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
