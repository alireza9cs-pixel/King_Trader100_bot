import os
import io
import asyncio
import logging
from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # جلوگیری از خطای نبود GUI در سرورها
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# توکن ربات از متغیرهای محیطی سیستم خوانده می‌شود
GAPGPTMASKTOKENm42janthlamX0X = os.getenv("GAPGPTMASKTOKENm42janthlamX1X", "").strip()

# صرافی MEXC برای قراردادهای فیوچرز
exchange = ccxt.mexc({'enableRateLimit': True, 'timeout': 10000, 'options': {'defaultType': 'swap'}})

dp = Dispatcher()

def get_symbols_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="بیت‌کوین (BTC)", callback_data="sym:BTC/USDT:USDT"),
            InlineKeyboardButton(text="اتریوم (ETH)", callback_data="sym:ETH/USDT:USDT")
        ],
        [
            InlineKeyboardButton(text="سولانا (SOL)", callback_data="sym:SOL/USDT:USDT"),
            InlineKeyboardButton(text="پپه (PEPE)", callback_data="sym:PEPE/USDT:USDT")
        ]
    ])

def get_timeframe_keyboard(symbol):
    return InlineKeyboardMarkup(inline_keyboard=[
        # بخش سیگنال و تحلیل تکنیکال
        [
            InlineKeyboardButton(text="📊 سیگنال 1m", callback_data=f"tf:{symbol}:1m"),
            InlineKeyboardButton(text="📊 سیگنال 5m", callback_data=f"tf:{symbol}:5m"),
            InlineKeyboardButton(text="📊 سیگنال 15m", callback_data=f"tf:{symbol}:15m")
        ],
        [
            InlineKeyboardButton(text="📊 سیگنال 1h", callback_data=f"tf:{symbol}:1h"),
            InlineKeyboardButton(text="📊 سیگنال 4h", callback_data=f"tf:{symbol}:4h"),
            InlineKeyboardButton(text="📊 سیگنال 1D", callback_data=f"tf:{symbol}:1d")
        ],
        # بخش ۶ تایم‌فریم اختصاصی والیوم پروفایل
        [
            InlineKeyboardButton(text="📈 VP 1m", callback_data=f"vp:{symbol}:1m"),
            InlineKeyboardButton(text="📈 VP 5m", callback_data=f"vp:{symbol}:5m"),
            InlineKeyboardButton(text="📈 VP 15m", callback_data=f"vp:{symbol}:15m")
        ],
        [
            InlineKeyboardButton(text="📈 VP 1h", callback_data=f"vp:{symbol}:1h"),
            InlineKeyboardButton(text="📈 VP 4h", callback_data=f"vp:{symbol}:4h"),
            InlineKeyboardButton(text="📈 VP 1D", callback_data=f"vp:{symbol}:1d")
        ],
        [
            InlineKeyboardButton(text="🔙 بازگشت به لیست ارزها", callback_data="back_to_symbols")
        ]
    ])

def format_price(price):
    """فرمت هوشمند قیمت برای جلوگیری از صفر شدن میم‌کوین‌ها"""
    if price is None or price == "-":
        return "-"
    try:
        p = float(price)
        if p == 0:
            return "0.0"
        if p < 0.0001:
            return f"{p:.8f}"
        elif p < 1:
            return f"{p:.5f}"
        elif p < 100:
            return f"{p:.3f}"
        else:
            return f"{p:.2f}"
    except:
        return str(price)

# ----------------- ماژول چارت والیوم پروفایل -----------------
async def generate_volume_profile_chart(symbol: str, timeframe: str = '1h'):
    try:
        limit = 200
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if GAPGPTMASKTOKENm42janthlamX2X ohlcv or len(ohlcv) < 50:
            return None, "داده‌های کافی جهت رسم پروفایل حجم موجود نیست."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')

        # تقسیم دامنه قیمت به سطوح مختلف
        price_min = df['low'].min()
        price_max = df['high'].max()
        bins = 45
        price_bins = np.linspace(price_min, price_max, bins)
        vol_profile = np.zeros(len(price_bins) - 1)

        # تخصیص حجم معاملات به قیمت‌ها
        for _, row in df.iterrows():
            idx = np.digitize((row['open'] + row['close'] + row['high'] + row['low']) / 4, price_bins) - 1
            if 0 <= idx < len(vol_profile):
                vol_profile[idx] += row['volume']

        # محاسبه POC
        poc_idx = np.argmax(vol_profile)
        poc_price = (price_bins[poc_idx] + price_bins[poc_idx + 1]) / 2

        # محاسبه Value Area (70 درصد حجم کل)
        total_vol = vol_profile.sum()
        va_target = total_vol * 0.70
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

        # رسم چارت
        plt.style.use('dark_background')
        fig, (ax_main, ax_vp) = plt.subplots(
            1, 2, figsize=(12, 6), sharey=True,
            gridspec_kw={'width_ratios': [4, 1.2], 'wspace': 0.05}
        )

        for i, row in df.iterrows():
            color = '#26a69a' if row['close'] >= row['open'] else '#ef5350'
            ax_main.plot([row['datetime'], row['datetime']], [row['low'], row['high']], color=color, linewidth=1)
            ax_main.plot([row['datetime'], row['datetime']], [row['open'], row['close']], color=color, linewidth=3)

        # خطوط POC و VAH و VAL
        ax_main.axhline(poc_price, color='#ff1744', linestyle='--', linewidth=1.5, label=f'POC: {format_price(poc_price)}')
        ax_main.axhline(vah_price, color='#00e676', linestyle=':', linewidth=1.3, label=f'VAH: {format_price(vah_price)}')
        ax_main.axhline(val_price, color='#ff9100', linestyle=':', linewidth=1.3, label=f'VAL: {format_price(val_price)}')
        ax_main.set_title(f"Volume Profile Chart: {symbol} ({timeframe})", fontsize=13, color='white', pad=10)
        ax_main.legend(loc='upper left', facecolor='#1e1e1e', edgecolor='none')
        ax_main.grid(True, linestyle='--', alpha=0.15)
        ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        plt.setp(ax_main.get_xticklabels(), rotation=30, ha='right')

        # ستون‌های والیوم پروفایل
        bin_height = price_bins[1] - price_bins[0]
        bin_centers = price_bins[:-1] + (bin_height / 2)
        bar_colors = ['#ff5252' if i == poc_idx else '#42a5f5' for i in range(len(vol_profile))]

        ax_vp.barh(bin_centers, vol_profile, height=bin_height * 0.9, color=bar_colors, alpha=0.75)
        ax_vp.set_xlabel("Volume", color='white', fontsize=10)
        ax_vp.grid(True, linestyle='--', alpha=0.15)
        ax_vp.tick_params(left=False, labelleft=False)

        buf = io.BytesIO()
        plt.tight_layout()
        plt.savefig(buf, format='png', dpi=120)
        buf.seek(0)
        plt.close(fig)

        caption = (
            f"📊 <b>تحلیل والیوم پروفایل (Volume Profile)</b>\n\n"
            f"🔹 <b>نماد:</b> <code>{symbol}</code>\n"
            f"⏱ <b>تایم‌فریم انتخابی:</b> <code>{timeframe}</code>\n\n"
            f"📍 <b>خط کنترل (POC - بیشترین حجم معامله شده):</b>\n"
            f"👉 <code>{format_price(poc_price)}</code>\n\n"
            f"🔺 <b>محدوده بالای ارزش (VAH):</b> <code>{format_price(vah_price)}</code>\n"
            f"🔻 <b>محدوده پایین ارزش (VAL):</b> <code>{format_price(val_price)}</code>\n\n"
            f"💡 <i>نکته: قیمت تمایل دارد به سمت POC برگردد. شکست و تثبیت خارج از محدوده VAH/VAL نشانه قدرت جهت‌گیری روند است.</i>"
        )
        return buf, caption

    except Exception as e:
        logging.error(f"VP generation error: {e}")
        return None, f"❌ خطا در ساخت والیوم پروفایل: {str(e)}"

# ----------------- الگوریتم تحلیل تکنیکال (کاملاً دست‌نخورده) -----------------
async def analyze_market(symbol: str, timeframe: str = '15m'):
    try:
        limit = 350
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if GAPGPTMASKTOKENm42janthlamX3X ohlcv or len(ohlcv) < 220:
            return "❌ داده‌های کافی از صرافی دریافت نشد. لطفاً از نمادهای معتبر استفاده کنید."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # محاسبه EMA
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # محاسبه RSI
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        # محاسبه MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        # محاسبه ATR
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()

        # محاسبه ADX
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm = pd.Series(np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0.0))
        minus_dm = pd.Series(np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0.0))
        
        tr_s = tr.rolling(window=14).sum()
        plus_di = 100 * (plus_dm.rolling(window=14).sum() / (tr_s + 1e-9))
        minus_di = 100 * (minus_dm.rolling(window=14).sum() / (tr_s + 1e-9))
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
        df['adx'] = dx.rolling(window=14).mean()

        df['vol_ma'] = df['volume'].rolling(window=20).mean()

        c = df.iloc[-2]
        prev_c = df.iloc[-3]
        current_live_price = df['close'].iloc[-1]
        
        atr_val = c['atr'] if GAPGPTMASKTOKENm42janthlamX4X pd.isna(c['atr']) else current_live_price * 0.015
        adx_val = c['adx'] if GAPGPTMASKTOKENm42janthlamX5X pd.isna(c['adx']) else 20.0
        vol_ratio = (c['volume'] / c['vol_ma']) if c['vol_ma'] > 0 else 1.0

        long_score = 0
        short_score = 0

        # فیلتر ترند کلان
        trend_bullish = c['close'] > c['ema200']
        trend_bearish = c['close'] < c['ema200']

        if c['ema20'] > c['ema50']:
            long_score += 1.5
        elif c['ema20'] < c['ema50']:
            short_score += 1.5

        if c['close'] > c['ema50']:
            long_score += 1.0
        else:
            short_score += 1.0

        if c['macd'] > c['macd_signal']:
            long_score += 1.0
            if c['macd_hist'] > prev_c['macd_hist']:
                long_score += 0.5
        elif c['macd'] < c['macd_signal']:
            short_score += 1.0
            if c['macd_hist'] < prev_c['macd_hist']:
                short_score += 0.5

        if 52 <= c['rsi'] <= 68:
            long_score += 1.5
        elif c['rsi'] > 75:
            long_score -= 2.0

        if 32 <= c['rsi'] <= 48:
            short_score += 1.5
        elif c['rsi'] < 25:
            short_score -= 2.0

        is_trending = adx_val >= 21
        has_volume = vol_ratio >= 0.95

        is_high_prob_long = trend_bullish and (long_score >= 4.0) and is_trending and has_volume
        is_high_prob_short = trend_bearish and (short_score >= 4.0) and is_trending and has_volume

        if is_high_prob_long:
            direction = "🟢 صعودی قوی (Strong Long) ⭐⭐⭐"
            sl_val = current_live_price - (1.1 * atr_val)
            tp1_val = current_live_price + (1.0 * atr_val)
            tp2_val = current_live_price + (1.8 * atr_val)
            tp3_val = current_live_price + (2.8 * atr_val)
            tp4_val = current_live_price + (4.0 * atr_val)
            confidence = "۸۰٪ تا ۸۸٪ (ورود پرایس‌اکشنی و هم‌جهت با ترند کلان)"
        elif is_high_prob_short:
            direction = "🔴 نزولی قوی (Strong Short) ⭐⭐⭐"
            sl_val = current_live_price + (1.1 * atr_val)
            tp1_val = current_live_price - (1.0 * atr_val)
            tp2_val = current_live_price - (1.8 * atr_val)
            tp3_val = current_live_price - (2.8 * atr_val)
            tp4_val = current_live_price - (4.0 * atr_val)
            confidence = "۸۰٪ تا ۸۸٪ (ورود پرایس‌اکشنی و هم‌جهت با ترند کلان)"
        else:
            direction = "⚪️ خنثی / بدون معامله (فیلتر حفظ سرمایه - بازار نوسانی و فاقد مومنتوم)"
            sl_val = tp1_val = tp2_val = tp3_val = tp4_val = "-"
            confidence = "نامناسب جهت معامله"

        report = (
            f"📊 <b>گزارش تحلیلی پیشرفته (High-Probability)</b>\n\n"
            f"🔹 <b>نماد:</b> <code>{symbol}</code>\n"
            f"⏱ <b>تایم‌فریم:</b> <code>{timeframe}</code>\n"
            f"💵 <b>Entry Price:</b> <code>{format_price(current_live_price)}</code>\n"
            f"📈 <b>سیگنال:</b> {direction}\n"
            f"🎯 <b>اعتبار تخمینی موقعیت:</b> <code>{confidence}</code>\n\n"
            f"🎯 <b>اهداف خروج پله‌ای (Take Profit):</b>\n"
            f"  ▫️ TP 1 (Scalp / قفل سود): <code>{format_price(tp1_val)}</code>\n"
            f"  ▫️ TP 2 (Target اصلی): <code>{format_price(tp2_val)}</code>\n"
            f"  ▫️ TP 3 (رونددار): <code>{format_price(tp3_val)}</code>\n"
            f"  ▫️ TP 4 (Runner): <code>{format_price(tp4_val)}</code>\n\n"
            f"🛑 <b>حد ضرر تحلیلی (Stop Loss):</b> <code>{format_price(sl_val)}</code>\n\n"
            f"📌 <i>نکته معاملاتی: پس از تاچ شدن TP 1، استاپ را دقیقاً روی Entry Price قرار دهید (ریسک‌فری).</i>\n\n"
            f"🔍 <b>متریک‌های کلیدی:</b>\n"
            f"  • RSI: <code>{c['rsi']:.1f}</code>\n"
            f"  • شاخص قدرت ترند (ADX): <code>{adx_val:.1f}</code> ({'رونددار قوی' if is_trending else 'رِنج / ضعیف'})\n"
            f"  • حجم نسبت به میانگین: <code>{vol_ratio:.2f}x</code>\n"
            f"  • وضعیت EMA200: <code>{'بالای ترند بلندمدت' if current_live_price > c['ema200'] else 'زیر ترند بلندمدت'}</code>"
        )
        return report

    except Exception as e:
        logging.error(f"Analysis error: {e}")
        return f"❌ خطایی در تحلیل {symbol} رخ داد: {str(e)}"

# ----------------- هندلرهای تلگرام -----------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "سلام! به ربات تحلیل تکنیکال خوش آمدید.\nارز مورد نظر خود را برای تحلیل انتخاب کنید:",
        reply_markup=get_symbols_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith('sym:'))
async def process_symbol_select(callback_query: types.CallbackQuery):
    symbol = callback_query.data.split('sym:')[1]
    await callback_query.message.edit_text(
        f"ارز انتخابی: <b>{symbol}</b>\nلطفاً ابزار یا تایم‌فریم مورد نظر را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard(symbol)
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('tf:'))
async def process_timeframe_select(callback_query: types.CallbackQuery):
    await callback_query.answer()
    data_str = callback_query.data[3:]
    symbol, tf = data_str.rsplit(':', 1)
    
    await callback_query.message.edit_text("⏳ در حال دریافت داده‌ها و تحلیل هوشمند... لطفاً شکیبا باشید.")
    result = await analyze_market(symbol, tf)
    await callback_query.message.edit_text(result, reply_markup=get_timeframe_keyboard(symbol))

@dp.callback_query(lambda c: c.data.startswith('vp:'))
async def process_volume_profile(callback_query: types.CallbackQuery):
    await callback_query.answer("در حال دریافت داده‌های حجم...")
    data_str = callback_query.data[3:]
    symbol, tf = data_str.rsplit(':', 1)
    
    wait_msg = await callback_query.message.answer(f"⏳ در حال رسم Volume Profile در تایم‌فریم <b>{tf}</b>...")
    buf, caption = await generate_volume_profile_chart(symbol, tf)
    
    await wait_msg.delete()
    if buf:
        photo = BufferedInputFile(buf.getvalue(), filename=f"vp_{symbol.replace('/', '_')}_{tf}.png")
        await callback_query.message.answer_photo(photo=photo, caption=caption)
    else:
        await callback_query.message.answer(caption)

@dp.callback_query(lambda c: c.data == 'back_to_symbols')
async def process_back(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "ارز مورد نظر خود را برای تحلیل انتخاب کنید:",
        reply_markup=get_symbols_keyboard()
    )

@dp.message()
async def process_custom_symbol(message: types.Message):
    raw_text = message.text.strip().upper()
    if "/" GAPGPTMASKTOKENm42janthlamX6X in raw_text:
        symbol = f"{raw_text}/USDT:USDT"
    else:
        symbol = raw_text
    
    await message.answer(
        f"ارز انتخابی: <b>{symbol}</b>\nلطفاً ابزار یا تایم‌فریم مورد نظر را انتخاب کنید:",
        reply_markup=get_timeframe_keyboard(symbol)
    )

async def handle_ping(request):
    return web.Response(text="Bot is awake and running perfectly!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/ping", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")

async def main():
    if GAPGPTMASKTOKENm42janthlamX7X GAPGPTMASKTOKENm42janthlamX8X:
        logging.error("GAPGPTMASKTOKENm42janthlamX9X is GAPGPTMASKTOKENm42janthlamX10X set in environment variables! لطفاً توکن تلگرام را تنظیم کنید.")
        return

    bot = Bot(token=GAPGPTMASKTOKENm42janthlamX11X, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await start_web_server()
    logging.info("Starting Telegram Bot Polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(main())
