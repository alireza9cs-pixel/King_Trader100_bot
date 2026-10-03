import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# استفاده از صرافی سازگار و استاندارد برای دریافت دیتای مارکت
exchange = ccxt.bingx({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

async def get_signals(symbol="BTC/USDT:USDT", timeframe="15m"):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # محاسبه RSI ساده
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        current_price = df['close'].iloc[-1]
        last_rsi = df['rsi'].iloc[-1]
        
        signal = "⏳ شرایط ورود فعلاً مهیا نیست (رنج)"
        if last_rsi < 30:
            signal = "🟢 سیگنال خرید (LONG / Oversold)"
        elif last_rsi > 70:
            signal = "🔴 سیگنال فروش (SHORT / Overbought)"
            
        return f"📊 وضعیت نماد {symbol} ({timeframe}):\n💰 قیمت فعلی: {current_price}\n📈 شاخص RSI: {last_rsi:.2f}\n🎯 وضعیت: {signal}"
    except Exception as e:
        return f"خطا در دریافت دیتا: {str(e)}"

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("سلام سلطان! 👑\nربات تریدر اختصاصی شما با موفقیت فعال شد.\n\nبرای تحلیل قیمت دستور /analyze رو بفرست.")

@dp.message(Command("analyze"))
async def analyze_handler(message: types.Message):
    await message.answer("⏳ در حال تحلیل بازار...")
    res = await get_signals("BTC/USDT:USDT", "15m")
    await message.answer(res)

async def main():
    try:
        print("Bot is starting...")
        await dp.start_polling(bot)
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
