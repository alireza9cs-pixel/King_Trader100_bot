import asyncio
import os
import ccxt.async_support as ccxt
import numpy as np
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN یافت نشد!")

bot = Bot(token=GAPGPTMASKTOKENett8xggb0mbX0X
dp = Dispatcher()

exchange = ccxt.kcex({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def calculate_poc(df, bins=25):
    p_min, p_max = df['low'].min(), df['high'].max()
    if p_min == p_max:
        return p_max
    bins_arr = np.linspace(p_min, p_max, bins)
    vol_prof = np.zeros(bins - 1)
    for _, row in df.iterrows():
        idx = np.digitize((row['high'] + row['low']) / 2, bins_arr) - 1
        if 0 <= idx < len(vol_prof):
            vol_prof[idx] += row['volume']
    m_idx = np.argmax(vol_prof)
    return (bins_arr[m_idx] + bins_arr[m_idx + 1]) / 2

def analyze_market(df: pd.DataFrame):
    if df is None or len(df) < 40:
        return None
    df = df.copy()
    df['rsi'] = calculate_rsi(df['close'])
    curr, prev, prior = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    poc = calculate_poc(df.tail(35))
    
    # ستاپ لانگ (ICT FVG + MSS + Volume POC + RSI)
    if prev['low'] > prior['high'] and curr['close'] > prev['high'] and curr['rsi'] < 45 and curr['close'] >= poc * 0.996:
        entry = curr['close']
        sl = min(prev['low'], prior['low']) * 0.998
        risk = entry - sl
        if risk > 0:
            return {
                "type": "LONG 🟢",
                "entry": entry,
                "sl": sl,
                "tp1": entry + (risk * 2.0),
                "tp2": entry + (risk * 3.5),
                "rr": "1:2 - 1:3.5",
                "poc": poc,
                "reason": "ICT Bullish FVG + MSS + Volume POC Support"
            }
            
    # ستاپ شورت (ICT Bearish FVG + MSS + POC Rejection + RSI)
    if prev['high'] < prior['low'] and curr['close'] < prev['low'] and curr['rsi'] > 55 and curr['close'] <= poc * 1.004:
        entry = curr['close']
        sl = max(prev['high'], prior['high']) * 1.002
        risk = sl - entry
        if risk > 0:
            return {
                "type": "SHORT 🔴",
                "entry": entry,
                "sl": sl,
                "tp1": entry - (risk * 2.0),
                "tp2": entry - (risk * 3.5),
                "rr": "1:2 - 1:3.5",
                "poc": poc,
                "reason": "ICT Bearish FVG + MSS + POC Rejection"
            }
    return None

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("🚀 ربات هوشمند KCEX Futures روی سرور فعال شد!\nاسکن ۲۴ ساعته مارکت در حال انجام است.")

async def scanner_task():
    while True:
        try:
            await exchange.load_markets()
            markets = [s for s, m in exchange.markets.items() if m.get('swap') and m.get('quote') == 'USDT' and m.get('active')]
            
            for symbol in markets[:30]:
                try:
                    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe='15m', limit=60)
                    if not ohlcv:
                        continue
                    df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                    sig = analyze_market(df)
                    
                    if sig and ADMIN_ID != 0:
                        text = (
                            f"🔔 **سیگنال تایید شده {sig['type']}**\n\n"
                            f"💎 **ارز:** `{symbol}`\n"
                            f"⏱ **تایم فریم:** 15m\n"
                            f"🎯 **Entry Price:** `{sig['entry']:.5f}`\n"
                            f"🛑 **Stop Loss:** `{sig['sl']:.5f}`\n"
                            f"🥇 **Target 1:** `{sig['tp1']:.5f}`\n"
                            f"🥈 **Target 2:** `{sig['tp2']:.5f}`\n"
                            f"⚖️ **R:R:** {sig['rr']}\n"
                            f"📊 **Volume POC:** `{sig['poc']:.5f}`\n"
                            f"🧠 **تحلیل:** {sig['reason']}"
                        )
                        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
                except Exception:
                    pass
                await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Scanner err: {e}")
        await asyncio.sleep(20)

async def main():
    asyncio.create_task(scanner_task())
    print("Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
