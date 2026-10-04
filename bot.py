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

# خواندن مستقیم توکن از تنظیمات رندر (امن‌ترین حالت)
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

exchange = ccxt.mexc({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# دکمه‌ها
def get_symbols_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="BTC/USDT", callback_data="sym_BTC/USDT"),
            InlineKeyboardButton(text="ETH/USDT", callback_data="sym_ETH/USDT"),
            InlineKeyboardButton(text="SOL/USDT", callback_data="sym_SOL/USDT")
        ],
        [
            InlineKeyboardButton(text="PEPE/USDT", callback_data="sym_PEPE/USDT"),
            InlineKeyboardButton(text="DOGE/USDT", callback_data="sym_DOGE/USDT"),
            InlineKeyboardButton(text="XRP/USDT", callback_data="sym_XRP/USDT")
        ],
        [
            InlineKeyboardButton(text="✍️ راهنما: نماد دلخواه", callback_data="help_custom")
        ]
    ])

def get_timeframe_keyboard(symbol):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="15 دقیقه", callback_data=f"tf_15m_{symbol}"),
            InlineKeyboardButton(text="1 ساعته", callback_data=f"tf_1h_{symbol}")
        ],
        [
            InlineKeyboardButton(text="4 ساعته", callback_data=f"tf_4h_{symbol}"),
            InlineKeyboardButton(text="روزانه (1D)", callback_data=f"tf_1d_{symbol}")
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="back_symbols")
        ]
    ])

# محاسبات فنی
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

# تابع اصلی تحلیل که سیگنال هم اضافه شده
async def analyze_market(symbol: str, timeframe: str = '1h'):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if not ohlcv or len(ohlcv) < 30:
            return None, f"داده‌ای برای {symbol} یافت نشد."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        last_close = df['close'].iloc[-1]
        
        # --- محاسبات سیگنال جدید ---
        leverage = "10x - 20x"
        sl = last_close * 0.985  # 1.5% ریسک
        risk = last_close - sl
        tp1 = last_close + (risk * 1.5)
        tp2 = last_close + (risk * 2.5)
        tp3 = last_close + (risk * 4.0)

        # محاسبات قبلی
        high_max = df['high'].max()
        low_min = df['low'].min()
        rsi = calculate_rsi(df['close']).iloc[-1]
        macd_line, signal_line, hist = calculate_macd(df['close'])
        curr_macd = macd_line.iloc[-1]
        curr_signal = signal_line.iloc[-1]
        macd_status = "🟢 صعودی" if curr_macd > curr_signal else "🔴 نزولی"

        df['price_bin'] = pd.cut(df['close'], bins=20)
        vol_profile = df.groupby('price_bin', observed=False)['volume'].sum()
        poc_bin = vol_profile.idxmax()
        poc_price = (poc_bin.left + poc_bin.right) / 2

        diff = high_max - low_min
        fib_382 = high_max - 0.382 * diff
        fib_500 = high_max - 0.500 * diff
        fib_618 = high_max - 0.618 * diff

        fvg_text = "عدم مشاهده FVG فعال"
        if len(df) >= 3:
            c1_high, c1_low = df['high'].iloc[-3], df['low'].iloc[-3]
            c3_high, c3_low = df['high'].iloc[-1], df['low'].iloc[-1]
            if c3_low > c1_high: fvg_text = f"🟢 FVG صعودی در {c1_high:.4f} تا {c3_low:.4f}"
            elif c3_high < c1_low: fvg_text = f"🔴 FVG نزولی در {c3_high:.4f} تا {c1_low:.4f}"

        ob_text = f"{df['low'].tail(10).min():.4f} تا {df['high'].tail(10).max():.4f}"

        report = (
            f"👑 **تحلیل King Trader** 👑\n\n"
            f"🪙 **جفت‌ارز:** `{symbol}`\n"
            f"⏱ **تایم‌فریم:** `{timeframe}`\n"
            f"💵 **قیمت:** `{last_close:.6f}`\n\n"
            f"🔥 **سیگنال پیشنهادی:**\n"
            f"• **Leverage:** `{leverage}`\n"
            f"• **Entry Price:** `{last_close:.6f}`\n"
            f"• **Stop Loss:** `{sl:.6f}`\n"
            f"• **TP 1:** `{tp1:.6f}`\n"
            f"• **TP 2:** `{tp2:.6f}`\n"
            f"• **TP 3:** `{tp3:.6f}`\n\n"
            f"📊 **تکنیکال:**\n"
            f"• **RSI:** `{rsi:.2f}` | **MACD:** {macd_status}\n"
            f"• **POC:** `{poc_price:.4f}`\n\n"
            f"🧠 **SMC و فیبو:**\n"
            f"• **FVG:** {fvg_text}\n"
            f"• **اردر بلاک:** {ob_text}\n"
            f"• **فیبو (0.618):** `{fib_618:.4f}`"
        )
        return report, None
    except Exception as e:
        return None, str(e)

# هندل کردن پیام‌ها
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("سلام! ارز انتخاب کن:", reply_markup=get_symbols_keyboard())

@dp.message()
async def handle_custom_symbol(message: types.Message):
    raw = message.text.strip().upper()
    symbol = raw if "/" in raw else f"{raw}/USDT"
    await message.answer(f"جفت‌ارز `{symbol}` انتخاب شد. تایم‌فریم را انتخاب کنید:", reply_markup=get_timeframe_keyboard(symbol))

@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    data = callback.data
    if data == "back_symbols":
        await callback.message.edit_text("انتخاب ارز:", reply_markup=get_symbols_keyboard())
    elif data == "help_custom":
        await callback.answer("نماد ارز را بفرست (مثلاً: TON یا DOGE)", show_alert=True)
    elif data.startswith("sym_"):
        symbol = data.replace("sym_", "")
        await callback.message.edit_text(f"جفت‌ارز `{symbol}`. انتخاب تایم‌فریم:", reply_markup=get_timeframe_keyboard(symbol))
    elif data.startswith("tf_"):
        parts = data.split("_")
        timeframe, symbol = parts[1], parts[2]
        await callback.message.edit_text(f"⏳ تحلیل در حال انجام...")
        report, err = await analyze_market(symbol, timeframe)
        if err: await callback.message.edit_text(f"❌ خطا: {err}", reply_markup=get_symbols_keyboard())
        else: await callback.message.edit_text(report, parse_mode="Markdown", reply_markup=get_timeframe_keyboard(symbol))
    await callback.answer()

async def start_web_server():
    app = web.Application()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

async def main():
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
