import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

exchange = ccxt.bingx({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def get_timeframe_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⏱ 15 دقیقه", callback_data="tf_15m")
    builder.button(text="⏱ 1 ساعت", callback_data="tf_1h")
    builder.button(text="⏱ 4 ساعت", callback_data="tf_4h")
    builder.button(text="⏱ 1 روز", callback_data="tf_1d")
    builder.adjust(2, 2)
    return builder.as_markup()

async def get_signals(symbol="BTC/USDT:USDT", timeframe="15m"):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if not ohlcv:
            return "داده‌ای از صرافی دریافت نشد."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        df['rsi'] = 100 - (100 / (1 + rs))

        bins = 20
        df['bin'] = pd.cut(df['close'], bins=bins)
        profile = df.groupby('bin', observed=False)['volume'].sum()
        poc_bin = profile.idxmax()
        poc_price = (poc_bin.left + poc_bin.right) / 2

        current_price = float(df['close'].iloc[-1])
        last_rsi = float(df['rsi'].iloc[-1])

        if last_rsi < 30:
            status = "🟢 اشباع فروش (احتمال صعود)"
        elif last_rsi > 70:
            status = "🔴 اشباع خرید (احتمال اصلاح)"
        else:
            status = "⚪️ محدوده خنثی"

        return (
            f"📊 تحلیل جفت‌ارز: {symbol}\n"
            f"⏱ تایم‌فریم: {timeframe}\n"
            f"─────────────────\n"
            f"💰 قیمت فعلی: {current_price:,.2f}$\n"
            f"🎯 مرکز حجم معاملات (POC): {poc_price:,.2f}$\n"
            f"📈 شاخص RSI: {last_rsi:.2f}\n"
            f"🚦 وضعیت: {status}\n"
            f"─────────────────\n"
            f"💡 تایم‌فریم دیگری را انتخاب کنید:"
        )
    except Exception as e:
        logging.exception("Error in analysis")
        return f"خطا در تحلیل: {str(e)}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام! به ربات تحلیل‌گر King Trader خوش آمدید. 👑\n\n"
        "تایم‌فریم مورد نظرتان را برای تحلیل BTC انتخاب کنید:",
        reply_markup=get_timeframe_keyboard()
    )

@dp.message(Command("analyze"))
async def cmd_analyze(message: types.Message):
    await message.answer(
        "لطفاً تایم‌فریم مد نظر خود را برای تحلیل بیت‌کوین انتخاب کنید:",
        reply_markup=get_timeframe_keyboard()
    )

@dp.callback_query(F.data.startswith("tf_"))
async def handle_timeframe(callback: types.CallbackQuery):
    tf = callback.data.replace("tf_", "")
    await callback.answer("در حال دریافت اطلاعات بازار...")
    await callback.message.edit_text("⏳ در حال تحلیل بازار... لطفاً چند ثانیه صبر کنید.")
    result = await get_signals(timeframe=tf)
    await callback.message.edit_text(result, reply_markup=get_timeframe_keyboard())

async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    port = int(os.environ.get("PORT", 8080))
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
