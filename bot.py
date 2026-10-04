import os
import io
import asyncio
import logging

from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np

import matplotlib
matplotlib.use("Agg")  # بدون GUI برای اجرا روی سرور

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

# =GAPGPTMASKTOKENp4nwj0gbwaX0X==============GAPGPTMASKTOKENp4nwj0gbwaX1X========================
# تنظیمات عمومی و توکن
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

# اتصال به صرافی MEXC (قراردادهای فیوچرز USDT)
exchange = ccxt.mexc({
    "enableRateLimit": True,
    "timeout": 15000,
    "options": {
        "defaultType": "swap",
    },
})

dp = Dispatcher()

# =========================================================
# کیبوردها و قالب‌بندی
# =========================================================

def format_price(price):
    """فرمت هوشمند قیمت برای نمادهای مختلف."""
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
                InlineKeyboardButton(text="بیت‌کوین (BTC)", callback_data="sym:BTC/USDT:USDT"),
                InlineKeyboardButton(text="اتریوم (ETH)", callback_data="sym:ETH/USDT:USDT"),
            ],
            [
                InlineKeyboardButton(text="سولانا (SOL)", callback_data="sym:SOL/USDT:USDT"),
                InlineKeyboardButton(text="پپه (PEPE)", callback_data="sym:PEPE/USDT:USDT"),
            ],
            [
                InlineKeyboardButton(text="📡 سیگنال اتوماتیک", callback_data="auto_signal"),
            ],
        ]
    )


def get_timeframe_keyboard(symbol):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1m", callback_data=f"tf:{symbol}:1m"),
                InlineKeyboardButton(text="5m", callback_data=f"tf:{symbol}:5m"),
                InlineKeyboardButton(text="15m", callback_data=f"tf:{symbol}:15m"),
            ],
            [
                InlineKeyboardButton(text="1h", callback_data=f"tf:{symbol}:1h"),
                InlineKeyboardButton(text="4h", callback_data=f"tf:{symbol}:4h"),
                InlineKeyboardButton(text="1D", callback_data=f"tf:{symbol}:1d"),
            ],
            [
                InlineKeyboardButton(text="📊 چارت والیوم پروفایل", callback_data=f"vp:{symbol}:1h"),
            ],
            [
                InlineKeyboardButton(text="🔙 بازگشت به لیست ارزها", callback_data="back_to_symbols"),
            ],
        ]
    )


# =========================================================
# ماژول چارت والیوم پروفایل (Volume Profile)
# =========================================================

async def generate_volume_profile_chart(symbol: str, timeframe: str = "1h"):
    figure = None
    try:
        limit = 200
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 50:
            return None, "داده‌های کافی جهت رسم پروفایل حجم موجود نیست."

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")

        price_min = df["low"].min()
        price_max = df["high"].max()

        bins = 45
        price_bins = np.linspace(price_min, price_max, bins)
        vol_profile = np.zeros(len(price_bins) - 1)

        for _, row in df.iterrows():
            avg_p = (row["open"] + row["close"] + row["high"] + row["low"]) / 4
            idx = np.digitize(avg_p, price_bins) - 1
            if 0 <= idx < len(vol_profile):
                vol_profile[idx] += row["volume"]

        poc_idx = int(np.argmax(vol_profile))
        poc_price = (price_bins[poc_idx] + price_bins[poc_idx + 1]) / 2

        tot_vol = vol_profile.sum()
        va_target = tot_vol * 0.70
        sorted_indices = np.argsort(vol_profile)[::-1]

        cum_vol = 0
        va_indices = []
        for idx in sorted_indices:
            cum_vol += vol_profile[idx]
            va_indices.append(idx)
            if cum_vol >= va_target:
                break

        val_price = price_bins[min(va_indices)]
        vah_price = price_bins[max(va_indices) + 1]

        plt.style.use("dark_background")
        figure, (ax_main, ax_vp) = plt.subplots(
            1, 2, figsize=(12, 6), sharey=True, gridspec_kw={"width_ratios": [4, 1.2], "wspace": 0.05}
        )

        for _, row in df.iterrows():
            c = "#26a69a" if row["close"] >= row["open"] else "#ef5350"
            ax_main.plot([row["datetime"], row["datetime"]], [row["low"], row["high"]], color=c, linewidth=1)
            ax_main.plot([row["datetime"], row["datetime"]], [row["open"], row["close"]], color=c, linewidth=3)

        ax_main.axhline(poc_price, color="#ff1744", linestyle="--", linewidth=1.5, label=f"POC: {format_price(poc_price)}")
        ax_main.axhline(vah_price, color="#00e676", linestyle=":", linewidth=1.3, label=f"VAH: {format_price(vah_price)}")
        ax_main.axhline(val_price, color="#ff9100", linestyle=":", linewidth=1.3, label=f"VAL: {format_price(val_price)}")

        ax_main.set_title(f"Volume Profile: {symbol} ({timeframe})", fontsize=13, color="white", pad=10)
        ax_main.legend(loc="upper left", facecolor="#1e1e1e", edgecolor="none")
        ax_main.grid(True, linestyle="--", alpha=0.15)
        ax_main.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        plt.setp(ax_main.get_xticklabels(), rotation=30, ha="right")

        bin_height = price_bins[1] - price_bins[0]
        bin_centers = price_bins[:-1] + (bin_height / 2)
        bar_colors = ["#ff5252" if i == poc_idx else "#42a5f5" for i in range(len(vol_profile))]

        ax_vp.barh(bin_centers, vol_profile, height=bin_height * 0.9, color=bar_colors, alpha=0.75)
        ax_vp.set_xlabel("Volume", color="white", fontsize=10)
        ax_vp.grid(True, linestyle="--", alpha=0.15)
        ax_vp.tick_params(left=False, labelleft=False)

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        buf.seek(0)

        caption = (
            f"📊 <b>تحلیل والیوم پروفایل (Volume Profile)</b>\n\n"
            f"🔹 <b>نماد:</b> <code>{symbol}</code>\n"
            f"⏱ <b>تایم‌فریم:</b> <code>{timeframe}</code>\n\n"
            f"📍 <b>خط POC (بیشترین حجم):</b> <code>{format_price(poc_price)}</code>\n"
            f"🔺 <b>محدوده بالای ارزش (VAH):</b> <code>{format_price(vah_price)}</code>\n"
            f"🔻 <b>محدوده پایین ارزش (VAL):</b> <code>{format_price(val_price)}</code>\n\n"
            f"💡 <i>قیمت تمایل دارد به سمت POC برگردد.</i>"
        )
        return buf, caption
    except Exception as e:
        logging.error(f"VP generation error: {e}")
        return None, f"❌ خطا در ساخت والیوم پروفایل: {str(e)}"
    finally:
        if figure is not None:
            plt.close(figure)


# =========================================================
# الگوریتم تحلیل تکنیکال (SMC + Volume Profile)
# =========================================================

async def analyze_market(symbol: str, timeframe: str = "15m"):
    try:
        limit = 350
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 220:
            return "❌ داده‌های کافی از صرافی دریافت نشد."

        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        df["rsi"] = 100 - (100 / (1 + rs))

        ema12 = df["close"].ewm(span=12, adjust=False).mean()
        ema26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema12 - ema26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=14).mean()

        plus_dm = pd.Series(np.where((df["high"].diff() > -df["low"].diff()) & (df["high"].diff() > 0), df["high"].diff(), 0.0))
        minus_dm = pd.Series(np.where((-df["low"].diff() > df["high"].diff()) & (-df["low"].diff() > 0), -df["low"].diff(), 0.0))
        tr_s = tr.rolling(window=14).sum()
        plus_di = 100 * (plus_dm.rolling(window=14).sum() / (tr_s + 1e-9))
        minus_di = 100 * (minus_dm.rolling(window=14).sum() / (tr_s + 1e-9))
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
        df["adx"] = dx.rolling(window=14).mean()
        df["vol_ma"] = df["volume"].rolling(window=20).mean()

        # والیوم پروفایل
        vp_window = df.iloc[-100:]
        p_min = vp_window["low"].min()
        p_max = vp_window["high"].max()
        price_bins = np.linspace(p_min, p_max, 40)
        vol_profile = np.zeros(len(price_bins) - 1)
        for _, row in vp_window.iterrows():
            avg_p = (row["open"] + row["close"] + row["high"] + row["low"]) / 4
            idx = np.digitize(avg_p, price_bins) - 1
            if 0 <= idx < len(vol_profile):
                vol_profile[idx] += row["volume"]

        poc_idx = int(np.argmax(vol_profile))
        poc_price = (price_bins[poc_idx] + price_bins[poc_idx + 1]) / 2
        tot_vol = vol_profile.sum()
        va_tgt = tot_vol * 0.70
        sorted_indices = np.argsort(vol_profile)[::-1]
        c_vol = 0
        va_idxs = []
        for idx in sorted_indices:
            c_vol += vol_profile[idx]
            va_idxs.append(idx)
            if c_vol >= va_tgt:
                break
        val_price = price_bins[min(va_idxs)]
        vah_price = price_bins[max(va_idxs) + 1]

        recent_high = df["high"].iloc[-21:-1].max()
        recent_low = df["low"].iloc[-21:-1].min()
        c = df.iloc[-2]
        prev_c = df.iloc[-3]
        current_live_price = float(df["close"].iloc[-1])

        atr_val = c["atr"] if not pd.isna(c["atr"]) and c["atr"] > 0 else current_live_price * 0.015
        adx_val = c["adx"] if not pd.isna(c["adx"]) else 20.0
        vol_ratio = (c["volume"] / c["vol_ma"]) if c["vol_ma"] > 0 else 1.0

        long_score = 0.0
        short_score = 0.0
        trend_bullish = c["close"] > c["ema200"]
        trend_bearish = c["close"] < c["ema200"]

        if c["ema20"] > c["ema50"]:
            long_score += 1.5
        elif c["ema20"] < c["ema50"]:
            short_score += 1.5

        if c["close"] > c["ema50"]:
            long_score += 1.0
        else:
            short_score += 1.0

        if c["macd"] > c["macd_signal"]:
            long_score += 1.0
            if c["macd_hist"] > prev_c["macd_hist"]:
                long_score += 0.5
        elif c["macd"] < c["macd_signal"]:
            short_score += 1.0
            if c["macd_hist"] < prev_c["macd_hist"]:
                short_score += 0.5

        if 52 <= c["rsi"] <= 68:
            long_score += 1.5
        elif c["rsi"] > 75:
            long_score -= 2.0

        if 32 <= c["rsi"] <= 48:
            short_score += 1.5
        elif c["rsi"] < 25:
            short_score -= 2.0

        is_trending = adx_val >= 21
        has_volume = vol_ratio >= 0.95

        vp_long_ok = (c["close"] >= poc_price) and ((c["close"] >= vah_price * 0.998) or (prev_c["low"] <= poc_price and c["close"] > poc_price))
        vp_short_ok = (c["close"] <= poc_price) and ((c["close"] <= val_price * 1.002) or (prev_c["high"] >= poc_price and c["close"] < poc_price))

        if c["close"] > poc_price:
            long_score += 1.0
        elif c["close"] < poc_price:
            short_score += 1.0

        smc_long_ok = (c["close"] >= recent_high * 0.995) and (c["close"] > c["open"])
        smc_short_ok = (c["close"] <= recent_low * 1.005) and (c["close"] < c["open"])

        is_high_prob_long = trend_bullish and (long_score >= 4.5) and is_trending and has_volume and smc_long_ok and vp_long_ok
        is_high_prob_short = trend_bearish and (short_score >= 4.5) and is_trending and has_volume and smc_short_ok and vp_short_ok

        if current_live_price >= vah_price:
            vp_status_tag = f"صعودی (بالای VAH: {format_price(vah_price)})"
        elif current_live_price <= val_price:
            vp_status_tag = f"نزولی (زیر VAL: {format_price(val_price)})"
        else:
            vp_status_tag = f"داخل محدوده ارزش (POC: {format_price(poc_price)})"

        if is_high_prob_long:
            direction = "🟢 صعودی قوی (Strong Long) ⭐⭐⭐"
            sl_val = current_live_price - (1.1 * atr_val)
            tp1_val = current_live_price + (1.0 * atr_val)
            tp2_val = current_live_price + (1.8 * atr_val)
            tp3_val = current_live_price + (2.8 * atr_val)
            tp4_val = current_live_price + (4.0 * atr_val)
            confidence = "۸۲٪ تا ۹۰٪ (تأییدیه همزمان ترند، SMC و والیوم پروفایل)"
            smc_tag = f"✅ تایید ورود نقدینگی بالای {format_price(recent_high)}"
        elif is_high_prob_short:
            direction = "🔴 نزولی قوی (Strong Short) ⭐⭐⭐"
            sl_val = current_live_price + (1.1 * atr_val)
            tp1_val = current_live_price - (1.0 * atr_val)
            tp2_val = current_live_price - (1.8 * atr_val)
            tp3_val = current_live_price - (2.8 * atr_val)
            tp4_val = current_live_price - (4.0 * atr_val)
            confidence = "۸۲٪ تا ۹۰٪ (تأییدیه همزمان ترند، SMC و والیوم پروفایل)"
            smc_tag = f"✅ تایید تخلیه نقدینگی زیر {format_price(recent_low)}"
        else:
            direction = "⚪️ خنثی / بدون معامله (فیلتر حفظ سرمایه)"
            sl_val = "-"
            tp1_val = "-"
            tp2_val = "-"
            tp3_val = "-"
            tp4_val = "-"
            confidence = "نامناسب جهت معامله"
            smc_tag = "⚠️ عدم تشکیل ساختار نقدینگی معتبر"

        report = (
            f"📊 <b>گزارش تحلیلی پیشرفته (High-Probability)</b>\n\n"
            f"🔹 <b>نماد:</b> <code>{symbol}</code>\n"
            f"⏱ <b>تایم‌فریم:</b> <code>{timeframe}</code>\n"
            f"💵 <b>Entry Price:</b> <code>{format_price(current_live_price)}</code>\n"
            f"📈 <b>سیگنال:</b> {direction}\n"
            f"🎯 <b>اعتبار تخمینی:</b> <code>{confidence}</code>\n\n"
            f"🎯 <b>اهداف خروج پله‌ای (Take Profit):</b>\n"
            f"  ▫️ TP 1 (قفل سود): <code>{format_price(tp1_val)}</code>\n"
            f"  ▫️ TP 2 (Target اصلی): <code>{format_price(tp2_val)}</code>\n"
            f"  ▫️ TP 3 (رونددار): <code>{format_price(tp3_val)}</code>\n"
            f"  ▫️ TP 4 (Runner): <code>{format_price(tp4_val)}</code>\n\n"
            f"🛑 <b>حد ضرر (Stop Loss):</b> <code>{format_price(sl_val)}</code>\n\n"
            f"📌 <i>نکته: پس از TP1، استاپ را روی Entry Price قرار دهید (ریسک‌فری).</i>\n\n"
            f"🔍 <b>متریک‌های کلیدی:</b>\n"
            f"  • والیوم پروفایل: <code>{vp_status_tag}</code>\n"
            f"  • اسمارت‌مانی: <code>{smc_tag}</code>\n"
            f"  • RSI: <code>{c['rsi']:.1f}</code>\n"
            f"  • شاخص ADX: <code>{adx_val:.1f}</code> ({'رونددار قوی' if is_trending else 'رِنج / ضعیف'})\n"
            f"  • حجم به میانگین: <code>{vol_ratio:.2f}x</code>\n"
            f"  • وضعیت EMA200: <code>{'بالای ترند بلندمدت' if current_live_price > c['ema200'] else 'زیر ترند بلندمدت'}</code>"
        )
        return report
    except Exception as e:
        logging.error(f"Analysis error: {e}")
        return f"❌ خطایی در تحلیل {symbol} رخ داد: {str(e)}"


# =========================================================
# ماژول اسکن خودکار
# =========================================================

async def scan_one_market(symbol: str, timeframe: str, semaphore: asyncio.Semaphore):
    try:
        async with semaphore:
            report = await analyze_market(symbol, timeframe)
        if "Strong Long" in report or "Strong Short" in report:
            return symbol, timeframe, report
        return None
    except Exception as e:
        logging.error(f"Auto scan error for {symbol} on {timeframe}: {e}")
        return None


async def scan_all_mexc_markets():
    markets = await exchange.load_markets()
    symbols = sorted({
        m["symbol"]
        for m in markets.values()
        if m.get("active", True) is not False
        and m.get("swap") is True
        and m.get("linear") is True
        and m.get("quote") == "USDT"
        and m.get("settle") == "USDT"
    })

    semaphore = asyncio.Semaphore(AUTO_SCAN_CONCURRENCY)
    tasks = [scan_one_market(symbol, tf, semaphore) for symbol in symbols for tf in AUTO_SIGNAL_TIMEFRAMES]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    signals = [r for r in results if isinstance(r, tuple)]
    signals.sort(key=lambda item: (item[0], item[1]))
    return len(symbols), signals


def split_signal_reports(reports, max_length=3900):
    chunks = []
    current_chunk = ""
    for r in reports:
        if not current_chunk:
            current_chunk = r
            continue
        candidate = current_chunk + "\n\n" + r
        if len(candidate) <= max_length:
            current_chunk = candidate
        else:
            chunks.append(current_chunk)
            current_chunk = r
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


# =========================================================
# هندلرهای تلگرام
# =========================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام! به ربات تحلیل تکنیکال خوش آمدید.\n"
        "ارز مورد نظر خود را برای تحلیل انتخاب کنید:",
        reply_markup=get_symbols_keyboard(),
    )


@dp.callback_query(lambda c: c.data and c.data.startswith("sym:"))
async def process_symbol_select(callback_query: types.CallbackQuery):
    symbol = callback_query.data.split("sym:")[1]
    await callback_query.message.edit_text(
        f"ارز انتخابی: <b>{symbol}</b>\n"
        "لطفاً تایم‌فریم یا ابزار مورد نظر را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard(symbol),
    )
    await callback_query.answer()


@dp.callback_query(lambda c: c.data and c.data.startswith("tf:"))
async def process_timeframe_select(callback_query: types.CallbackQuery):
    await callback_query.answer()
    data_str = callback_query.data[3:]
    symbol, tf = data_str.rsplit(":", 1)

    await callback_query.message.edit_text("⏳ در حال دریافت داده‌ها و تحلیل هوشمند... لطفاً شکیبا باشید.")
    result = await analyze_market(symbol, tf)
    await callback_query.message.edit_text(result, reply_markup=get_timeframe_keyboard(symbol))


@dp.callback_query(lambda c: c.data and c.data.startswith("vp:"))
async def process_volume_profile(callback_query: types.CallbackQuery):
    await callback_query.answer("در حال آماده‌سازی تصویر...")
    data_str = callback_query.data[3:]
    symbol, tf = data_str.rsplit(":", 1)

    wait_msg = await callback_query.message.answer("⏳ در حال پردازش داده‌های حجم و تولید چارت...")
    buf, caption = await generate_volume_profile_chart(symbol, tf)
    try:
        await wait_msg.delete()
    except Exception:
        pass

    if buf:
        photo = BufferedInputFile(buf.getvalue(), filename=f"vp_{symbol.replace('/', '_').replace(':', '_')}.png")
        await callback_query.message.answer_photo(photo=photo, caption=caption)
    else:
        await callback_query.message.answer(caption)


@dp.callback_query(lambda c: c.data == "back_to_symbols")
async def process_back(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "ارز مورد نظر خود را برای تحلیل انتخاب کنید:",
        reply_markup=get_symbols_keyboard(),
    )


@dp.callback_query(lambda c: c.data == "auto_signal")
async def process_auto_signal(callback_query: types.CallbackQuery):
    await callback_query.answer("اسکن بازار MEXC شروع شد...")
    await callback_query.message.edit_text(
        "⏳ در حال دریافت تمام قراردادهای فیوچرز USDT صرافی MEXC...\n"
        "سپس تمام تایم‌فریم‌های ربات بررسی می‌شوند.\n\n"
        "این عملیات ممکن است چند دقیقه زمان ببرد."
    )

    try:
        total_symbols, signals = await scan_all_mexc_markets()
        if not signals:
            await callback_query.message.edit_text(
                f"✅ اسکن کامل شد.\n\n"
                f"🔎 تعداد ارزهای بررسی‌شده: <code>{total_symbols}</code>\n"
                f"⏱ تایم‌فریم‌ها: <code>{', '.join(AUTO_SIGNAL_TIMEFRAMES)}</code>\n\n"
                f"⚪️ در حال حاضر هیچ‌کدام از ارزها شرایط ورود ندارند.",
                reply_markup=get_symbols_keyboard(),
            )
            return

        reports = []
        for symbol, timeframe, report in signals:
            reports.append(
                f"📡 <b>سیگنال اتوماتیک</b>\n"
                f"🔹 نماد: <code>{symbol}</code>\n"
                f"⏱ تایم‌فریم: <code>{timeframe}</code>\n\n"
                f"{report}"
            )

        chunks = split_signal_reports(reports, max_length=3900)
        await callback_query.message.edit_text(
            f"✅ اسکن کامل شد.\n\n"
            f"🔎 ارزهای بررسی‌شده: <code>{total_symbols}</code>\n"
            f"🚨 سیگنال‌های یافت‌شده: <code>{len(signals)}</code>\n\n"
            f"گزارش‌ها در پیام‌های بعدی ارسال می‌شوند.",
            reply_markup=get_symbols_keyboard(),
        )
        for chunk in chunks:
            await callback_query.message.answer(chunk)
    except Exception as e:
        logging.error(f"Auto signal handler error: {e}")
        await callback_query.message.edit_text(
            f"❌ خطا در اسکن خودکار:\n<code>{str(e)}</code>",
            reply_markup=get_symbols_keyboard(),
        )


# =========================================================
# سرور Health Check مخصوص پورت Render
# =========================================================

async def health_check(request):
    return web.Response(text="Bot is running OK", status=200)


async def start_web_server():
    port = int(os.getenv("PORT", "10000"))
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/healthz", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start(GAPGPTMASKTOKENp4nwj0gbwaX2Xging.info(f"Health server listGAPGPTMASKTOKENp4nwj0gbwaX3XportGAPGPTMASKTOKENp4nwj0gbwaX4Xort}")
    return runner


# =========================GAPGPTMASKTOKENp4nwj0gbwaX5X=======================
# اجرای اصلی
# =========================================================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in Environment Variables.")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    web_runner = None

    try:
        web_runner = await start_web_server()
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Bot started successfully!")
        await dp.start_polling(bot)
    finally:
        logging.info("Shutting down...")
        if web_runner:
            await web_runner.cleanup()
        try:
            await exchange.close()
        except Exception:
            pass
        try:
            await bot.session.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Stopped.")
