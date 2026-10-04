import os
import ccxt
import pandas as pd
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# تنظیمات ربات
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=GAPGPTMASKTOKENrycn7cx42j9X0X)
dp = Dispatcher()

# اتصال به صرافی
exchange = ccxt.mexc()

def get_market_data(symbol, timeframe='1h'):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def calculate_analysis(df):
    close = df['close']
    # محاسبه ساده RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    current_rsi = rsi.iloc[-1]
    
    # محاسبه سیگنال‌دهی
    current_price = close.iloc[-1]
    leverage = "10x - 20x" # اهرم پیشنهادی
    sl = current_price * 0.985  # 1.5% استاپ لاس
    risk = current_price - sl
    
    tp1 = current_price + (risk * 1.5)
    tp2 = current_price + (risk * 2.5)
    tp3 = current_price + (risk * 4.0)
    
    return current_rsi, current_price, leverage, sl, tp1, tp2, tp3

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("سلام! ارز مورد نظرت رو بفرست (مثلاً BTC/USDT):")

@dp.message()
async def handle_message(message: types.Message):
    symbol = message.text.upper()
    if "/" not in symbol:
        symbol += "/USDT"
    
    try:
        df = get_market_data(symbol)
        rsi, price, leverage, sl, tp1, tp2, tp3 = calculate_analysis(df)
        
        text = f"""
👑 سیگنال پیشنهادی ربات 👑

💰 جفت‌ارز: {symbol}
💵 قیمت لحظه‌ای: {price:.6f}
⚡️ Leverage: {leverage}

🟢 Entry Price: {price:.6f}
🔴 Stop Loss: {sl:.6f}

🎯 Take Profit 1: {tp1:.6f}
🎯 Take Profit 2: {tp2:.6f}
🚀 Take Profit 3: {tp3:.6f}

📊 وضعیت فنی:
• RSI: {rsi:.2f}
• پیشنهاد: رعایت مدیریت سرمایه الزامی است.
"""
        await message.answer(text)
    except Exception as e:
        await message.answer(f"خطا در دریافت دیتا: {str(e)}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
