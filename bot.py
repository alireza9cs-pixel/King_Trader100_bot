import os
import asyncio
import logging
from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

# خواندن توکن از متغیرهای محیطی با مقدار پیش‌فرض امن
TOKEN = os.getenv("BOT_TOKEN", "").strip()

# صرافی MEXC
exchange = ccxt.mexc({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})

dp = Dispatcher()

def get_symbols_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTC/USDT", callback_data="sym_BTC/USDT"), InlineKeyboardButton(text="ETH/USDT", callback_data="sym_ETH/USDT")],
        [InlineKeyboardButton(text="SOL/USDT", callback_data="sym_SOL/USDT"), InlineKeyboardButton(text="PEPE/USDT", callback_data="sym_PEPE/USDT")],
    ])

def get_timeframe_keyboard(symbol):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1m", callback_data=f"tf_1m_{symbol}"), InlineKeyboardButton(text="5m", callback_data=f"tf_5m_{symbol}")],
        [InlineKeyboardButton(text="15m", callback_data=f"tf_15m_{symbol}"), InlineKeyboardButton(text="1h", callback_data=f"tf_1h_{symbol}")],
        [InlineKeyboardButton(text="4h", callback_data=f"tf_4h_{symbol}"), InlineKeyboardButton(text="1D", callback_data=f"tf_1d_{symbol}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_symbols")]
    ])

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def calculate_macd(df, fast=12, slow=26, signal=9):
    exp1 = df['close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['close'].ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1]

async def analyze_market(symbol: str, timeframe: str):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if not ohlcv: return "❌ خطا: ارز یافت نشد یا داده‌ای ندارد.", None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        last = df.iloc[-1]
        high_24h = df['high'].max()
        low_24h = df['low'].min()
        
        rsi = calculate_rsi(df).iloc[-1]
        macd, sig = calculate_macd(df)
        
        df['price_bin'] = pd.cut(df['close'], bins=10)
        poc = df.groupby('price_bin', observed=False)['volume'].sum().idxmax()
        poc_price = (poc.left + poc.right) / 2

        fvg = "✅ فعال" if last['low'] > df['high'].iloc[-3] else "❌ غیرفعال"
        ob = f"{df['low'].tail(5).min():.4f} - {df['high'].tail(5).max():.4f}"
        
        range_size = high_24h - low_24h
        amd = "Accumulation (انباشت)" if last['close'] < (low_24h + range_size*0.2) else "Distribution (توزیع)"
        
        fib_0618 = high_24h - (0.618 * (high_24h - low_24h))
        sentiment = "🟢 صعودی (Bullish)" if rsi > 50 and macd > sig else "🔴 نزولی (Bearish)"
        
        sl = last['close'] * 0.98 if sentiment == "🟢 صعودی (Bullish)" else last['close'] * 1.02
        tp1 = last['close'] * 1.01 if sentiment == "🟢 صعودی (Bullish)" else last['close'] * 0.99
        tp2 = last['close'] * 1.02 if sentiment == "🟢 صعودی (Bullish)" else last['close'] * 0.98
        tp3 = last['close'] * 1.04 if sentiment == "🟢 صعودی (Bullish)" else last['close'] * 0.96
        tp4 = last['close'] * 1.06 if sentiment == "🟢 صعودی (Bullish)" else last['close'] * 0.94

        report = (
            f"👑 **تحلیل جامع {symbol} - {timeframe}** 👑\n\n"
            f"💰 قیمت لحظه‌ای: `{last['close']:.6f}`\n"
            f"📈 ۲۴ساعت (High/Low): `{high_24h:.4f}` / `{low_24h:.4f}`\n\n"
            f"📊 **تکنیکال:**\n"
            f"• RSI: `{rsi:.2f}` | MACD: {'🟢' if macd>sig else '🔴'}\n"
            f"• POC (Volume): `{poc_price:.4f}`\n"
            f"• فیبوناچی (0.618): `{fib_0618:.4f}`\n\n"
            f"🧠 **پرایس‌اکشن & SMC:**\n"
            f"• FVG: {fvg}\n"
            f"• Order Block: `{ob}`\n"
            f"• چرخه AMD: {amd}\n"
            f"• نظر کلی: {sentiment}\n\n"
            f"🔥 **سیگنال پیشنهادی:**\n"
            f"• Leverage: 10x - 20x\n"
            f"• Entry Price: `{last['close']:.6f}`\n"
            f"• Stop Loss: `{sl:.6f}`\n"
            f"• TP 1: `{tp1:.6f}`\n"
            f"• TP 2: `{tp2:.6f}`\n"
            f"• TP 3: `{tp3:.6f}`\n"
            f"• TP 4: `{tp4:.6f}`"
        )
        return report, None
    except Exception as e: return f"❌ خطا: {str(e)}", None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("سلام! ارز مورد نظر رو انتخاب کن یا اسمش رو بنویس (مثلا ADA):", reply_markup=get_symbols_keyboard())

@dp.message()
async def handle_search(message: types.Message):
    symbol_input = message.text.upper().strip()
    if "/" not in symbol_input:
        symbol_input += "/USDT"
    await message.answer(f"جفت‌ارز `{symbol_input}` انتخاب شد. تایم‌فریم رو انتخاب کن:", reply_markup=get_timeframe_keyboard(symbol_input))

@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    if callback.data == "back_symbols": 
        await callback.message.edit_text("انتخاب ارز:", reply_markup=get_symbols_keyboard())
    elif callback.data.startswith("sym_"):
        s = callback.data.replace("sym_", "")
        await callback.message.edit_text(f"جفت‌ارز `{s}` انتخاب شد. تایم‌فریم رو انتخاب کن:", reply_markup=get_timeframe_keyboard(s))
    elif callback.data.startswith("tf_"):
        parts = callback.data.split("_")
        report, _ = await analyze_market(parts[2], parts[1])
        await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_timeframe_keyboard(parts[2]))
    await callback.answer()

# وب‌سرور برای پاسخ‌دهی به پینگ UptimeRobot و رندر
async def handle_ping(request):
    return web.Response(text="Bot is running and active!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Web server started on port {port}")

async def main():
    await start_web_server()
    if TOKEN:
        bot = Bot(token=TOKEN)
        logging.info("Starting bot polling...")
        await dp.start_polling(bot)
    else:
        logging.warning("BOT_TOKEN is not set. Web server is running, but bot polling will not start.")
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
