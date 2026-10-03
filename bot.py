import os
import asyncio
import logging
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# تنظیم لاگ
logging.basicConfig(level=logging.INFO)

# خواندن اطلاعات از متغیرهای رندر (امن)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# اتصال به صرافی KCEX
exchange = ccxt.kcex({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

async def analyze_market(symbol="BTC/USDT:USDT", timeframe="15m"):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['rsi'] = calculate_rsi(df['close'])
        
        last_close = df['close'].iloc[-1]
        last_rsi = df['rsi'].iloc[-1]
        prev_high = df['high'].iloc[-50:-1].max()
        prev_low = df['low'].iloc[-50:-1].min()

        signal = None
        # استراتژی ساده‌شده کانفلوئنس (RSI + FVG/Swing)
        if last_rsi < 32 and last_close <= prev_low * 1.002:
            signal = {
                "type": "🟢 LONG",
                "symbol": symbol,
                "price": last_close,
                "sl": last_close * 0.985,
                "tp": last_close * 1.03,
                "rsi": round(last_rsi, 1)
            }
        elif last_rsi > 68 and last_close >= prev_high * 0.998:
            signal = {
                "type": "🔴 SHORT",
                "symbol": symbol,
                "price": last_close,
                "sl": last_close * 1.015,
                "tp": last_close * 0.97,
                "rsi": round(last_rsi, 1)
            }
        return signal
    except Exception as e:
        logging.error(f"Error analyzing {symbol}: {e}")
        return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👑 **ربات تریدر کینگ فعال شد!**\n\n"
        "دستورات:\n"
        "/scan - اسکن لحظه‌ای بیت‌کوین\n"
        "/status - وضعیت ربات"
    )

@dp.message(Command("scan"))
async def cmd_scan(message: types.Message):
    await message.answer("🔍 در حال اسکن بازار KCEX...")
    sig = await analyze_market("BTC/USDT:USDT", "15m")
    if sig:
        text = (
            f"⚡️ **سیگنال جدید**\n"
            f"جهت: {sig['type']}\n"
            f"ارز: `{sig['symbol']}`\n"
            f"قیمت ورود (Entry Price): `{sig['price']}`\n"
            f"حد ضرر (SL): `{sig['sl']:.2f}`\n"
            f"تارگت (TP): `{sig['tp']:.2f}`\n"
            f"شاخص RSI: `{sig['rsi']}`"
        )
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer("⚪️ در تایم‌فریم فعلی سیگنال با وین‌ریت بالا پیدا نشد.")

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    await message.answer("✅ ربات آنلاین است و به صرافی KCEX متصل می‌باشد.")

async def scanner_loop():
    while True:
        try:
            sig = await analyze_market("BTC/USDT:USDT", "15m")
            if sig and ADMIN_ID:
                text = (
                    f"🚨 **سیگنال خودکار اسکنر**\n"
                    f"جهت: {sig['type']}\n"
                    f"ارز: `{sig['symbol']}`\n"
                    f"قیمت ورود: `{sig['price']}`\n"
                    f"حد ضرر: `{sig['sl']:.2f}`\n"
                    f"تارگت: `{sig['tp']:.2f}`"
                )
                await bot.send_message(chat_id=ADMIN_ID, text=text)
        except Exception as e:
            logging.error(f"Scanner loop error: {e}")
        await asyncio.sleep(300) # هر ۵ دقیقه اسکن می‌کند

async def main():
    asyncio.create_task(scanner_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
