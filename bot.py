import os
import asyncio
import logging
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

import ccxt.async_support as ccxt
import pandas as pd


logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN در Environment Variables تنظیم نشده است")


# سرور ساده برای سالم نگه داشتن Web Service روی Render
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"King Trader bot is running")

    def log_message(self, format, *args):
        return


def run_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logging.info("Health server started on port %s", port)
    server.serve_forever()


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

exchange = ccxt.bingx({
    "enableRateLimit": True,
    "options": {
        "defaultType": "swap"
    }
})


async def get_signals(symbol="BTC/USDT:USDT", timeframe="15m"):
    try:
        ohlcv = await exchange.fetch_ohlcv(
            symbol,
            timeframe,
            limit=100
        )

        if not ohlcv:
            return "داده‌ای از صرافی دریافت نشد."

        df = pd.DataFrame(
            ohlcv,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        )

        delta = df["close"].diff()

        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()

        rs = gain / loss.replace(0, float("nan"))
        df["rsi"] = 100 - (100 / (1 + rs))

        current_price = float(df["close"].iloc[-1])
        last_rsi = df["rsi"].iloc[-1]

        if pd.isna(last_rsi):
            return "هنوز داده کافی برای محاسبه RSI وجود ندارد."

        if last_rsi < 30:
            signal = "🟢 احتمال LONG؛ بازار اشباع فروش است"
        elif last_rsi > 70:
            signal = "🔴 احتمال SHORT؛ بازار اشباع خرید است"
        else:
            signal = "⏳ شرایط ورود قطعی نیست؛ بازار در محدوده میانی است"

        return (
            f"📊 تحلیل {symbol}\n"
            f"⏱ تایم‌فریم: {timeframe}\n"
            f"💰 قیمت فعلی: {current_price:.2f}\n"
            f"📈 RSI: {last_rsi:.2f}\n"
            f"🎯 وضعیت: {signal}"
        )

    except Exception as error:
        logging.exception("Market data error")
        return f"خطا در دریافت داده بازار:\n{error}"


@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer(
        "سلام سیسی! 👑\n"
        "ربات تریدر با موفقیت فعال شد.\n\n"
        "برای تحلیل BTC دستور زیر را بفرست:\n"
        "/analyze"
    )


@dp.message(Command("analyze"))
async def analyze_handler(message: types.Message):
    await message.answer("⏳ در حال دریافت و تحلیل بازار...")

    result = await get_signals(
        symbol="BTC/USDT:USDT",
        timeframe="15m"
    )

    await message.answer(result)


async def main():
    try:
        logging.info("Bot is starting...")
        await dp.start_polling(bot)

    finally:
        await exchange.close()
        await bot.session.close()


if __name__ == "__main__":
    health_thread = Thread(
        target=run_health_server,
        daemon=True
    )
    health_thread.start()

    asyncio.run(main())
