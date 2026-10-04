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
    raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

bot = Bot(token=GAPGPTMASKTOKEN7qxtl1e7rcoX0X
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
    if len(df) < 5:
        return "📐 فیبوناچی: داده کافی نیست"

    high_pos = int(df["high"].to_numpy().argmax())
    low_pos = int(df["low"].to_numpy().argmin())

    high_price = float(df["high"].iloc[high_pos])
    low_price = float(df["low"].iloc[low_pos])
    diff = high_price - low_price

    if diff <= 0:
        return "📐 فیبوناچی: قابل محاسبه نیست"

    if low_pos < high_pos:
        direction = "صعودی"
        f236 = high_price - diff * 0.236
        f382 = high_price - diff * 0.382
        f500 = high_price - diff * 0.500
        f618 = high_price - diff * 0.618
        f786 = high_price - diff * 0.786
    else:
        direction = "نزولی"
        f236 = low_price + diff * 0.236
        f382 = low_price + diff * 0.382
        f500 = low_price + diff * 0.500
        f618 = low_price + diff * 0.618
        f786 = low_price + diff * 0.786

    return (
        f"📐 فیبوناچی ({direction})\n"
        f"0.236: {f236:,.2f} | 0.382: {f382:,.2f}\n"
        f"0.500: {f500:,.2f} | 0.618: {f618:,.2f}\n"
        f"0.786: {f786:,.2f}"
    )


def calculate_macd(df):
    close = df["close"].astype(float)
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line

    m_val = float(macd_line.iloc[-1])
    s_val = float(signal_line.iloc[-1])

    if m_val > s_val:
        status = "🟢 صعودی"
    elif m_val < s_val:
        status = "🔴 نزولی"
    else:
        status = "⚪️ خنثی"

    return f"📉 MACD: {m_val:.2f} | Signal: {s_val:.2f} ({status})"


def find_order_block(df, bullish):
    start = max(0, len(df) - 25)
    for i in range(len(df) - 2, start - 1, -1):
        o = float(df["open"].iloc[i])
        c = float(df["close"].iloc[i])
        l = float(df["low"].iloc[i])
        h = float(df["high"].iloc[i])
        if bullish and c < o:
            return f"{l:,.2f} - {h:,.2f}"
        if not bullish and c > o:
            return f"{l:,.2f} - {h:,.2f}"
    return "نامشخص"


def find_fvg(df):
    for i in range(len(df) - 1, 1, -1):
        c2_h = float(df["high"].iloc[i - 2])
        c2_l = float(df["low"].iloc[i - 2])
        c_h = float(df["high"].iloc[i])
        c_l = float(df["low"].iloc[i])

        if c_l > c2_h:
            return f"🟢 صعودی ({c2_h:,.2f} تا {c_l:,.2f})"
        if c_h < c2_l:
            return f"🔴 نزولی ({c_h:,.2f} تا {c2_l:,.2f})"
    return "ندارد"


def calculate_smart_money(df):
    if len(df) < 20:
        return "🧠 SMC: داده کافی نیست"

    c_close = float(df["close"].iloc[-1])
    s_highs = []
    s_lows = []

    for i in range(3, len(df) - 3):
        h = float(df["high"].iloc[i])
        l = float(df["low"].iloc[i])
        if h >= df["high"].iloc[i-3:i].max() and h >= df["high"].iloc[i+1:i+4].max():
            s_highs.append(h)
        if l <= df["low"].iloc[i-3:i].min() and l <= df["low"].iloc[i+1:i+4].min():
            s_lows.append(l)

    structure = "⚪️ رنج"
    bullish_structure = False
    bearish_structure = False

    if s_highs and c_close > s_highs[-1]:
        structure = "🟢 شکست سقف (Bullish BOS)"
        bullish_structure = True
    elif s_lows and c_close < s_lows[-1]:
        structure = "🔴 شکست کف (Bearish BOS)"
        bearish_structure = True

    p_high = float(df["high"].iloc[-21:-1].max())
    p_low = float(df["low"].iloc[-21:-1].min())
    l_high = float(df["high"].iloc[-1])
    l_low = float(df["low"].iloc[-1])

    if l_high > p_high and c_close < p_high:
        liq = "🔴 شکار نقدینگی بالای سقف"
    elif l_low < p_low and c_close > p_low:
        liq = "🟢 شکار نقدینگی کف"
    else:
        liq = "⚪️ نقدینگی شکار نشده"

    ob = find_order_block(df, bullish=bullish_structure or not bearish_structure)
    fvg = find_fvg(df)

    return (
        f"🧠 Smart Money (SMC)\n"
        f"• ساختار: {structure}\n"
        f"• نقدینگی: {liq}\n"
        f"• اوردربلاک (OB): {ob}\n"
        f"• گپ ارزش (FVG): {fvg}"
    )


def calculate_amd(df):
    if len(df) < 25:
        return "🔄 AMD: داده کافی نیست"

    c_close = float(df["close"].iloc[-1])
    c_vol = float(df["volume"].iloc[-1])
    p_high = float(df["high"].iloc[-21:-1].max())
    p_low = float(df["low"].iloc[-21:-1].min())
    avg_vol = float(df["volume"].iloc[-20:-1].mean())

    if float(df["high"].iloc[-1]) > p_high and c_close < p_high:
        phase = "🔴 Manipulation (دستکاری نزولی)"
    elif float(df["low"].iloc[-1]) < p_low and c_close > p_low:
        phase = "🟢 Manipulation (دستکاری صعودی)"
    elif c_close > p_high and c_vol > avg_vol * 1.2:
        phase = "🟢 Distribution (پخش صعودی)"
    elif c_close < p_low and c_vol > avg_vol * 1.2:
        phase = "🔴 Distribution (پخش نزولی)"
    else:
        phase = "⚪️ Accumulation (تجمع و آماده‌سازی)"

    return f"🔄 چرخه ICT/AMD: {phase}"


async def get_signals(symbol="BTC/USDT:USDT", timeframe="15m"):
    try:
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if not ohlcv:
            return "داده‌ای از صرافی دریافت نشد."

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna().reset_index(drop=True)

        if len(df) < 30:
            return "داده کافی برای تحلیل دریافت نشد."

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        df["rsi"] = 100 - (100 / (1 + rs))

        last_rsi = df["rsi"].iloc[-1]
        rsi_text = f"{float(last_rsi):.2f}" if not pd.isna(last_rsi) else "نامشخص"

        # POC
        p_min = float(df["close"].min())
        p_max = float(df["close"].max())
        if p_min == p_max:
            poc_price = p_min
        else:
            df["bin"] = pd.cut(df["close"], bins=20, duplicates="drop")
            prof = df.groupby("bin", observed=False)["volume"].sum().dropna()
            poc_bin = prof.idxmax()
            poc_price = (poc_bin.left + poc_bin.right) / 2

        current_price = float(df["close"].iloc[-1])

        macd_res = calculate_macd(df)
        fib_res = calculate_fibonacci(df)
        smc_res = calculate_smart_money(df)
        amd_res = calculate_amd(df)

        return (
            f"📊 تحلیل جامع بیت‌کوین\n"
            f"⏱ تایم‌فریم: {timeframe}\n"
            f"─────────────────\n"
            f"💰 قیمت فعلی: {current_price:,.2f}$\n"
            f"🎯 مرکز حجم (POC): {poc_price:,.2f}$\n"
            f"📈 RSI: {rsi_text}\n"
            f"─────────────────\n"
            f"{macd_res}\n"
            f"─────────────────\n"
            f"{fib_res}\n"
            f"─────────────────\n"
            f"{smc_res}\n"
            f"─────────────────\n"
            f"{amd_res}\n"
            f"─────────────────\n"
            f"⚠️ تحلیل‌ها جنبه الگوریتمی دارند و توصیه مالی نیستند."
        )

    except Exception as error:
        logging.exception("Analysis error")
        return f"خطا در تحلیل: {str(error)}"


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام! به ربات King Trader خوش آمدید 👑\n\nتایم‌فریم را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard()
    )


@dp.message(Command("analyze"))
async def cmd_analyze(message: types.Message):
    await message.answer(
        "تایم‌فریم مورد نظر را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard()
    )


@dp.callback_query(F.data.startswith("tf_"))
async def handle_timeframe(callback: types.CallbackQuery):
    timeframe = callback.data.replace("tf_", "")
    await callback.answer("در حال تحلیل...")
    await callback.message.edit_text("⏳ در حال دریافت دیتا و محاسبات...")
    result = await get_signals(timeframe=timeframe)
    await callback.message.edit_text(result, reply_markup=get_timeframe_keyboard())


async def health_check(request):
    return web.Response(text="Bot is running!")


async def main():
    port = int(os.getenv("PORT", "8080"))
    app = web.Application()
    app.router.add_get("/", health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logging.info(f"Health check running on port {port}")

    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await exchange.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
