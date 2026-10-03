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
    if len(df) < 5:
        return "📐 فیبوناچی: داده کافی نیست"

    high_position = int(df["high"].to_numpy().argmax())
    low_position = int(df["low"].to_numpy().argmin())

    high_price = float(df["high"].iloc[high_position])
    low_price = float(df["low"].iloc[low_position])

    difference = high_price - low_price

    if difference <= 0:
        return "📐 فیبوناچی: قابل محاسبه نیست"

    if low_position < high_position:
        direction = "صعودی"

        fib_236 = high_price - difference * 0.236
        fib_382 = high_price - difference * 0.382
        fib_500 = high_price - difference * 0.500
        fib_618 = high_price - difference * 0.618
        fib_786 = high_price - difference * 0.786

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


def calculate_macd(df):
    close = df["close"].astype(float)

    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()

    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    macd_value = float(macd_line.iloc[-1])
    signal_value = float(signal_line.iloc[-1])
    histogram_value = float(histogram.iloc[-1])

    if macd_value > signal_value:
        status = "🟢 صعودی"
    elif macd_value < signal_value:
        status = "🔴 نزولی"
    else:
        status = "⚪️ خنثی"

    return (
        f"📉 MACD\n"
        f"خط MACD: {macd_value:.4f}\n"
        f"خط Signal: {signal_value:.4f}\n"
        f"Histogram: {histogram_value:.4f}\n"
        f"وضعیت: {status}"
    )


def find_order_block(df, bullish):
    start_index = max(0, len(df) - 30)

    for i in range(len(df) - 2, start_index - 1, -1):
        open_price = float(df["open"].iloc[i])
        close_price = float(df["close"].iloc[i])
        low_price = float(df["low"].iloc[i])
        high_price = float(df["high"].iloc[i])

        if bullish and close_price < open_price:
            return f"{low_price:,.2f} تا {high_price:,.2f}"

        if not bullish and close_price > open_price:
            return f"{low_price:,.2f} تا {high_price:,.2f}"

    return "پیدا نشد"


def find_fair_value_gap(df):
    for i in range(len(df) - 1, 1, -1):
        candle_two_high = float(df["high"].iloc[i - 2])
        candle_two_low = float(df["low"].iloc[i - 2])

        current_high = float(df["high"].iloc[i])
        current_low = float(df["low"].iloc[i])

        # FVG صعودی
        if current_low > candle_two_high:
            return (
                f"🟢 صعودی: "
                f"{candle_two_high:,.2f} تا {current_low:,.2f}"
            )

        # FVG نزولی
        if current_high < candle_two_low:
            return (
                f"🔴 نزولی: "
                f"{current_high:,.2f} تا {candle_two_low:,.2f}"
            )

    return "پیدا نشد"


def calculate_smart_money(df):
    if len(df) < 20:
        return (
            "🧠 Smart Money / SMC\n"
            "داده کافی برای تشخیص ساختار بازار وجود ندارد."
        )

    current_close = float(df["close"].iloc[-1])

    swing_highs = []
    swing_lows = []

    window = 3

    for i in range(window, len(df) - window):
        current_high = float(df["high"].iloc[i])
        current_low = float(df["low"].iloc[i])

        left_highs = df["high"].iloc[i - window:i]
        right_highs = df["high"].iloc[i + 1:i + window + 1]

        left_lows = df["low"].iloc[i - window:i]
        right_lows = df["low"].iloc[i + 1:i + window + 1]

        if current_high >= left_highs.max() and current_high >= right_highs.max():
            swing_highs.append(i)

        if current_low <= left_lows.min() and current_low <= right_lows.min():
            swing_lows.append(i)

    structure = "⚪️ رنج یا بدون شکست مشخص"
    bullish_structure = False
    bearish_structure = False

    if swing_highs:
        last_swing_high = swing_highs[-1]
        swing_high_price = float(df["high"].iloc[last_swing_high])

        if current_close > swing_high_price:
            structure = "🟢 شکست ساختار صعودی - Bullish BOS"
            bullish_structure = True

    if swing_lows:
        last_swing_low = swing_lows[-1]
        swing_low_price = float(df["low"].iloc[last_swing_low])

        if current_close < swing_low_price:
            structure = "🔴 شکست ساختار نزولی - Bearish BOS"
            bearish_structure = True

    lookback = min(20, len(df) - 1)

    previous_high = float(
        df["high"].iloc[-lookback - 1:-1].max()
    )

    previous_low = float(
        df["low"].iloc[-lookback - 1:-1].min()
    )

    last_high = float(df["high"].iloc[-1])
    last_low = float(df["low"].iloc[-1])

    if last_high > previous_high and current_close < previous_high:
        liquidity = "🔴 جمع‌آوری نقدینگی بالای سقف"
    elif last_low < previous_low and current_close > previous_low:
        liquidity = "🟢 جمع‌آوری نقدینگی پایین کف"
    else:
        liquidity = "⚪️ نقدینگی مشخصی شکار نشده است"

    if bullish_structure:
        order_block_zone = find_order_block(df, bullish=True)
    elif bearish_structure:
        order_block_zone = find_order_block(df, bullish=False)
    else:
        order_block_zone = "با ساختار فعلی مشخص نیست"

    fvg = find_fair_value_gap(df)

    return (
        f"🧠 Smart Money / SMC\n"
        f"🏗 ساختار بازار: {structure}\n"
        f"💧 نقدینگی: {liquidity}\n"
        f"🧱 Order Block: {order_block_zone}\n"
        f"🕳 FVG: {fvg}"
    )


def calculate_amd(df):
    if len(df) < 30:
        return (
            "🔄 AMD\n"
            "داده کافی برای تشخیص Accumulation، Manipulation و Distribution نیست."
        )

    current_close = float(df["close"].iloc[-1])
    current_volume = float(df["volume"].iloc[-1])

    previous_high = float(df["high"].iloc[-21:-1].max())
    previous_low = float(df["low"].iloc[-21:-1].min())

    average_volume = float(df["volume"].iloc[-20:-1].mean())

    recent_range = (
        float(df["high"].iloc[-10:].max())
        - float(df["low"].iloc[-10:].min())
    )

    previous_range = (
        float(df["high"].iloc[-20:-10].max())
        - float(df["low"].iloc[-20:-10].min())
    )

    # مرحله Manipulation؛ شکار نقدینگی و برگشت به داخل محدوده
    if (
        float(df["high"].iloc[-1]) > previous_high
        and current_close < previous_high
    ):
        return (
            "🔄 AMD\n"
            "مرحله احتمالی: 🔴 Manipulation نزولی\n"
            "قیمت بالای محدوده را لمس کرده و دوباره پایین‌تر بسته شده است."
        )

    if (
        float(df["low"].iloc[-1]) < previous_low
        and current_close > previous_low
    ):
        return (
            "🔄 AMD\n"
            "مرحله احتمالی: 🟢 Manipulation صعودی\n"
            "قیمت پایین محدوده را لمس کرده و دوباره بالاتر بسته شده است."
        )

    # مرحله Distribution؛ شکست محدوده همراه با حجم بالاتر
    if (
        current_close > previous_high
        and current_volume > average_volume * 1.2
    ):
        return (
            "🔄 AMD\n"
            "مرحله احتمالی: 🟢 Distribution صعودی\n"
            "شکست سقف محدوده با حجم نسبتاً بالا دیده می‌شود."
        )

    if (
        current_close < previous_low
        and current_volume > average_volume * 1.2
    ):
        return (
            "🔄 AMD\n"
            "مرحله احتمالی: 🔴 Distribution نزولی\n"
            "شکست کف محدوده با حجم نسبتاً بالا دیده می‌شود."
        )

    # مرحله Accumulation؛ فشرده‌شدن محدوده
    if previous_range > 0 and recent_range < previous_range * 0.75:
        return (
            "🔄 AMD\n"
            "مرحله احتمالی: ⚪️ Accumulation\n"
            "نوسان قیمت در حال فشرده‌شدن و بازار در حالت جمع‌آوری است."
        )

    return (
        "🔄 AMD\n"
        "مرحله فعلی: ⚪️ نامشخص یا انتقالی\n"
        "برای تشخیص واضح‌تر، باید حرکت بعدی قیمت تأیید شود."
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

        numeric_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]

        for column in numeric_columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

        df = df.dropna().reset_index(drop=True)

        if len(df) < 30:
            return "داده کافی برای تحلیل دریافت نشد."

        # محاسبه RSI
        delta = df["close"].diff()

        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()

        rs = gain / loss.replace(0, float("nan"))
        df["rsi"] = 100 - (100 / (1 + rs))

        last_rsi = df["rsi"].iloc[-1]

        if pd.isna(last_rsi):
            rsi_text = "نامشخص"
            rsi_status = "⚪️ اطلاعات کافی نیست"
        else:
            rsi_text = f"{float(last_rsi):.2f}"

            if last_rsi < 30:
                rsi_status = "🟢 اشباع فروش"
            elif last_rsi > 70:
                rsi_status = "🔴 اشباع خرید"
            else:
                rsi_status = "⚪️ محدوده خنثی"

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

            profile = (
                df.groupby(
                    "price_bin",
                    observed=False
                )["volume"]
                .sum()
                .dropna()
            )

            if profile.empty:
                poc_price = float(df["close"].iloc[-1])
            else:
                poc_bin = profile.idxmax()
                poc_price = (poc_bin.left + poc_bin.right) / 2

        current
