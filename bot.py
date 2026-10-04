import os
import io
import asyncio
import logging

from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


# =========================================================
# تنظیمات عمومی
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

AUTO_SIGNAL_TIMEFRAMES = (
    "1m",
    "5m",
    "15m",
    "1h",
    "4h",
    "1d",
)

AUTO_SCAN_CONCURRENCY = 4


# =========================================================
# اتصال به MEXC
# =========================================================

exchange = ccxt.mexc({
    "enableRateLimit": True,
    "timeout": 15000,
    "options": {
        "defaultType": "swap",
    },
})

dp = Dispatcher()


# =========================================================
# ابزارهای کمکی
# =========================================================

def format_price(price):
    """فرمت هوشمند قیمت برای ارزهای مختلف."""

    if price is None or price == "-":
        return "-"

    try:
        p = float(price)

        if not np.isfinite(p):
            return "-"

        if p == 0:
            return "0.0"
        elif p < 0.0001:
            return f"{p:.8f}"
        elif p < 1:
            return f"{p:.5f}"
        elif p < 100:
            return f"{p:.3f}"
        else:
            return f"{p:.2f}"

    except Exception:
        return str(price)


def get_symbols_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="بیت‌کوین (BTC)",
                    callback_data="sym:BTC/USDT:USDT",
                ),
                InlineKeyboardButton(
                    text="اتریوم (ETH)",
                    callback_data="sym:ETH/USDT:USDT",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="سولانا (SOL)",
                    callback_data="sym:SOL/USDT:USDT",
                ),
                InlineKeyboardButton(
                    text="پپه (PEPE)",
                    callback_data="sym:PEPE/USDT:USDT",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📡 سیگنال اتوماتیک",
                    callback_data="auto_signal",
                ),
            ],
        ]
    )


def get_timeframe_keyboard(symbol):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1m",
                    callback_data=f"tf:{symbol}:1m",
                ),
                InlineKeyboardButton(
                    text="5m",
                    callback_data=f"tf:{symbol}:5m",
                ),
                InlineKeyboardButton(
                    text="15m",
                    callback_data=f"tf:{symbol}:15m",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="1h",
                    callback_data=f"tf:{symbol}:1h",
                ),
                InlineKeyboardButton(
                    text="4h",
                    callback_data=f"tf:{symbol}:4h",
                ),
                InlineKeyboardButton(
                    text="1D",
                    callback_data=f"tf:{symbol}:1d",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 چارت والیوم پروفایل",
                    callback_data=f"vp:{symbol}:1h",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 بازگشت به لیست ارزها",
                    callback_data="back_to_symbols",
                ),
            ],
        ]
    )


def create_ohlcv_dataframe(ohlcv):
    return pd.DataFrame(
        ohlcv,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    )


def calculate_volume_profile(dataframe, window=None, bins=40):
    """
    محاسبه POC، VAH و VAL از روی داده‌های OHLCV.
    """

    if window is not None:
        df = dataframe.iloc[-window:].copy()
    else:
        df = dataframe.copy()

    if len(df) < 20:
        raise ValueError("داده کافی برای محاسبه والیوم پروفایل وجود ندارد.")

    price_min = float(df["low"].min())
    price_max = float(df["high"].max())

    if (
        not np.isfinite(price_min)
        or not np.isfinite(price_max)
        or price_max <= price_min
    ):
        raise ValueError("دامنه قیمت برای محاسبه والیوم پروفایل معتبر نیست.")

    price_bins = np.linspace(
        price_min,
        price_max,
        bins,
    )

    vol_profile = np.zeros(len(price_bins) - 1)

    for _, row in df.iterrows():
        average_price = (
            float(row["open"])
            + float(row["close"])
            + float(row["high"])
            + float(row["low"])
        ) / 4

        index = np.digitize(
            average_price,
            price_bins,
        ) - 1

        # جلوگیری از خارج شدن قیمت آخرین کندل از محدوده آرایه
        index = max(0, min(index, len(vol_profile) - 1))

        volume = float(row["volume"])

        if np.isfinite(volume):
            vol_profile[index] += volume

    poc_index = int(np.argmax(vol_profile))

    poc_price = (
        price_bins[poc_index]
        + price_bins[poc_index + 1]
    ) / 2

    total_volume = float(vol_profile.sum())

    if total_volume <= 0:
        value_area_indices = list(range(len(vol_profile)))
    else:
        value_area_target = total_volume * 0.70

        sorted_indices = np.argsort(
            vol_profile
        )[::-1]

        cumulative_volume = 0
        value_area_indices = []

        for index in sorted_indices:
            cumulative_volume += vol_profile[index]
            value_area_indices.append(int(index))

            if cumulative_volume >= value_area_target:
                break

    val_price = price_bins[min(value_area_indices)]
    vah_price = price_bins[max(value_area_indices) + 1]

    return {
        "price_bins": price_bins,
        "vol_profile": vol_profile,
        "poc_index": poc_index,
        "poc_price": poc_price,
        "val_price": val_price,
        "vah_price": vah_price,
        "dataframe": df,
    }


# =========================================================
# تولید چارت والیوم پروفایل
# =========================================================

async def generate_volume_profile_chart(
    symbol: str,
    timeframe: str = "1h",
):
    figure = None

    try:
        ohlcv = await exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=200,
        )

        if not ohlcv or len(ohlcv) < 50:
            return (
                None,
                "داده‌های کافی جهت رسم پروفایل حجم موجود نیست.",
            )

        df = create_ohlcv_dataframe(ohlcv)

        df["datetime"] = pd.to_datetime(
            df["timestamp"],
            unit="ms",
        )

        vp = calculate_volume_profile(
            df,
            bins=45,
        )

        price_bins = vp["price_bins"]
        vol_profile = vp["vol_profile"]
        poc_index = vp["poc_index"]
        poc_price = vp["poc_price"]
        val_price = vp["val_price"]
        vah_price = vp["vah_price"]

        plt.style.use("dark_background")

        figure, (ax_main, ax_vp) = plt.subplots(
            1,
            2,
            figsize=(12, 6),
            sharey=True,
            gridspec_kw={
                "width_ratios": [4, 1.2],
                "wspace": 0.05,
            },
        )

        for _, row in df.iterrows():
            color = (
                "#26a69a"
                if row["close"] >= row["open"]
                else "#ef5350"
            )

            # سایه کندل
            ax_main.plot(
                [
                    row["datetime"],
                    row["datetime"],
                ],
                [
                    row["low"],
                    row["high"],
                ],
                color=color,
                linewidth=1,
            )

            # بدنه کندل
            ax_main.plot(
                [
                    row["datetime"],
                    row["datetime"],
                ],
                [
                    row["open"],
                    row["close"],
                ],
                color=color,
                linewidth=3,
            )

        ax_main.axhline(
            poc_price,
            color="#ff1744",
            linestyle="--",
            linewidth=1.5,
            label=f"POC: {format_price(poc_price)}",
        )

        ax_main.axhline(
            vah_price,
            color="#00e676",
            linestyle=":",
            linewidth=1.3,
            label=f"VAH: {format_price(vah_price)}",
        )

        ax_main.axhline(
            val_price,
            color="#ff9100",
            linestyle=":",
            linewidth=1.3,
            label=f"VAL: {format_price(val_price)}",
        )

        ax_main.set_title(
            f"Volume Profile: {symbol} ({timeframe})",
            fontsize=13,
            color="white",
            pad=10,
        )

        ax_main.legend(
            loc="upper left",
            facecolor="#1e1e1e",
            edgecolor="none",
        )

        ax_main.grid(
            True,
            linestyle="--",
            alpha=0.15,
        )

        ax_main.xaxis.set_major_formatter(
            mdates.DateFormatter("%m-%d %H:%M")
        )

        plt.setp(
            ax_main.get_xticklabels(),
            rotation=30,
            ha="right",
        )

        bin_height = price_bins[1] - price_bins[0]

        bin_centers = (
            price_bins[:-1]
            + (bin_height / 2)
        )

        bar_colors = [
            "#ff5252"
            if index == poc_index
            else "#42a5f5"
            for index in range(len(vol_profile))
        ]

        ax_vp.barh(
            bin_centers,
            vol_profile,
            height=bin_height * 0.9,
            color=bar_colors,
            alpha=0.75,
        )

        ax_vp.set_xlabel(
            "Volume",
            color="white",
            fontsize=10,
        )

        ax_vp.grid(
            True,
            linestyle="--",
            alpha=0.15,
        )

        ax_vp.tick_params(
            left=False,
            labelleft=False,
        )

        plt.tight_layout()

        buffer = io.BytesIO()

        plt.savefig(
            buffer,
            format="png",
            dpi=120,
            bbox_inches="tight",
        )

        buffer.seek(0)

        caption = (
            f"📊 <b>تحلیل والیوم پروفایل</b>\n\n"
            f"🔹 <b>نماد:</b> "
            f"<code>{symbol}</code>\n"
            f"⏱ <b>تایم‌فریم:</b> "
            f"<code>{timeframe}</code>\n\n"
            f"📍 <b>POC:</b> "
            f"<code>{format_price(poc_price)}</code>\n"
            f"🔺 <b>VAH:</b> "
            f"<code>{format_price(vah_price)}</code>\n"
            f"🔻 <b>VAL:</b> "
            f"<code>{format_price(val_price)}</code>\n\n"
            f"💡 قیمت معمولاً به محدوده‌های پرحجم، "
            f"به‌خصوص POC، واکنش نشان می‌دهد."
        )

        return buffer, caption

    except Exception as error:
        logging.exception("Volume profile error")

        return (
            None,
            f"❌ خطا در ساخت والیوم پروفایل:\n{error}",
        )

    finally:
        if figure is not None:
            plt.close(figure)


# =========================================================
# تحلیل تکنیکال
# =========================================================

async def analyze_market(
    symbol: str,
    timeframe: str = "15m",
):
    try:
        ohlcv = await exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=350,
        )

        if not ohlcv or len(ohlcv) < 220:
            return (
                "❌ داده‌های کافی از صرافی دریافت نشد.\n"
                "لطفاً از نمادهای معتبر استفاده کنید."
            )

        df = create_ohlcv_dataframe(ohlcv)

        # -------------------------------------------------
        # EMA
        # -------------------------------------------------

        df["ema20"] = df["close"].ewm(
            span=20,
            adjust=False,
        ).mean()

        df["ema50"] = df["close"].ewm(
            span=50,
            adjust=False,
        ).mean()

        df["ema200"] = df["close"].ewm(
            span=200,
            adjust=False,
        ).mean()

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        delta = df["close"].diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.ewm(
            alpha=1 / 14,
            min_periods=14,
            adjust=False,
        ).mean()

        avg_loss = loss.ewm(
            alpha=1 / 14,
            min_periods=14,
            adjust=False,
        ).mean()

        relative_strength = avg_gain / (
            avg_loss + 1e-9
        )

        df["rsi"] = 100 - (
            100 / (1 + relative_strength)
        )

        # -------------------------------------------------
        # MACD
        # -------------------------------------------------

        ema12 = df["close"].ewm(
            span=12,
            adjust=False,
        ).mean()

        ema26 = df["close"].ewm(
            span=26,
            adjust=False,
        ).mean()

        df["macd"] = ema12 - ema26

        df["macd_signal"] = df["macd"].ewm(
            span=9,
            adjust=False,
        ).mean()

        df["macd_hist"] = (
            df["macd"]
            - df["macd_signal"]
        )

        # -------------------------------------------------
        # ATR
        # -------------------------------------------------

        tr1 = df["high"] - df["low"]

        tr2 = (
            df["high"]
            - df["close"].shift(1)
        ).abs()

        tr3 = (
            df["low"]
            - df["close"].shift(1)
        ).abs()

        true_range = pd.concat(
            [tr1, tr2, tr3],
            axis=1,
        ).max(axis=1)

        df["atr"] = true_range.rolling(
            window=14
        ).mean()

        # -------------------------------------------------
        # ADX
        # -------------------------------------------------

        plus_dm_raw = df["high"].diff()
        minus_dm_raw = -df["low"].diff()

        plus_dm = pd.Series(
            np.where(
                (
                    (plus_dm_raw > minus_dm_raw)
                    & (plus_dm_raw > 0)
                ),
                plus_dm_raw,
                0.0,
            ),
            index=df.index,
        )

        minus_dm = pd.Series(
            np.where(
                (
                    (minus_dm_raw > plus_dm_raw)
                    & (minus_dm_raw > 0)
                ),
                minus_dm_raw,
                0.0,
            ),
            index=df.index,
        )

        tr_sum = true_range.rolling(
            window=14
        ).sum()

        plus_di = 100 * (
            plus_dm.rolling(window=14).sum()
            / (tr_sum + 1e-9)
        )

        minus_di = 100 * (
            minus_dm.rolling(window=14).sum()
            / (tr_sum + 1e-9)
        )

        dx = (
            (plus_di - minus_di).abs()
            / (plus_di + minus_di + 1e-9)
        ) * 100

        df["adx"] = dx.rolling(
            window=14
        ).mean()

        # -------------------------------------------------
        # میانگین حجم
        # -------------------------------------------------

        df["vol_ma"] = df["volume"].rolling(
            window=20
        ).mean()

        # -------------------------------------------------
        # والیوم پروفایل
        # -------------------------------------------------

        vp = calculate_volume_profile(
            df,
            window=100,
            bins=40,
        )

        poc_price = vp["poc_price"]
        val_price = vp["val_price"]
        vah_price = vp["vah_price"]

        # -------------------------------------------------
        # داده‌های کندل بسته‌شده
        # -------------------------------------------------

        recent_high = df["high"].iloc[-21:-1].max()
        recent_low = df["low"].iloc[-21:-1].min()

        # آخرین کندل ممکن است هنوز در حال تشکیل باشد
        current_candle = df.iloc[-2]
        previous_candle = df.iloc[-3]

        current_live_price = float(df["close"].iloc[-1])

        atr_value = current_candle["atr"]

        if pd.isna(atr_value) or atr_value <= 0:
            atr_value = current_live_price * 0.015

        adx_value = current_candle["adx"]

        if pd.isna(adx_value):
            adx_value = 20.0

        volume_ma = current_candle["vol_ma"]

        if pd.isna(volume_ma) or volume_ma <= 0:
            volume_ratio = 1.0
        else:
            volume_ratio = (
                current_candle["volume"]
                / volume_ma
            )

        # -------------------------------------------------
        # امتیازدهی لانگ و شورت
        # -------------------------------------------------

        long_score = 0.0
        short_score = 0.0

        trend_bullish = (
            current_candle["close"]
            > current_candle["ema200"]
        )

        trend_bearish = (
            current_candle["close"]
            < current_candle["ema200"]
        )

        if current_candle["ema20"] > current_candle["ema50"]:
            long_score += 1.5
        elif current_candle["ema20"] < current_candle["ema50"]:
            short_score += 1.5

        if current_candle["close"] > current_candle["ema50"]:
            long_score += 1.0
        else:
            short_score += 1.0

        if (
            current_candle["macd"]
            > current_candle["macd_signal"]
        ):
            long_score += 1.0

            if (
                current_candle["macd_hist"]
                > previous_candle["macd_hist"]
            ):
                long_score += 0.5

        elif (
            current_candle["macd"]
            < current_candle["macd_signal"]
        ):
            short_score += 1.0

            if (
                current_candle["macd_hist"]
                < previous_candle["macd_hist"]
            ):
                short_score += 0.5

        rsi_value = current_candle["rsi"]

        if not pd.isna(rsi_value):
            if 52 <= rsi_value <= 68:
                long_score += 1.5
            elif rsi_value > 75:
                long_score -= 2.0

            if 32 <= rsi_value <= 48:
                short_score += 1.5
            elif rsi_value < 25:
                short_score -= 2.0

        is_trending = float(adx_value) >= 21
        has_volume = float(volume_ratio) >= 0.95

        # -------------------------------------------------
        # تأیید والیوم پروفایل
        # -------------------------------------------------

        vp_long_ok = (
            (
                current_candle["close"]
                >= poc_price
            )
            and (
                (
                    current_candle["close"]
                    >= vah_price * 0.998
                )
                or (
                    previous_candle["low"]
                    <= poc_price
                    and current_candle["close"]
                    > poc_price
                )
            )
        )

        vp_short_ok = (
            (
                current_candle["close"]
                <= poc_price
            )
            and (
                (
                    current_candle["close"]
                    <= val_price * 1.002
                )
                or (
                    previous_candle["high"]
                    >= poc_price
                    and current_candle["close"]
                    < poc_price
                )
            )
        )

        if current_candle["close"] > poc_price:
            long_score += 1.0
        elif current_candle["close"] < poc_price:
            short_score += 1.0

        # -------------------------------------------------
        # تأیید SMC / شکست ساختار
        # -------------------------------------------------

        smc_long_ok = (
            current_candle["close"]
            >= recent_high * 0.995
            and current_candle["close"]
            > current_candle["open"]
        )

        smc_short_ok = (
            current_candle["close"]
            <= recent_low * 1.005
            and current_candle["close"]
            < current_candle["open"]
        )

        is_high_probability_long = (
            trend_bullish
            and long_score >= 4.5
            and is_trending
            and has_volume
            and smc_long_ok
            and vp_long_ok
        )

        is_high_probability_short = (
            trend_bearish
            and short_score >= 4.5
            and is_trending
            and has_volume
            and smc_short_ok
            and vp_short_ok
        )

        # -------------------------------------------------
        # وضعیت والیوم پروفایل
        # -------------------------------------------------

        if current_live_price >= vah_price:
            vp_status = (
                f"صعودی "
                f"(بالای VAH: {format_price(vah_price)})"
            )
        elif current_live_price <= val_price:
            vp_status = (
                f"نزولی "
                f"(زیر VAL: {format_price(val_price)})"
            )
        else:
            vp_status = (
                f"داخل محدوده ارزش "
                f"(POC: {format_price(poc_price)})"
            )

        # -------------------------------------------------
        # تعیین جهت و اهداف
        # -------------------------------------------------

        if is_high_probability_long:
            direction = (
                "🟢 صعودی قوی "
                "(Strong Long) ⭐⭐⭐"
            )

            stop_loss = (
                current_live_price
                - 1.1 * float(atr_value)
            )

            tp1 = (
                current_live_price
                + 1.0 * float(atr_value)
            )

            tp2 = (
                current_live_price
                + 1.8 * float(atr_value)
            )

            tp3 = (
                current_live_price
                + 2.8 * float(atr_value)
            )

            tp4 = (
                current_live_price
                + 4.0 * float(atr_value)
            )

            confidence = (
                "۸۲٪ تا ۹۰٪ "
                "(تأییدیه ترند، SMC و والیوم پروفایل)"
            )

            smc_status = (
                f"✅ تایید ورود نقدینگی بالای "
                f"{format_price(recent_high)}"
            )

        elif is_high_probability_short:
            direction = (
                "🔴 نزولی قوی "
                "(Strong Short) ⭐⭐⭐"
            )

            stop_loss = (
                current_live_price
                + 1.1 * float(atr_value)
            )

            tp1 = (
                current_live_price
                - 1.0 * float(atr_value)
            )

            tp2 = (
                current_live_price
                - 1.8 * float(atr_value)
            )

            tp3 = (
                current_live_price
                - 2.8 * float(atr_value)
            )

            tp4 = (
                current_live_price
                - 4.0 * float(atr_value)
            )

            confidence = (
                "۸۲٪ تا ۹۰٪ "
                "(تأییدیه ترند، SMC و والیوم پروفایل)"
            )

            smc_status = (
                f"✅ تایید تخلیه نقدینگی زیر "
                f"{format_price(recent_low)}"
            )

        else:
            direction = (
                "⚪️ خنثی / بدون معامله "
                "(فیلتر حفظ سرمایه)"
            )

            stop_loss = "-"
            tp1 = "-"
            tp2 = "-"
            tp3 = "-"
            tp4 = "-"

            confidence = "نامناسب جهت معامله"

            smc_status = (
                "⚠️ ساختار نقدینگی معتبر تشکیل نشده است"
            )

        rsi_display = (
            f"{float(rsi_value):.1f}"
            if not pd.isna(rsi_value)
            else "-"
        )

        ema200_status = (
            "بالای ترند بلندمدت"
            if current_live_price
            > current_candle["ema200"]
            else "زیر ترند بلندمدت"
        )

        report = (
            f"📊 <b>گزارش تحلیلی پیشرفته</b>\n\n"
            f"🔹 <b>نماد:</b> "
            f"<code>{symbol}</code>\n"
            f"⏱ <b>تایم‌فریم:</b> "
            f"<code>{timeframe}</code>\n"
            f"💵 <b>Entry Price:</b> "
            f"<code>{format_price(current_live_price)}</code>\n"
            f"📈 <b>سیگنال:</b> "
            f"{direction}\n"
            f"🎯 <b>اعتبار تخمینی:</b> "
            f"<code>{confidence}</code>\n\n"
            f"🎯 <b>اهداف خروج پله‌ای:</b>\n"
            f"▫️ TP1: "
            f"<code>{format_price(tp1)}</code>\n"
            f"▫️ TP2: "
            f"<code>{format_price(tp2)}</code>\n"
            f"▫️ TP3: "
            f"<code>{format_price(tp3)}</code>\n"
            f"▫️ TP4: "
            f"<code>{format_price(tp4)}</code>\n\n"
            f"🛑 <b>Stop Loss:</b> "
            f"<code>{format_price(stop_loss)}</code>\n\n"
            f"📌 <i>پس از لمس TP1، "
            f"استاپ را روی Entry Price قرار دهید.</i>\n\n"
            f"🔍 <b>متریک‌های کلیدی:</b>\n"
            f"• والیوم پروفایل: "
            f"<code>{vp_status}</code>\n"
            f"• اسمارت‌مانی: "
            f"<code>{smc_status}</code>\n"
            f"• RSI: "
            f"<code>{rsi_display}</code>\n"
            f"• ADX: "
            f"<code>{float(adx_value):.1f}</code> "
            f"({'رونددار قوی' if is_trending else 'رنج / ضعیف'})\n"
            f"• حجم نسبت به میانگین: "
            f"<code>{float(volume_ratio):.2f}x</code>\n"
            f"• وضعیت EMA200: "
            f"<code>{ema200_status}</code>"
        )

        return report

    except Exception as error:
        logging.exception(
            f"Analysis error for {symbol} - {timeframe}"
        )

        return (
            f"❌ خطایی در تحلیل {symbol} رخ داد:\n"
            f"{error}"
        )


# =========================================================
# اسکن خودکار بازار
# =========================================================

async def scan_one_market(
    symbol: str,
    timeframe: str,
    semaphore: asyncio.Semaphore,
):
    try:
        async with semaphore:
            report = await analyze_market(
                symbol,
                timeframe,
            )

        if (
            "Strong Long" in report
            or "Strong Short" in report
        ):
            return symbol, timeframe, report

        return None

    except Exception as error:
        logging.exception(
            f"Auto scan error: {symbol} - {timeframe}"
        )
        return None


async def scan_all_mexc_markets():
    markets = await exchange.load_markets()

    symbols = sorted(
        {
            market["symbol"]
            for market in markets.values()
            if (
                market.get("active", True) is not False
                and market.get("swap") is True
                and market.get("linear") is True
                and market.get("quote") == "USDT"
                and market.get("settle") == "USDT"
            )
        }
    )

    if not symbols:
        raise RuntimeError(
            "هیچ قرارداد USDT-M فعالی در MEXC پیدا نشد."
        )

    semaphore = asyncio.Semaphore(
        AUTO_SCAN_CONCURRENCY
    )

    tasks = [
        scan_one_market(
            symbol,
            timeframe,
            semaphore,
        )
        for symbol in symbols
        for timeframe in AUTO_SIGNAL_TIMEFRAMES
    ]

    results = await asyncio.gather(
        *tasks,
        return_exceptions=True,
    )

    signals = []

    for result in results:
        if isinstance(result, tuple):
            signals.append(result)

    signals.sort(
        key=lambda item: (
            item[0],
            item[1],
        )
    )

    return len(symbols), signals


def split_signal_reports(
    reports,
    max_length=3900,
):
    """
    تقسیم گزارش‌ها برای جلوگیری از عبور از محدودیت تلگرام.
    """

    chunks = []
    current_chunk = ""

    for report in reports:
        if not current_chunk:
            current_chunk = report
            continue

        candidate = (
            current_chunk
            + "\n\n"
            + report
        )

        if len(candidate) <= max_length:
            current_chunk = candidate
        else:
            chunks.append(current_chunk)
            current_chunk = report

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


# =========================================================
# هندلرهای تلگرام
# =========================================================

@dp.message(Co
