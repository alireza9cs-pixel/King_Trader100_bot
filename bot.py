import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import ccxt.async_support as ccxt
import pandas as pd

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN در Environment Variables تنظیم نشده است.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

exchange = ccxt.bingx({
    "enableRateLimit": True,
    "options": {
        "defaultType": "swap"
    }
})


def get_timeframe_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(text="⏱ 15 دقیقه", callback_data="tf_15m")
    builder.button(text="⏱ 1 ساعت", callback_data="tf_1h")
    builder.button(text="⏱ 4 ساعت", callback_data="tf_4h")
    builder.button(text="⏱ 1 روز", callback_data="tf_1d")

    builder.adjust(2, 2)
    return builder.as_markup()


def calculate_fibonacci(df):
    recent_high_index = df["high"].idxmax()
    recent_low_index = df["low"].idxmin()

    high_price = float(df.loc[recent_high_index, "high"])
    low_price = float(df.loc[recent_low_index, "low"])

    difference = high_price - low_price

    if difference <= 0:
        return "قابل محاسبه نیست"

    # اگر حرکت از کف به سقف بوده باشد
    if recent_low_index < recent_high_index:
        direction = "صعودی"
        fib_236 = high_price - difference * 0.236
        fib_382 = high_price - difference * 0.382
        fib_500 = high_price - difference * 0.500
        fib_618 = high_price - difference * 0.618
        fib_786 = high_price - difference * 0.786

    # اگر حرکت از سقف به کف بوده باشد
    else:
        direction = "نزولی"
        fib_236 = low_price + difference * 0.236
        fib_382 = low_price + difference * 0.382
        fib_500 = low_price + difference * 0.500
        fib_618 = low_price + difference * 0.618
        fib_786 = low_price + difference * 0.786

    return (
        f"📐 فیبوناچی حرکت {direction}\n"
        f"0.236 : {fib_236:,.2f}\n"
        f"0.382 : {fib_382:,.2f}\n"
        f"0.500 : {fib_500:,.2f}\n"
        f"0.618 : {fib_618:,.2f}\n"
        f"0.786 : {fib_786:,.2f}"
    )


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

        # محاسبه RSI
        delta = df["close"].diff()

        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()

        rs = gain / loss.replace(0, float("nan"))
        df["rsi"] = 100 - (100 / (1 + rs))

        # محاسبه POC
        price_min = float(df["close"].min())
        price_max = float(df["close"].max())

        if price_min == price_max:
            poc_price = price_min
        else:
            df["price_bin"] = pd.cut(
                df["close"],
                bins=20,
                duplicates="drop"
            )

            profile = df.groupby(
                "price_bin",
                observed=False
            )["volume"].sum()

            poc_bin = profile.idxmax()
            poc_price = (poc_bin.left + poc_bin.right) / 2

        # قیمت و RSI
        current_price = float(df["close"].iloc[-1])
        last_rsi = df["rsi"].iloc[-1]

        if pd.isna(last_rsi):
            rsi_text = "نامشخص"
            status = "⚪️ اطلاعات کافی نیست"
        else:
            rsi_text = f"{float(last_rsi):.2f}"

            if last_rsi < 30:
                status = "🟢 اشباع فروش"
            elif last_rsi > 70:
                status = "🔴 اشباع خرید"
            else:
                status = "⚪️ محدوده خنثی"

        fibonacci_text = calculate_fibonacci(df)

        return (
            f"📊 تحلیل بیت‌کوین\n"
            f"⏱ تایم‌فریم: {timeframe}\n"
            f"─────────────────\n"
            f"💰 قیمت فعلی: {current_price:,.2f}$\n"
            f"🎯 مرکز حجم معاملات POC: {poc_price:,.2f}$\n"
            f"📈 RSI: {rsi_text}\n"
            f"🚦 وضعیت: {status}\n"
            f"─────────────────\n"
            f"{fibonacci_text}\n"
            f"─────────────────\n"
            f"⚠️ این اعداد فقط سطوح احتمالی هستند، نه تضمین خرید یا فروش."
        )

    except Exception as e:
        logging.exception("Analysis error")
        return f"خطا در تحلیل: {str(e)}"


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام! به ربات King Trader خوش آمدید 👑\n\n"
        "تایم‌فریم را انتخاب کن:",
        reply_markup=get_timeframe_keyboard()
    )


@dp.message(Command("analyze"))
async def cmd_analyze(message: types.Message):
    await message.answer(
        "تایم‌فریم مورد نظر را انتخاب کن:",
        reply_markup=get_timeframe_keyboard()
    )


@dp.callback_query(F.data.startswith("tf_"))
async def handle_timeframe(callback: types.CallbackQuery):
    timeframe = callback.data.replace("tf_", "")

    await callback.answer("در حال تحلیل بازار...")

    await callback.message.edit_text(
        "⏳ در حال دریافت اطلاعات بازار..."
    )

    result = await get_signals(timeframe=timeframe)

    await callback.message.edit_text(
        result,
        reply_markup=get_timeframe_keyboard()
    )


async def handle(request):
    return web.Response(text="Bot is running!")


async def main():
    port = int(os.getenv("PORT", "8080"))

    app = web.Application()
    app.router.add_get("/", handle)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
