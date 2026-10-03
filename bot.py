import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np

# تنظیمات اولیه
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

exchange = ccxt.bingx({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# تابع تحلیل با والیوم پروفایل
async def get_signals(symbol="BTC/USDT:USDT", timeframe="15m"):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if not ohlcv: return "داده‌ای دریافت نشد."
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # محاسبه RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # محاسبه POC
        bins = 20
        df['bin'] = pd.cut(df['close'], bins=bins)
        profile = df.groupby('bin')['volume'].sum()
        poc_bin = profile.idxmax()
        poc_price = (poc_bin.left + poc_bin.right) / 2
        
        current_price = float(df['close'].iloc[-1])
        last_rsi = df['rsi'].iloc[-1]
        
        return (f"📊 تحلیل {symbol}\n"
                f"💰 قیمت: {current_price:.2f}\n"
                f"🎯 مرکز اصلی (POC): {poc_price:.2f}\n"
                f"📈 RSI: {last_rsi:.2f}")
    except Exception as e:
        return f"خطا: {str(e)}"

# هندلرها
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("ربات تریدر فعال است. برای تحلیل از /analyze استفاده کنید.")

@dp.message(Command("analyze"))
async def cmd_analyze(message: types.Message):
    result = await get_signals()
    await message.answer(result)

# سرور کمکی برای روشن ماندن در Render
async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
