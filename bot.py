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

# خواندن مستقیم توکن از رندر
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

exchange = ccxt.mexc({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

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

async def analyze_market(symbol: str, timeframe: str = '1h'):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if not ohlcv or len(ohlcv) < 30:
            return None, f"داده‌ای برای {symbol} یافت نشد."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        last_close = df['close'].iloc[-1]
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
            if c3_low > c1_high:
                fvg_text = f"🟢 FVG صعودی در {c1_high:.4f} تا {c3_low:.4f}"
            elif c3_high < c1_low:
                fvg_text = f"🔴 FVG نزولی در {c3_high:.4f} تا {c1_low:.4f}"

        ob_text = f"محدوده عرضه/تقاضا: {df['low'].tail(10).min():.4f} تا {df['high'].tail(10).max():.4f}"

        range_size = high_max - low_min
        if last_close > (high_max - range_size * 0.25):
            amd_status = "توزیع (Distribution)"
        elif last_close < (low_min + range_size * 0.25):
            amd_status = "انباشت (Accumulation)"
        else:
            amd_status = "دستکاری / رنج (Manipulation)"

        report = (
            f"👑 **تحلیل King Trader** 👑\n\n"
            f"🪙 **جفت‌ارز:** `{symbol}`\n"
            f"⏱ **تایم‌فریم:** `{timeframe}`\n"
            f"💵 **قیمت:** `{last_close}`\n\n"
            f"📊 **تکنیکال:**\n"
            f"• **RSI (14):** `{rsi:.2f}`\n"
            f"• **MACD:** {macd_status}\n"
            f"• **POC:** `{poc_price:.4f}`\n\n"
            f"📐 **فیبوناچی:**\n"
            f"• 0.382: `{fib_382:.4f}`\n"
            f"• 0.500: `{fib_500:.4f}`\n"
            f"• 0.618: `{fib_618:.4f}`\n\n"
            f"🧠 **پرایس‌اکشن SMC:**\n"
            f"• **FVG:** {fvg_text}\n"
            f"• **اردر بلاک:** {ob_text}\n\n"
            f"🔄 **چرخه AMD:**\n"
            f"• **فاز:** `{amd_status}`"
        )
        return report, None
    except Exception as e:
        return None, str(e)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام! به ربات King Trader خوش آمدید. 👑\n\n"
        "یک ارز انتخاب کنید یا نماد هر ارزی را تایپ کنید (مثل SOL یا PEPE):",
        reply_markup=get_symbols_keyboard()
    )

@dp.message()
async def handle_custom_symbol(message: types.Message):
    raw = message.text.strip().upper()
    symbol = raw if "/" in raw else f"{raw}/USDT"
    await message.answer(
        f"جفت‌ارز `{symbol}` انتخاب شد.\nتایم‌فریم را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard(symbol)
    )

@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    data = callback.data

    if data == "back_symbols":
        await callback.message.edit_text(
            "جفت‌ارز مورد نظر را انتخاب یا تایپ کنید:",
            reply_markup=get_symbols_keyboard()
        )
        await callback.answer()
        return

    if data == "help_custom":
        await callback.answer("کافیه نماد ارز را به انگلیسی بفرستید (مثلاً: TON یا DOGE)", show_alert=True)
        return

    if data.startswith("sym_"):
        symbol = data.replace("sym_", "")
        await callback.message.edit_text(
            f"جفت‌ارز: `{symbol}`\nتایم‌فریم را انتخاب کنید:",
            reply_markup=get_timeframe_keyboard(symbol)
        )
        await callback.answer()
        return

    if data.startswith("tf_"):
        parts = data.split("_")
        timeframe = parts[1]
        symbol = parts[2]

        await callback.message.edit_text(f"⏳ در حال تحلیل `{symbol}` ({timeframe})...")
        report, err = await analyze_market(symbol, timeframe)
        if err:
            await callback.message.edit_text(
                f"❌ خطا در تحلیل `{symbol}`: {err}",
                reply_markup=get_symbols_keyboard()
            )
        else:
            await callback.message.edit_text(
                report,
                parse_mode="Markdown",
                reply_markup=get_timeframe_keyboard(symbol)
            )
        await callback.answer()

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    try:
        await start_web_server()
        await dp.start_polling(bot)
    finally:
        await exchange.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
