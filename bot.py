import os
import io
import asyncio
import logging
from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # جلوگیری از ارور نبود GUI روی سرور
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# توکن ربات از متغیر محیطی خوانده می‌شود
TOKEN = os.getenv("GAPGPTMASKTOKENzzi8ilqs35gX1X", "").strip()

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
        [
            InlineKeyboardButton(text="1m", callback_data=f"tf:{symbol}:1m"),
            InlineKeyboardButton(text="5m", callback_data=f"tf:{symbol}:5m"),
            InlineKeyboardButton(text="15m", callback_data=f"tf:{symbol}:15m")
        ],
        [
            InlineKeyboardButton(text="1h", callback_data=f"tf:{symbol}:1h"),
            InlineKeyboardButton(text="4h", callback_data=f"tf:{symbol}:4h"),
            InlineKeyboardButton(text="1D", callback_data=f"tf:{symbol}:1d")
        ],
        [
            InlineKeyboardButton(text="📊 چارت والیوم پروفایل (Volume Profile)", callback_data=f"vp:{symbol}:1h")
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
        if not ohlcv or len(ohlcv) < 50:
            return None, "داده‌های کافی جهت رسم پروفایل حجم موجود نیست."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')

        price_min = df['low'].min()
        price_max = df['high'].max()
        bins = 45
        price_bins = np.linspace(price_min, price_max, bins)
        vol_profile = np.zeros(len(price_bins) - 1)

        for _, row in df.iterrows():
            idx = np.digitize((row['open'] + row['close'] + row['high'] + row['low']) / 4, price_bins) - 1
            if 0 <= idx < len(vol_profile):
                vol_profile[idx] += row['volume']

        poc_idx = np.argmax(vol_profile)
        poc_price = (price_bins[poc_idx] + price_bins[poc_idx + 1]) / 2

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

        plt.style.use('dark_background')
        fig, (ax_main, ax_vp) = plt.subplots(
            1, 2, figsize=(12, 6), sharey=True,
            gridspec_kw={'width_ratios': [4, 1.2], 'wspace': 0.05}
        )

        for i, row in df.iterrows():
            color = '#26a69a' if row['close'] >= row['open'] else '#ef5350'
            ax_main.plot([row['datetime'], row['datetime']], [row['low'], row['high']], color=color, linewidth=1)
            ax_main.plot([row['datetime'], row['datetime']], [row['open'], row['close']], color=color, linewidth=3)

        ax_main.axhline(poc_price, color='#ff1744', linestyle='--', linewidth=1.5, label=f'POC: {format_price(poc_price)}')
        ax_main.axhline(vah_price, color='#00e676', linestyle=':', linewidth=1.3, label=f'VAH: {format_price(vah_price)}')
        ax_main.axhline(val_price, color='#ff9100', linestyle=':', linewidth=1.3, label=f'VAL: {format_price(val_price)}')
        ax_main.set_title(f"Volume Profile Chart: {symbol} ({timeframe})", fontsize=13, color='white', pad=10)
        ax_main.legend(loc='upper left', facecolor='#1e1e1e', edgecolor='none')
        ax_main.grid(True, linestyle='--', alpha=0.15)
        ax_main.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        plt.setp(ax_main.get_xticklabels(), rotation=30, ha='right')

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
            f"⏱ <b>تایم‌فریم مبنا:</b> <code>{timeframe}</code>\n\n"
            f"📍 <b>خط کنترل (POC - بیشترین حجم معامله شده):</b>\n"
            f"👉 <code>{format_price(poc_price)}</code>\n\n"
            f"🔺 <b>محدوده بالای ارزش (VAH):</b> <code>{format_price(vah_price)}</code>\n"
            f"🔻 <b>محدوده پایین ارزش (VAL):</b> <code>{format_price(val_price)}</code>\n\n"
            f"💡 <i>نکته: قیمت تمایل دارد به سمت POC برگردد. خروج تثبیت‌شده از محدوده VAH/VAL می‌تواند نشانه جهت‌گیری اصلی بازار باشد.</i>"
        )
        return buf, caption

    except Exception as e:
        logging.error(f"VP generation error: {e}")
        return None, f"❌ خطا در ساخت والیوم پروفایل: {str(e)}"

# ----------------- الگوریتم تحلیل تکنیکال تلفیقی -----------------
async def analyze_market(symbol: str, timeframe: str = '15m'):
    try:
        limit = 350
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        ohlcv_4h = await exchange.fetch_ohlcv(symbol, timeframe='4h', limit=50)

        if not ohlcv or len(ohlcv) < 220 or not ohlcv_4h or len(ohlcv_4h) < 30:
            return "❌ داده‌های کافی از صرافی دریافت نشد."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        trend_4h = "bullish" if df_4h['close'].iloc[-1] > df_4h['close'].rolling(50).mean().iloc[-1] else "bearish"
        df['pv'] = df['volume'] * (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = df['pv'].cumsum() / df['volume'].cumsum()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['vol_ma'] = df['volume'].rolling(window=20).mean()

        c = df.iloc[-2]
        prev_c = df.iloc[-3]
        current_live_price = df['close'].iloc[-1]
        
        atr_val = c['atr'] if not pd.isna(c['atr']) else current_live_price * 0.015
        vol_ratio = (c['volume'] / c['vol_ma']) if c['vol_ma'] > 0 else 1.0
        recent_high = df['high'].iloc[-25:-2].max()
        recent_low = df['low'].iloc[-25:-2].min()

        bullish_fvg = prev_c['high'] < c['low']
        bearish_fvg = prev_c['low'] > c['high']
        long_liq_sweep = (c['low'] < recent_low) and (c['close'] > recent_low) and (c['close'] > c['open'])
        short_liq_sweep = (c['high'] > recent_high) and (c['close'] < recent_high) and (c['close'] < c['open'])
        bullish_engulf = (c['close'] > prev_c['high']) and (c['close'] > c['open']) and (abs(c['close'] - c['open']) > atr_val * 0.8)
        bearish_engulf = (c['close'] < prev_c['low']) and (c['close'] < c['open']) and (abs(c['close'] - c['open']) > atr_val * 0.8)
        ftr_bullish = (c['close'] > recent_high) and (c['low'] > prev_c['low'])
        ftr_bearish = (c['close'] < recent_low) and (c['high'] < prev_c['high'])

        long_score, short_score = 0, 0
        if c['ema20'] > c['ema50']: long_score += 1.0
        elif c['ema20'] < c['ema50']: short_score += 1.0
        if c['macd'] > c['macd_signal']: long_score += 1.0
        elif c['macd'] < c['macd_signal']: short_score += 1.0
        if 48 <= c['rsi'] <= 68: long_score += 1.0
        if 32 <= c['rsi'] <= 52: short_score += 1.0
        if bullish_fvg or long_liq_sweep: long_score += 2.0
        if bearish_fvg or short_liq_sweep: short_score += 2.0
        if bullish_engulf or ftr_bullish: long_score += 2.0
        if bearish_engulf or ftr_bearish: short_score += 2.0

        vwap_val = df['vwap'].iloc[-1]
        can_filter_long = (trend_4h == "bullish") and (current_live_price > vwap_val)
        can_filter_short = (trend_4h == "bearish") and (current_live_price < vwap_val)

        is_high_prob_long = can_filter_long and (long_score >= 5.0) and (bullish_engulf or ftr_bullish or long_liq_sweep)
        is_high_prob_short = can_filter_short and (short_score >= 5.0) and (bearish_engulf or ftr_bearish or short_liq_sweep)

        if is_high_prob_long:
            direction = "🟢 صعودی قوی (Strong Long) ⭐⭐⭐"
            sl_val = min(min(c['low'], prev_c['low']), current_live_price - (1.2 * atr_val))
            risk_dist = abs(current_live_price - sl_val)
            tp1, tp2, tp3, tp4 = current_live_price + (1.2 * risk_dist), current_live_price + (2.0 * risk_dist), current_live_price + (3.2 * risk_dist), current_live_price + (4.5 * risk_dist)
            ict_tag = "تایید جاروب نقدینگی" if (long_liq_sweep or bullish_fvg) else "جریان نقدینگی صعودی"
            rtm_tag = "اینگالف مومنتومی / FTR"
        elif is_high_prob_short:
            direction = "🔴 نزولی قوی (Strong Short) ⭐⭐⭐"
            sl_val = max(max(c['high'], prev_c['high']), current_live_price + (1.2 * atr_val))
            risk_dist = abs(sl_val - current_live_price)
            tp1, tp2, tp3, tp4 = current_live_price - (1.2 * risk_dist), current_live_price - (2.0 * risk_dist), current_live_price - (3.2 * risk_dist), current_live_price - (4.5 * risk_dist)
            ict_tag = "تایید جاروب نقدینگی / FVG نزولی" if (short_liq_sweep or bearish_fvg) else "تخلیه نقدینگی سازمانی"
            rtm_tag = "اینگالف کف قبلی / شکست عرضه"
        else:
            return "⚪️ خنثی / بدون معامله (فیلتر حفظ سرمایه - عدم هم‌راستایی)"

        return (f"📊 <b>گزارش تحلیلی پیشرفته</b>\n\n"
                f"🔹 <b>نماد:</b> <code>{symbol}</code>\n"
                f"💵 <b>Entry Price:</b> <code>{format_price(current_live_price)}</code>\n"
                f"📈 <b>سیگنال:</b> {direction}\n\n"
                f"🎯 <b>اهداف:</b>\n TP1: <code>{format_price(tp1)}</code> | TP2: <code>{format_price(tp2)}</code>\n"
                f"🛑 <b>حد ضرر:</b> <code>{format_price(sl_val)}</code>\n\n"
                f"🔍 <b>متریک‌ها:</b> روند 4H: {trend_4h} | تاییدیه: {ict_tag}")

    except Exception as e:
        logging.error(f"Analysis error: {e}")
        return f"❌ خطایی رخ داد: {str(e)}"

# ----------------- هندلرهای تلگرام -----------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("سلام! ارز مورد نظر خود را انتخاب کنید:", reply_markup=get_symbols_keyboard())

@dp.callback_query(lambda c: c.data.startswith('sym:'))
async def process_symbol_select(callback_query: types.CallbackQuery):
    symbol = callback_query.data.split('sym:')[1]
    await callback_query.message.edit_text(f"ارز: <b>{symbol}</b>", reply_markup=get_timeframe_keyboard(symbol))
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('tf:'))
async def process_timeframe_select(callback_query: types.CallbackQuery):
    await callback_query.answer()
    data = callback_query.data[3:].rsplit(':', 1)
    await callback_query.message.edit_text("⏳ تحلیل...", reply_markup=get_timeframe_keyboard(data[0]))
    result = await analyze_market(data[0], data[1])
    await callback_query.message.edit_text(result, reply_markup=get_timeframe_keyboard(data[0]))

@dp.callback_query(lambda c: c.data.startswith('vp:'))
async def process_volume_profile(callback_query: types.CallbackQuery):
    await callback_query.answer("در حال آماده‌سازی...")
    data = callback_query.data[3:].rsplit(':', 1)
    buf, caption = await generate_volume_profile_chart(data[0], data[1])
    if buf:
        await callback_query.message.answer_photo(photo=BufferedInputFile(buf.getvalue(), filename="vp.png"), caption=caption)
    else:
        await callback_query.message.answer(caption)

@dp.callback_query(lambda c: c.data == 'back_to_symbols')
async def process_back(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_text("ارز مورد نظر خود را انتخاب کنید:", reply_markup=get_symbols_keyboard())

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is running"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000))).start()

async def main():
    if not TOKEN:
        logging.error("توکن ربات در متغیرهای محیطی یافت نشد!")
        return

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
