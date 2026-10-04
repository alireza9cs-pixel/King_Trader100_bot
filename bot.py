import os
import asyncio
import logging
from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# توکن ربات از متغیرهای محیطی خوانده می‌شود
TOKEN = os.getenv("BOT_TOKEN", "").strip()

# صرافی MEXC برای قراردادهای فیوچرز
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
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست ارزها", callback_data="back_to_symbols")
        ]
    ])

async def analyze_market(symbol: str, timeframe: str = '15m'):
    try:
        # دریافت ۳۰۰ کندل جهت محاسبه دقیق EMA200
        limit = 300
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 200:
            return "❌ داده‌های کافی از صرافی دریافت نشد. لطفاً از نمادهای معتبر استفاده کنید."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # محاسبه EMA 50 و EMA 200
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # محاسبه استاندارد RSI
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        # محاسبه MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        # محاسبه ATR
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

        # سیستم امتیازدهی
        score = 0
        if current_price > ema50_val:
            score += 1
        else:
            score -= 1

        if current_price > ema200_val:
            score += 1
        else:
            score -= 1

        if macd_val > macd_sig:
            score += 1
        else:
            score -= 1

        if rsi_val > 53:
            score += 1
        elif rsi_val < 47:
            score -= 1

        # تعیین جهت ورود و اهداف
        if score >= 2:
            direction = "🟢 صعودی (Long / Bullish)"
            sl = round(current_price - (1.2 * atr_val), 4)
            tp1 = round(current_price + (1.5 * atr_val), 4)
            tp2 = round(current_price + (2.5 * atr_val), 4)
            tp3 = round(current_price + (3.5 * atr_val), 4)
            tp4 = round(current_price + (5.0 * atr_val), 4)
        elif score <= -2:
            direction = "🔴 نزولی (Short / Bearish)"
            sl = round(current_price + (1.2 * atr_val), 4)
            tp1 = round(current_price - (1.5 * atr_val), 4)
            tp2 = round(current_price - (2.5 * atr_val), 4)
            tp3 = round(current_price - (3.5 * atr_val), 4)
            tp4 = round(current_price - (5.0 * atr_val), 4)
        else:
            direction = "⚪️ خنثی / بدون معامله (صبر برای خروج از رِنج)"
            sl = tp1 = tp2 = tp3 = tp4 = "-"

        report = (
            f"📊 <b>گزارش تحلیل تکنیکال</b>\n\n"
            f"🔹 <b>نماد:</b> <code>{symbol}</code>\n"
            f"⏱ <b>تایم‌فریم:</b> <code>{timeframe}</code>\n"
            f"💵 <b>Entry Price:</b> <code>{current_price}</code>\n"
            f"📈 <b>سیگنال:</b> {direction}\n\n"
            f"🎯 <b>اهداف سود (Take Profit):</b>\n"
            f"  ▫️ TP 1: <code>{tp1}</code>\n"
            f"  ▫️ TP 2: <code>{tp2}</code>\n"
            f"  ▫️ TP 3: <code>{tp3}</code>\n"
            f"  ▫️ TP 4: <code>{tp4}</code>\n\n"
            f"🛑 <b>حد ضرر (Stop Loss):</b> <code>{sl}</code>\n\n"
            f"📊 <b>شاخص RSI:</b> <code>{rsi_val:.2f}</code>\n"
            f"📉 <b>وضعیت MACD:</b> {'گاوی (Bullish)' if macd_val > macd_sig else 'خرسی (Bearish)'}\n"
            f"📏 <b>وضعیت نسبت به EMA200:</b> {'بالای میانگین' if current_price > ema200_val else 'زیر میانگین'}"
        )
        return report

    except Exception as e:
        logging.error(f"Analysis error: {e}")
        return f"❌ خطایی در تحلیل {symbol} رخ داد: {str(e)}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام! به ربات تحلیل تکنیکال خوش آمدید.\nارز مورد نظر خود را برای تحلیل انتخاب کنید:",
        reply_markup=get_symbols_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith('sym:'))
async def process_symbol_select(callback_query: types.CallbackQuery):
    symbol = callback_query.data.split('sym:')[1]
    await callback_query.message.edit_text(
        f"ارز انتخابی: <b>{symbol}</b>\nلطفاً تایم‌فریم مورد نظر را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard(symbol)
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('tf:'))
async def process_timeframe_select(callback_query: types.CallbackQuery):
    await callback_query.answer()
    data_str = callback_query.data[3:]
    symbol, tf = data_str.rsplit(':', 1)
    
    await callback_query.message.edit_text("⏳ در حال دریافت داده‌ها و تحلیل هوشمند... لطفاً شکیبا باشید.")
    result = await analyze_market(symbol, tf)
    await callback_query.message.edit_text(result, reply_markup=get_timeframe_keyboard(symbol))

@dp.callback_query(lambda c: c.data == 'back_to_symbols')
async def process_back(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "ارز مورد نظر خود را برای تحلیل انتخاب کنید:",
        reply_markup=get_symbols_keyboard()
    )

@dp.message()
async def process_custom_symbol(message: types.Message):
    raw_text = message.text.strip().upper()
    if "/" not in raw_text:
        symbol = f"{raw_text}/USDT:USDT"
    else:
        symbol = raw_text
    
    await message.answer(
        f"ارز انتخابی: <b>{symbol}</b>\nلطفاً تایم‌فریم مورد نظر را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard(symbol)
    )

async def handle_ping(request):
    return web.Response(text="Bot is awake and running perfectly!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/ping", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")

async def main():
    if not TOKEN:
        logging.error("BOT_TOKEN is not set in environment variables!")
        return

    # استفاده از DefaultBotProperties در aiogram 3.x
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await start_web_server()
    logging.info("Starting Telegram Bot Polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
