import os
import io
import asyncio
import logging
from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import matplotlib

matplotlib.use('Agg')  # جلوگیری از ارور نبود GUI روی سرور

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    BufferedInputFile
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# GAPGPTMASKTOKENl07ryrl6szX2X= دریافت امن توکن GAPGPTMASKTOKENl07ryrl6szX3X=
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("متغیر محیطی BOT_TOKEN تنظیم نشده است. لطفاً آن را در بخش Environment پنل Render اضافه کنید.")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# GAPGPTMASKTOKENl07ryrl6szX4X= تنظیمات صرافی GAPGPTMASKTOKENl07ryrl6szX5X=
exchange = ccxt.mexc({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'},  # بازار فیوچرز
    'timeout': 15000,
})

# وضعیت کاربران
user_states = {}

# لیست ارزها و تایم‌فریم‌ها
SYMBOLS = {
    "BTC": "BTC/USDT:USDT",
    "ETH": "ETH/USDT:USDT",
    "SOL": "SOL/USDT:USDT",
    "PEPE": "PEPE/USDT:USDT"
}

TIMEFRAMES = {
    "1m": "1m", "5m": "5m", "15m": "15m",
    "1h": "1h", "4h": "4h", "1D": "1d"
}

# GAPGPTMASKTOKENl07ryrl6szX6X= ساخت کیبوردها GAPGPTMASKTOKENl07ryrl6szX7X=
def get_main_keyboard():
    buttons = [
        [
            InlineKeyboardButton(text="بیت‌کوین (BTC)", callback_data="sym_BTC"),
            InlineKeyboardButton(text="اتریوم (ETH)", callback_data="sym_ETH")
        ],
        [
            InlineKeyboardButton(text="سولانا (SOL)", callback_data="sym_SOL"),
            InlineKeyboardButton(text="پپه (PEPE)", callback_data="sym_PEPE")
        ],
        [
            InlineKeyboardButton(text="سیگنال‌یاب خودکار (Top 100)", callback_data="auto_scan")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_timeframe_keyboard():
    buttons = [
        [
            InlineKeyboardButton(text="1 دقیقه", callback_data="tf_1m"),
            InlineKeyboardButton(text="5 دقیقه", callback_data="tf_5m"),
            InlineKeyboardButton(text="15 دقیقه", callback_data="tf_15m")
        ],
        [
            InlineKeyboardButton(text="1 ساعته", callback_data="tf_1h"),
            InlineKeyboardButton(text="4 ساعته", callback_data="tf_4h"),
            InlineKeyboardButton(text="روزانه", callback_data="tf_1D")
        ],
        [
            InlineKeyboardButton(text="بازگشت به منوی ارزها", callback_data="back_to_symbols")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# GAPGPTMASKTOKENl07ryrl6szX8X= وب‌سرور کوچک برای Render GAPGPTMASKTOKENl07ryrl6szX9X=
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
    logging.info(f"Web server started on port {port}")

# GAPGPTMASKTOKENl07ryrl6szX10X= دریافت داده ও محاسبات GAPGPTMASKTOKENl07ryrl6szX11X=
async def fetch_ohlcv(symbol, timeframe, limit=120):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logging.error(f"Error fetching OHLCV for {symbol}: {e}")
        return None

def calculate_indicators(df):
    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df['rsi'] = 100 - (100 / (1 + rs))

    # EMA 20 & 50
    df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()

    # Volume Profile (تقریبی برای بازه اخیر)
    price_min = df['low'].min()
    price_max = df['high'].max()
    bins = np.linspace(price_min, price_max, 30)
    df['price_bin'] = pd.cut(df['close'], bins=bins)
    vol_profile = df.groupby('price_bin', observed=False)['volume'].sum()

    if not vol_profile.empty and vol_profile.sum() > 0:
        poc_bin = vol_profile.idxmax()
        poc = (poc_bin.left + poc_bin.right) / 2
        sorted_bins = vol_profile.sort_values(ascending=False)
        total_vol = vol_profile.sum()
        cum_vol = 0
        value_area_bins = []
        for b, v in sorted_bins.items():
            cum_vol += v
            value_area_bins.append(b)
            if cum_vol >= 0.70 * total_vol:
                break
        vah = max([b.right for b in value_area_bins])
        val = min([b.left for b in value_area_bins])
    else:
        poc = df['close'].iloc[-1]
        vah = poc * 1.01
        val = poc * 0.99

    return df, poc, vah, val

def generate_chart(df, symbol_name, tf, poc, vah, val):
    plt.style.use('dark_background')
    fig, (ax, ax_vol) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)

    # رسم قیمت
    ax.plot(df['timestamp'], df['close'], label='Close Price', color='#00ffcc', linewidth=1.5)
    ax.plot(df['timestamp'], df['ema20'], label='EMA 20', color='#ff007f', linestyle='--', alpha=0.7)
    ax.plot(df['timestamp'], df['ema50'], label='EMA 50', color='#ffaa00', linestyle='--', alpha=0.7)

    # سطوح والیوم پروفایل
    ax.axhline(poc, color='#ff3333', linestyle='-', linewidth=1.5, label=f'POC: {poc:.4f}')
    ax.axhline(vah, color='#33ff33', linestyle=':', linewidth=1.2, label=f'VAH: {vah:.4f}')
    ax.axhline(val, color='#3388ff', linestyle=':', linewidth=1.2, label=f'VAL: {val:.4f}')

    ax.set_title(f"{symbol_name} - {tf} (Volume Profile & EMAs)", fontsize=14, color='white')
    ax.legend(loc='upper left', facecolor='#222222', edgecolor='none')
    ax.grid(True, linestyle=':', alpha=0.3)

    # ولوم پایین
    colors = ['#00ffcc' if c >= o else '#ff3333' for c, o in zip(df['close'], df['open'])]
    ax_vol.bar(df['timestamp'], df['volume'], color=colors, alpha=0.7, width=0.005)
    ax_vol.grid(True, linestyle=':', alpha=0.3)
    ax_vol.set_ylabel("Volume")

    plt.xticks(rotation=30)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120)
    buf.seek(0)
    plt.close(fig)
    return buf

# GAPGPTMASKTOKENl07ryrl6szX12X= هندلرهای تلگرام GAPGPTMASKTOKENl07ryrl6szX13X=
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 **درود! به ربات تحلیل‌گر بازار فیوچرز خوش آمدید.**\n\n"
        "لطفاً یک ارز را برای دریافت تحلیل جامع چند تایم‌فریمه و سطوح Volume Profile انتخاب کنید:",
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith('sym_'))
async def process_symbol_select(callback: types.CallbackQuery):
    sym_key = callback.data.split('_')[1]
    user_states[callback.from_user.id] = {'symbol_key': sym_key}
    
    await callback.message.edit_text(
        f"✅ ارز انتخاب شد: **{sym_key}**\nحالا تایم‌فریم مورد نظرتان را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == 'back_to_symbols')
async def process_back(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "لطفاً یک ارز را انتخاب کنید:",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('tf_'))
async def process_timeframe_select(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in user_states or 'symbol_key' not in user_states[user_id]:
        await callback.message.edit_text("لطفاً دوباره از اول ارز را انتخاب کنید.", reply_markup=get_main_keyboard())
        await callback.answer()
        return

    tf_key = callback.data.split('_')[1]
    sym_key = user_states[user_id]['symbol_key']
    symbol = SYMBOLS[sym_key]
    tf = TIMEFRAMES[tf_key]

    await callback.message.edit_text(f"⏳ در حال پردازش و استخراج سطوح برای **{sym_key}** در تایم‌فریم **{tf}**...")
    await callback.answer()

    df = await fetch_ohlcv(symbol, tf)
    if df is None or len(df) < 50:
        await callback.message.answer("❌ خطا در دریافت دیتای صرافی. لطفاً بعداً دوباره امتحان کنید.")
        return

    df, poc, vah, val = calculate_indicators(df)
    last_close = df['close'].iloc[-1]
    last_rsi = df['rsi'].iloc[-1]
    last_ema20 = df['ema20'].iloc[-1]
    last_ema50 = df['ema50'].iloc[-1]

    # تعیین سیگنال تکنیکال
    signal = "خنثی ⚪"
    if last_close > poc and last_rsi > 50 and last_ema20 > last_ema50:
        signal = "صعودی / لانگ (Long) 🟢"
    elif last_close < poc and last_rsi < 50 and last_ema20 < last_ema50:
        signal = "نزولی / شورت (Short) 🔴"

    caption = (
        f"📊 **تحلیل زنده {sym_key} ({tf})**\n\n"
        f"💵 آخرین قیمت: `{last_close:.4f}`\n"
        f"📈 وضعیت: **{signal}**\n\n"
        f"📌 **سطوح ولوم پروفایل (Volume Profile):**\n"
        f"• VAH (سقف ارزش): `{vah:.4f}`\n"
        f"• POC (بیشترین حجم): `{poc:.4f}`\n"
        f"• VAL (کف ارزش): `{val:.4f}`\n\n"
        f"📐 **شاخص‌های فنی:**\n"
        f"• RSI (14): `{last_rsi:.1f}`\n"
        f"• EMA 20: `{last_ema20:.4f}`\n"
        f"• EMA 50: `{last_ema50:.4f}`\n\n"
        f"🎯 *نکته معاملاتی:* شکست یا بازگشت به POC نقطه ورود کم‌ریسک محسوب می‌شود."
    )

    chart_buf = generate_chart(df, sym_key, tf, poc, vah, val)
    input_file = BufferedInputFile(chart_buf.getvalue(), filename=f"{sym_key}_{tf}.png")

    await callback.message.answer_photo(
        photo=input_file,
        caption=caption,
        reply_markup=get_timeframe_keyboard()
    )

@dp.callback_query(lambda c: c.data == 'auto_scan')
async def process_auto_scan(callback: types.CallbackQuery):
    await callback.message.edit_text("🔍 در حال اسکن 10 ارز برتر فیوچرز MEXC... لطفاً شکیبا باشید.")
    await callback.answer()

    top_coins = ["BTC", "ETH", "SOL", "PEPE", "XRP", "DOGE"]
    signals = []

    for sym in top_coins:
        pair = f"{sym}/USDT:USDT"
        df = await fetch_ohlcv(pair, "15m", limit=60)
        if df is not None and len(df) >= 50:
            df, poc, vah, val = calculate_indicators(df)
            last_c = df['close'].iloc[-1]
            last_rsi = df['rsi'].iloc[-1]
            if last_c > poc and last_rsi > 55:
                signals.append(f"🟢 **{sym}**: سیگنال لانگ (قیمت بالای POC و RSI = {last_rsi:.0f})")
            elif last_c < poc and last_rsi < 45:
                signals.append(f"🔴 **{sym}**: سیگنال شورت (قیمت زیر POC و RSI = {last_rsi:.0f})")

    if not signals:
        result_text = "در حال حاضر در تایم‌فریم 15 دقیقه سیگنال قطعی پیدا نشد."
    else:
        result_text = "🎯 **نتایج اسکن فوری (15m):**\n\n" + "\n".join(signals)

    await callback.message.answer(result_text, reply_markup=get_main_keyboard())

# GAPGPTMASKTOKENl07ryrl6szX14X= تابع اصلی اجرا GAPGPTMASKTOKENl07ryrl6szX15X=
async def main():
    logging.info("Starting background web server for Render keepalive...")
    asyncio.create_task(start_web_server())

    logging.info("Starting Telegram Bot Polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
