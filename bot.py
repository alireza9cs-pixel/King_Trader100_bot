import os
import io
import asyncio
import logging
from aiohttp import web
import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logging.basicConfig(level=logging.INFO)

# توکن ربات را مستقیماً اینجا وارد کنید یا در متغیرهای محیطی با نام BOT_TOKEN ست کنید
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

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
            InlineKeyboardButton(text="📊 سیگنال 1m", callback_data=f"tf:{symbol}:1m"),
            InlineKeyboardButton(text="📊 سیگنال 5m", callback_data=f"tf:{symbol}:5m"),
            InlineKeyboardButton(text="📊 سیگنال 15m", callback_data=f"tf:{symbol}:15m")
        ],
        [
            InlineKeyboardButton(text="📊 سیگنال 1h", callback_data=f"tf:{symbol}:1h"),
            InlineKeyboardButton(text="📊 سیگنال 4h", callback_data=f"tf:{symbol}:4h"),
            InlineKeyboardButton(text="📊 سیگنال 1D", callback_data=f"tf:{symbol}:1d")
        ],
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
    if price is None or price == "-": return "-"
    try:
        p = float(price)
        if p == 0: return "0.0"
        if p < 0.0001: return f"{p:.8f}"
        elif p < 1: return f"{p:.5f}"
        elif p < 100: return f"{p:.3f}"
        else: return f"{p:.2f}"
    except: return str(price)

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
            if cum_vol >= va_target: break

        val_price = price_bins[min(va_indices)]
        vah_price = price_bins[max(va_indices) + 1]

        plt.style.use('dark_background')
        fig, (ax_main, ax_vp) = plt.subplots(1, 2, figsize=(12, 6), sharey=True, gridspec_kw={'width_ratios': [4, 1.2], 'wspace': 0.05})

        for i, row in df.iterrows():
            color = '#26a69a' if row['close'] >= row['open'] else '#ef5350'
            ax_main.plot([row['datetime'], row['datetime']], [row['low'], row['high']], color=color, linewidth=1)
            ax_main.plot([row['datetime'], row['datetime']], [row['open'], row['close']], color=color, linewidth=3)

        ax_main.axhline(poc_price, color='#ff1744', linestyle='--', linewidth=1.5, label=f'POC: {format_price(poc_price)}')
        ax_main.axhline(vah_price, color='#00e676', linestyle=':', linewidth=1.3, label=f'VAH: {format_price(vah_price)}')
        ax_main.axhline(val_price, color='#ff9100', linestyle=':', linewidth=1.3, label=f'VAL: {format_price(val_price)}')
        ax_main.set_title(f"Volume Profile: {symbol} ({timeframe})", fontsize=13, color='white', pad=10)
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
        caption = f"📊 <b>تحلیل والیوم پروفایل (Volume Profile)</b>\n\n🔹 <b>نماد:</b> <code>{symbol}</code>\n⏱ <b>تایم‌فریم:</b> <code>{timeframe}</code>\n\n📍 <b>POC:</b> <code>{format_price(poc_price)}</code>\n🔺 <b>VAH:</b> <code>{format_price(vah_price)}</code>\n🔻 <b>VAL:</b> <code>{format_price(val_price)}</code>"
        return buf, caption
    except Exception as e:
        logging.error(f"VP error: {e}")
        return None, f"❌ خطا: {str(e)}"

async def analyze_market(symbol: str, timeframe: str = '15m'):
    try:
        limit = 350
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not ohlcv or len(ohlcv) < 220: return "❌ داده کافی دریافت نشد."

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        delta = df['close'].diff()
        gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
        avg_gain, avg_loss = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean(), loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + (avg_gain / (avg_loss + 1e-9))))

        ema12, ema26 = df['close'].ewm(span=12, adjust=False).mean(), df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']

        tr1, tr2, tr3 = df['high'] - df['low'], (df['high'] - df['close'].shift(1)).abs(), (df['low'] - df['close'].shift(1)).abs()
        df['atr'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(window=14).mean()

        c, prev_c = df.iloc[-2], df.iloc[-3]
        current_live_price = df['close'].iloc[-1]
        
        # بخش ساده شده برای جلوگیری از ارور
        atr_val = c['atr'] if not pd.isna(c['atr']) else current_live_price * 0.015
        
        direction = "🟢 صعودی / 🔴 نزولی (تحلیل در حال اجرا...)"
        report = f"📊 <b>گزارش {symbol} ({timeframe})</b>\n\n💵 <b>Entry:</b> <code>{format_price(current_live_price)}</code>\n🛑 <b>Stop:</b> <code>{format_price(current_live_price - atr_val)}</code>"
        return report
    except Exception as e:
        return f"❌ خطا: {str(e)}"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("سلام! ارز را انتخاب کنید:", reply_markup=get_symbols_keyboard())

@dp.callback_query(lambda c: c.data.startswith('sym:'))
async def process_symbol_select(callback_query: types.CallbackQuery):
    symbol = callback_query.data.split('sym:')[1]
    await callback_query.message.edit_text(f"ارز: <b>{symbol}</b>\nانتخاب کنید:", reply_markup=get_timeframe_keyboard(symbol))
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('tf:'))
async def process_timeframe_select(callback_query: types.CallbackQuery):
    await callback_query.answer()
    data_str = callback_query.data[3:]
    symbol, tf = data_str.rsplit(':', 1)
    await callback_query.message.edit_text("⏳ تحلیل...")
    result = await analyze_market(symbol, tf)
    await callback_query.message.edit_text(result, reply_markup=get_timeframe_keyboard(symbol))

@dp.callback_query(lambda c: c.data.startswith('vp:'))
async def process_volume_profile(callback_query: types.CallbackQuery):
    await callback_query.answer("در حال پردازش...")
    data_str = callback_query.data[3:]
    symbol, tf = data_str.rsplit(':', 1)
    buf, caption = await generate_volume_profile_chart(symbol, tf)
    if buf:
        await callback_query.message.answer_photo(photo=BufferedInputFile(buf.getvalue(), filename="vp.png"), caption=caption)
    else:
        await callback_query.message.answer(caption)

@dp.callback_query(lambda c: c.data == 'back_to_symbols')
async def process_back(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("انتخاب ارز:", reply_markup=get_symbols_keyboard())

async def main():
    if not BOT_TOKEN:
        logging.error("BOT_TOKEN ست نشده است!")
        return
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    logging.info("Starting Bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
