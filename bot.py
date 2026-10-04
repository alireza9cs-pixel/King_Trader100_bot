import os
import asyncio
import logging
from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# تنظیمات لاگ
logging.basicConfig(level=logging.INFO)

# دریافت توکن ربات از متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# تعریف صرافی KCEX (پشتیبانی استاندارد در ccxt)
exchange = ccxt.kcex({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}  # یا spot در صورت نیاز
})

# وضعیت کاربر برای ذخیره ارز انتخابی
USER_SELECTED_SYMBOL = {}

# منوی ارزهای محبوب
def get_symbols_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
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
            InlineKeyboardButton(text="✍️ راهنما: ارسال نماد دلخواه", callback_data="help_custom")
        ]
    ])
    return keyboard

# منوی تایم‌فریم‌ها
def get_timeframe_keyboard(symbol):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="15 دقیقه", callback_data=f"tf_15m_{symbol}"),
            InlineKeyboardButton(text="1 ساعته", callback_data=f"tf_1h_{symbol}")
        ],
        [
            InlineKeyboardButton(text="4 ساعته", callback_data=f"tf_4h_{symbol}"),
            InlineKeyboardButton(text="روزانه (1D)", callback_data=f"tf_1d_{symbol}")
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست ارزها", callback_data="back_symbols")
        ]
    ])
    return keyboard

# تابع محاسبه RSI
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

# تابع محاسبه MACD
def calculate_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

# تحلیل کامل تکنیکال، SMC و AMD
async def analyze_market(symbol: str, timeframe: str = '1h'):
    try:
        # دریافت داده‌های کندلی از KCEX
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if not ohlcv or len(ohlcv) < 30:
            return None, "خطا در دریافت کندل‌ها از صرافی KCEX."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        last_close = df['close'].iloc[-1]
        high_max = df['high'].max()
        low_min = df['low'].min()
        
        # 1. RSI
        rsi_series = calculate_rsi(df['close'])
        current_rsi = rsi_series.iloc[-1]
        
        # 2. MACD
        macd_line, signal_line, hist = calculate_macd(df['close'])
        curr_macd = macd_line.iloc[-1]
        curr_signal = signal_line.iloc[-1]
        macd_status = "🟢 صعودی (Bullish Cross)" if curr_macd > curr_signal else "🔴 نزولی (Bearish Cross)"
        
        # 3. Volume Profile (POC)
        bins = 20
        df['price_bin'] = pd.cut(df['close'], bins=bins)
        vol_profile = df.groupby('price_bin', observed=False)['volume'].sum()
        poc_bin = vol_profile.idxmax()
        poc_price = (poc_bin.left + poc_bin.right) / 2
        
        # 4. فیبوناچی
        diff = high_max - low_min
        fib_382 = high_max - 0.382 * diff
        fib_500 = high_max - 0.500 * diff
        fib_618 = high_max - 0.618 * diff
        
        # 5. Smart Money Concept (SMC)
        # FVG Check
        fvg_text = "عدم مشاهده FVG فعال"
        if len(df) >= 3:
            c1_high, c1_low = df['high'].iloc[-3], df['low'].iloc[-3]
            c3_high, c3_low = df['high'].iloc[-1], df['low'].iloc[-1]
            if c3_low > c1_high:
                fvg_text = f"🟢 FVG صعودی در محدوده {c1_high:.4f} تا {c3_low:.4f}"
            elif c3_high < c1_low:
                fvg_text = f"🔴 FVG نزولی در محدوده {c3_high:.4f} تا {c1_low:.4f}"
        
        # Order Block ساده
        ob_text = f"محدوده عرضه/تقاضا: {df['low'].tail(10).min():.4f} تا {df['high'].tail(10).max():.4f}"
        
        # 6. چرخه ICT / AMD
        range_size = high_max - low_min
        if last_close > (high_max - range_size * 0.25):
            amd_status = "توزیع / فاز خروج (Distribution)"
        elif last_close < (low_min + range_size * 0.25):
            amd_status = "جمع‌آوری / انباشت (Accumulation)"
        else:
            amd_status = "دستکاری / نوسان در رنج (Manipulation)"

        report = (
            f"👑 **تحلیل پیشرفته King Trader (KCEX)** 👑\n\n"
            f"🪙 **جفت‌ارز:** `{symbol}`\n"
            f"⏱ **تایم‌فریم:** `{timeframe}`\n"
            f"💵 **قیمت فعلی:** `{last_close}`\n\n"
            f"📊 **شاخص‌های تکنیکال:**\n"
            f"• **RSI (14):** `{current_rsi:.2f}`\n"
            f"• **MACD وضعیت:** {macd_status}\n"
            f"• **POC (نقطه کنترل حجم):** `{poc_price:.4f}`\n\n"
            f"📐 **سطوح طلایی فیبوناچی:**\n"
            f"• 0.382: `{fib_382:.4f}`\n"
            f"• 0.500: `{fib_500:.4f}`\n"
            f"• 0.618: `{fib_618:.4f}`\n\n"
            f"🧠 **تحلیل پرایس‌اکشن اسمارت‌مانی (SMC):**\n"
            f"• **وضعیت FVG:** {fvg_text}\n"
            f"• **بلاک‌های قیمت:** {ob_text}\n\n"
            f"🔄 **چرخه مارکت (AMD):**\n"
            f"• **فاز بازار:** `{amd_status}`"
        )
        return report, None
    except Exception as e:
        return None, f"خطا در تحلیل نماد {symbol}: {str(e)}"

# هندلر دستور /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام به ربات تحلیل‌گر King Trader خوش آمدید! 👑\n\n"
        "لطفاً یکی از جفت‌ارزهای زیر از صرافی **KCEX** را انتخاب کنید،\n"
        "یا **نام هر ارزی** که می‌خواهید را تایپ کرده و بفرستید (مثلاً: `SOL` یا `PEPE` یا `TON`):",
        reply_markup=get_symbols_keyboard()
    )

# هندلر دریافت پیام متنی (برای وارد کردن هر ارز دلخواه)
@dp.message()
async def handle_custom_symbol(message: types.Message):
    raw_text = message.text.strip().upper()
    
    # اگر اسلش ندارد خودکار به فرمت KCEX تبدیل کن
    if "/" not in raw_text:
        symbol = f"{raw_text}/USDT"
    else:
        symbol = raw_text
        
    await message.answer(
        f"جفت‌ارز `{symbol}` انتخاب شد.\nحالا تایم‌فریم مورد نظر را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard(symbol)
    )

# هندلرهای کال‌بک دکمه‌ها
@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    data = callback.data

    if data == "back_symbols":
        await callback.message.edit_text(
            "لطفاً جفت‌ارز مورد نظر خود از **KCEX** را انتخاب کنید یا نام ارز را تایپ کنید:",
            reply_markup=get_symbols_keyboard()
        )
        await callback.answer()
        return

    if data == "help_custom":
        await callback.answer(
            "کافیه اسم هر ارزی رو انگلیسی بنویسی و بفرستی!\nمثلاً: DOGE یا ETH یا SHIB",
            show_alert=True
        )
        return

    if data.startswith("sym_"):
        symbol = data.replace("sym_", "")
        await callback.message.edit_text(
            f"جفت‌ارز انتخابی: `{symbol}`\nحالا تایم‌فریم تحلیل را مشخص کنید:",
            reply_markup=get_timeframe_keyboard(symbol)
        )
        await callback.answer()
        return

    if data.startswith("tf_"):
        parts = data.split("_")
        timeframe = parts[1]
        symbol = parts[2]
        
        await callback.message.edit_text(f"⏳ در حال استخراج دیتای KCEX و تحلیل `{symbol}` در تایم‌فریم `{timeframe}`...")
        
        report, err = await analyze_market(symbol, timeframe)
        if err:
            await callback.message.edit_text(
                f"❌ متأسفانه نماد `{symbol}` یافت نشد یا دیتایی برای آن وجود ندارد.\n\nجزئیات: {err}",
                reply_markup=get_symbols_keyboard()
            )
        else:
            await callback.message.edit_text(
                report,
                parse_mode="Markdown",
                reply_markup=get_timeframe_keyboard(symbol)
            )
        await callback.answer()

# سرور کوچک برای جلوگیری از Sleep شدن در پلن رایگان Render
async def health_check(request):
    return web.Response(text="Bot is running smoothly on KCEX!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# تابع اجرای اصلی
async def main():
    try:
        await start_web_server()
        await dp.start_polling(bot)
    finally:
        await exchange.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
