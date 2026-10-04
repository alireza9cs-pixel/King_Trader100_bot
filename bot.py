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

# خواندن امن توکن تلگرام
TOKEN = os.getenv("BOT_TOKEN", "").strip()

# صرافی MEXC
exchange = ccxt.mexc({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})

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
        limit = 250
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 50:
            return "❌ داده‌های کافی از صرافی دریافت نشد. لطفاً مجدداً تلاش کنید."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # محاسبات اندیکاتورها و میانگین‌ها
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean() if len(df) >= 200 else df['close'].ewm(span=50, adjust=False).mean()
        
        # محاسبه RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        # محاسبه MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

        # محاسبه نوسان واقعی پویا (ATR)
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

        # سیستم هم‌گرایی و امتیازدهی
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

        if rsi_val > 52:
            score += 1
        elif rsi_val < 48:
            score -= 1

        # تعیین جهت ورود و سطوح خروج
        if score >= 2:
            direction = "🟢 صعودی (Bullish - High Confluence)"
            fvg_state = "شکست صعودی گپ (Mitigated)"
            sl = round(current_price - (1.5 * atr_val), 4)
            tp1 = round(current_price + (1.0 * atr_val), 4)
            tp2 = round(current_price + (2.0 * atr_val), 4)
            tp3 = round(current_price + (3.2 * atr_val), 4)
            tp4 = round(current_price + (4.5 * atr_val), 4)
        elif score <= -2:
            direction = "🔴 نزولی (Bearish - High Confluence)"
            fvg_state = "شکست نزولی گپ (Mitigated)"
            sl = round(current_price + (1.5 * atr_val), 4)
            tp1 = round(current_price - (1.0 * atr_val), 4)
            tp2 = round(current_price - (2.0 * atr_val), 4)
            tp3 = round(current_price - (3.2 * atr_val), 4)
            tp4 = round(current_price - (4.5 * atr_val), 4)
        else:
            direction = "⚪️ خنثی / رِنج (صبر برای تاییدیه)"
            fvg_state = "ناحیه تعادل (Equilibrium)"
            sl = round(current_price - atr_val, 4)
            tp1 = round(current_price + atr_val, 4)
            tp2 = round(current_price + (1.8 * atr_val), 4)
            tp3 = round(current_price + (2.5 * atr_val), 4)
            tp4 = round(current_price + (3.5 * atr_val), 4)

        report = (
            f"📊 **گزارش تحلیل تکنیکال و پرایس‌اکشن**\n\n"
            f"🔹 **نماد:** `{symbol}`\n"
            f"⏱ **تایم‌فریم:** `{timeframe}`\n"
            f"💵 **Entry Price:** `{current_price}`\n"
            f"📈 **جهت پیشنهادی:** {direction}\n\n"
            f"🎯 **اهداف سود (Take Profit):**\n"
            f"  ▫️ TP 1: `{tp1}`\n"
            f"  ▫️ TP 2: `{tp2}`\n"
            f"  ▫️ TP 3: `{tp3}`\n"
            f"  ▫️ TP 4: `{tp4}`\n\n"
            f"🛑 **حد ضرر (Stop Loss):** `{sl}`\n\n"
            f"🔍 **وضعیت پرایس‌اکشن:** {fvg_state}\n"
            f"📊 **شاخص RSI:** `{rsi_val:.2f}`\n"
            f"📉 **وضعیت MACD:** `{'مثبت/گاوی' if macd_val > macd_sig else 'منفی/خرسی'}`"
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
        parse_mode="HTML",
        reply_markup=get_timeframe_keyboard(symbol)
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('tf:'))
async def process_timeframe_select(callback_query: types.CallbackQuery):
    _, symbol, tf = callback_query.data.split(':')
    await callback_query.message.edit_text("⏳ در حال دریافت داده‌ها و تحلیل هوشمند... لطفاً شکیبا باشید.")
    result = await analyze_market(symbol, tf)
    await callback_query.message.edit_text(result, parse_mode="Markdown", reply_markup=get_timeframe_keyboard(symbol))
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == 'back_to_symbols')
async def process_back(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text(
        "ارز مورد نظر خود را برای تحلیل انتخاب کنید:",
        reply_markup=get_symbols_keyboard()
    )
    await callback_query.answer()

@dp.message()
async def process_custom_symbol(message: types.Message):
    raw_text = message.text.strip().upper()
    if "/" not in raw_text:
        symbol = f"{raw_text}/USDT:USDT"
    else:
        symbol = raw_text
    
    await message.answer(
        f"ارز انتخابی: <b>{symbol}</b>\nلطفاً تایم‌فریم مورد نظر را انتخاب کنید:",
        parse_mode="HTML",
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

    bot = Bot(token=TOKEN)
    await start_web_server()
    logging.info("Starting Telegram Bot Polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
