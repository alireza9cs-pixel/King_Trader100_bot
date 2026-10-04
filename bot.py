import os
import asyncio
import logging
from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- کتابخانه‌های اضافه شده برای رسم نمودار ---
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from io import BytesIO

logging.basicConfig(level=logging.INFO)

# متغیر برای نگهداری آخرین تایم‌فریم کاربر
user_last_tf = {}

# خواندن امن توکن تلگرام
TOKEN = os.getenv("BOT_TOKEN", "").strip()

# صرافی MEXC با تایم‌اوت ۱۰ ثانیه‌ای جهت عدم معلق ماندن
exchange = ccxt.mexc({'enableRateLimit': True, 'timeout': 10000, 'options': {'defaultType': 'swap'}})

dp = Dispatcher()

def get_symbols_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="بیت‌کوین (BTC)", callback_data="sym:BTC/USDT:USDT"),
            InlineKeyboardButton(text="اتریوم (ETH)", callback_data="sym:ETH/USDT:USDT")
        ],
        [
            InlineKeyboardButton(text="سولانا (SOL)", callback_data="sym:SOL/USDT:USDT"),
            InlineKeyboardButton(text="پپه (PEPE)", callback_data="sym:PEPE/USDT:USDT")
        ]
    ])

def get_timeframe_keyboard(symbol):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1m", callback_data=f"tf:{symbol}:1m"),
            InlineKeyboardButton(text="5m", callback_data=f"tf:{symbol}:5m"),
            InlineKeyboardButton(text="15m", callback_data=f"tf:{symbol}:15m")
        ],
        [
            InlineKeyboardButton(text="1h", callback_data=f"tf:{symbol}:1h"),
            InlineKeyboardButton(text="4h", callback_data=f"tf:{symbol}:4h"),
            InlineKeyboardButton(text="1D", callback_data=f"tf:{symbol}:1d")
        ],
        # --- اضافه شده: دکمه Volume Profile ---
        [
            InlineKeyboardButton(text="📊 Volume Profile", callback_data=f"vp:{symbol}")
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست ارزها", callback_data="back_to_symbols")
        ]
    ])

async def analyze_market(symbol: str, timeframe: str = '15m'):
    try:
        limit = 250 # افزایش لیمیت برای محاسبات بهتر
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 30:
            return "❌ داده‌های کافی از صرافی دریافت نشد."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # محاسبات اندیکاتورها (دقیقاً کدهای قبلی شما)
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()

        current_price = df['close'].iloc[-1]
        rsi_val = df['rsi'].iloc[-1]
        macd_val = df['macd'].iloc[-1]
        macd_sig = df['macd_signal'].iloc[-1]
        ema50_val = df['ema50'].iloc[-1]
        ema200_val = df['ema200'].iloc[-1]
        atr_val = df['atr'].iloc[-1] if not pd.isna(df['atr'].iloc[-1]) else current_price * 0.015

        score = 0
        score += 1 if current_price > ema50_val else -1
        score += 1 if current_price > ema200_val else -1
        score += 1 if macd_val > macd_sig else -1
        if rsi_val > 52: score += 1
        elif rsi_val < 48: score -= 1

        if score >= 2:
            direction = "🟢 صعودی (Bullish)"
            sl = round(current_price - (1.5 * atr_val), 4)
            tp1, tp2, tp3, tp4 = round(current_price + (1.0 * atr_val), 4), round(current_price + (2.0 * atr_val), 4), round(current_price + (3.2 * atr_val), 4), round(current_price + (4.5 * atr_val), 4)
        elif score <= -2:
            direction = "🔴 نزولی (Bearish)"
            sl = round(current_price + (1.5 * atr_val), 4)
            tp1, tp2, tp3, tp4 = round(current_price - (1.0 * atr_val), 4), round(current_price - (2.0 * atr_val), 4), round(current_price - (3.2 * atr_val), 4), round(current_price - (4.5 * atr_val), 4)
        else:
            direction = "⚪️ خنثی"
            sl = round(current_price - atr_val, 4)
            tp1, tp2, tp3, tp4 = round(current_price + atr_val, 4), round(current_price + (1.8 * atr_val), 4), round(current_price + (2.5 * atr_val), 4), round(current_price + (3.5 * atr_val), 4)

        return f"📊 <b>تحلیل تکنیکال</b>\n\n🔹 <b>نماد:</b> <code>{symbol}</code>\n⏱ <b>تایم‌فریم:</b> <code>{timeframe}</code>\n💵 <b>Entry:</b> <code>{current_price}</code>\n📈 <b>جهت:</b> {direction}\n\n🎯 <b>TP:</b> {tp1}, {tp2}\n🛑 <b>SL:</b> <code>{sl}</code>"

    except Exception as e:
        return f"❌ خطا: {str(e)}"

# --- توابع اضافه شده برای Volume Profile ---
def generate_vp_chart(df):
    n_bins = 60
    low, high = df["low"].min(), df["high"].max()
    edges = np.linspace(low, high, n_bins + 1)
    centers = (edges[:-1] + edges[1:]) / 2
    vol_bins = np.zeros(n_bins)
    for _, row in df.iterrows():
        left = np.searchsorted(edges, row["low"]) - 1
        right = np.searchsorted(edges, row["high"])
        vol_bins[max(left, 0):min(right, n_bins)] += row["volume"] / max(right - left, 1)

    total_vol = vol_bins.sum()
    poc_idx = np.argmax(vol_bins)
    target = total_vol * 0.70
    acc = vol_bins[poc_idx]
    included = np.zeros(n_bins, dtype=bool)
    included[poc_idx] = True
    l, r = poc_idx - 1, poc_idx + 1
    while acc < target and (l >= 0 or r < n_bins):
        if r < n_bins and (l < 0 or vol_bins[r] > vol_bins[l]):
            included[r] = True; acc += vol_bins[r]; r += 1
        else:
            included[l] = True; acc += vol_bins[l]; l -= 1
    
    poc, val, vah = centers[poc_idx], centers[included].min(), centers[included].max()
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.barh(centers, vol_bins, height=(centers[1]-centers[0])*0.8, color='skyblue', alpha=0.6)
    ax.axhline(poc, color='green', label=f'POC: {poc:.4f}')
    ax.axhline(val, color='red', linestyle='--', label=f'VAL: {val:.4f}')
    ax.axhline(vah, color='red', linestyle='--', label=f'VAH: {vah:.4f}')
    ax.legend(); ax.set_title("Volume Profile (Fixed Range)")
    buf = BytesIO()
    fig.savefig(buf, format='png'); buf.seek(0)
    return buf, poc, val, vah

@dp.callback_query(lambda c: c.data.startswith('vp:'))
async def process_vp_select(callback_query: types.CallbackQuery):
    symbol = callback_query.data.split('vp:')[1]
    tf = user_last_tf.get(callback_query.from_user.id, "15m")
    await callback_query.answer("در حال محاسبه...")
    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=tf, limit=250)
    df = pd.DataFrame(ohlcv, columns=['t', 'o', 'high', 'low', 'c', 'volume'])
    img_buf, poc, val, vah = generate_vp_chart(df)
    await callback_query.message.answer_photo(
        photo=types.BufferedInputFile(img_buf.read(), "vp.png"),
        caption=f"📊 Volume Profile\nPOC: {poc:.4f}\nVAL: {val:.4f}\nVAH: {vah:.4f}"
    )

# --- باقی کدهای شما ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("سلام! ارز مورد نظر خود را انتخاب کنید:", reply_markup=get_symbols_keyboard())

@dp.callback_query(lambda c: c.data.startswith('sym:'))
async def process_symbol_select(callback_query: types.CallbackQuery):
    symbol = callback_query.data.split('sym:')[1]
    await callback_query.message.edit_text(f"ارز: <b>{symbol}</b>\nتایم‌فریم را انتخاب کنید:", parse_mode="HTML", reply_markup=get_timeframe_keyboard(symbol))
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('tf:'))
async def process_timeframe_select(callback_query: types.CallbackQuery):
    data_str = callback_query.data[3:]
    symbol, tf = data_str.rsplit(':', 1)
    user_last_tf[callback_query.from_user.id] = tf # ذخیره آخرین تایم‌فریم
    await callback_query.message.edit_text("⏳ در حال تحلیل...")
    result = await analyze_market(symbol, tf)
    await callback_query.message.edit_text(result, parse_mode="HTML", reply_markup=get_timeframe_keyboard(symbol))
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == 'back_to_symbols')
async def process_back(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("ارز مورد نظر خود را انتخاب کنید:", reply_markup=get_symbols_keyboard())
    await callback_query.answer()

async def handle_ping(request): return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000)))
    await site.start()

async def main():
    bot = Bot(token=TOKEN)
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
