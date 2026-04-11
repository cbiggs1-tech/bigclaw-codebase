#!/usr/bin/env python3
"""Technical analysis for BigClaw. Uses yfinance + ta library.

Usage:
    python3 technical_analysis.py TSLA
    python3 technical_analysis.py TSLA NVDA AAPL --period 3mo
    python3 technical_analysis.py TSLA --json
"""

import argparse
import json
import sys
import yfinance as yf
import pandas as pd

def analyze_ticker(ticker, period="3mo"):
    """Run technical analysis on a ticker."""
    try:
        import ta
    except ImportError:
        return {"ticker": ticker, "error": "ta library not installed. pip install ta"}

    ticker = ticker.upper()
    stock = yf.Ticker(ticker)
    df = stock.history(period=period)

    if df.empty:
        return {"ticker": ticker, "error": "No data returned"}

    # Current price
    current = float(df['Close'].iloc[-1])
    prev_close = float(df['Close'].iloc[-2]) if len(df) > 1 else current
    day_change = ((current - prev_close) / prev_close) * 100

    # Moving averages
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()

    sma20 = float(df['SMA_20'].iloc[-1]) if not pd.isna(df['SMA_20'].iloc[-1]) else None
    sma50 = float(df['SMA_50'].iloc[-1]) if not pd.isna(df['SMA_50'].iloc[-1]) else None

    # RSI
    rsi_series = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
    rsi = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None

    # MACD
    macd_ind = ta.trend.MACD(df['Close'])
    macd_line = float(macd_ind.macd().iloc[-1]) if not pd.isna(macd_ind.macd().iloc[-1]) else None
    macd_signal = float(macd_ind.macd_signal().iloc[-1]) if not pd.isna(macd_ind.macd_signal().iloc[-1]) else None
    macd_hist = float(macd_ind.macd_diff().iloc[-1]) if not pd.isna(macd_ind.macd_diff().iloc[-1]) else None

    # Bollinger Bands
    bb = ta.volatility.BollingerBands(df['Close'], window=20, window_dev=2)
    bb_upper = float(bb.bollinger_hband().iloc[-1]) if not pd.isna(bb.bollinger_hband().iloc[-1]) else None
    bb_lower = float(bb.bollinger_lband().iloc[-1]) if not pd.isna(bb.bollinger_lband().iloc[-1]) else None
    bb_mid = float(bb.bollinger_mavg().iloc[-1]) if not pd.isna(bb.bollinger_mavg().iloc[-1]) else None

    # Average Volume
    avg_vol = float(df['Volume'].tail(20).mean())
    last_vol = float(df['Volume'].iloc[-1])
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 0

    # Support/Resistance (simple: recent lows/highs)
    recent = df.tail(20)
    support = float(recent['Low'].min())
    resistance = float(recent['High'].max())

    # 52-week high/low
    week52 = stock.history(period="1y")
    high_52w = float(week52['High'].max()) if not week52.empty else None
    low_52w = float(week52['Low'].min()) if not week52.empty else None

    # Generate signals
    signals = []
    if rsi is not None:
        if rsi > 70:
            signals.append("⚠️ RSI overbought (>70)")
        elif rsi < 30:
            signals.append("📈 RSI oversold (<30)")

    if sma20 and sma50:
        if sma20 > sma50 and current > sma20:
            signals.append("📈 Above SMA20 & SMA50 (bullish)")
        elif sma20 < sma50 and current < sma20:
            signals.append("📉 Below SMA20 & SMA50 (bearish)")

    if macd_hist is not None:
        if macd_hist > 0 and macd_line > macd_signal:
            signals.append("📈 MACD bullish crossover")
        elif macd_hist < 0 and macd_line < macd_signal:
            signals.append("📉 MACD bearish crossover")

    if bb_upper and bb_lower:
        if current > bb_upper:
            signals.append("⚠️ Above upper Bollinger Band")
        elif current < bb_lower:
            signals.append("📈 Below lower Bollinger Band (potential bounce)")

    if vol_ratio > 1.5:
        signals.append(f"🔊 High volume ({vol_ratio:.1f}x average)")
    elif vol_ratio < 0.5:
        signals.append(f"🔇 Low volume ({vol_ratio:.1f}x average)")

    # Overall bias
    bullish_count = sum(1 for s in signals if "📈" in s)
    bearish_count = sum(1 for s in signals if "📉" in s or "⚠️" in s)
    if bullish_count > bearish_count:
        bias = "Bullish"
    elif bearish_count > bullish_count:
        bias = "Bearish"
    else:
        bias = "Neutral"

    return {
        "ticker": ticker,
        "price": round(current, 2),
        "day_change_pct": round(day_change, 2),
        "sma_20": round(sma20, 2) if sma20 else None,
        "sma_50": round(sma50, 2) if sma50 else None,
        "rsi": round(rsi, 1) if rsi else None,
        "macd": {"line": round(macd_line, 3) if macd_line else None,
                 "signal": round(macd_signal, 3) if macd_signal else None,
                 "histogram": round(macd_hist, 3) if macd_hist else None},
        "bollinger": {"upper": round(bb_upper, 2) if bb_upper else None,
                      "middle": round(bb_mid, 2) if bb_mid else None,
                      "lower": round(bb_lower, 2) if bb_lower else None},
        "volume": {"last": int(last_vol), "avg_20d": int(avg_vol), "ratio": round(vol_ratio, 2)},
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "52w_high": round(high_52w, 2) if high_52w else None,
        "52w_low": round(low_52w, 2) if low_52w else None,
        "signals": signals,
        "bias": bias,
    }


def format_output(results):
    lines = []
    for r in results:
        if "error" in r:
            lines.append(f"❌ {r['ticker']}: {r['error']}")
            continue

        emoji = "🟢" if r["bias"] == "Bullish" else "🔴" if r["bias"] == "Bearish" else "⚪"
        lines.append(f"{emoji} **{r['ticker']}** — ${r['price']} ({r['day_change_pct']:+.2f}%) | Bias: {r['bias']}")
        lines.append(f"   RSI: {r['rsi']} | SMA20: ${r['sma_20']} | SMA50: ${r['sma_50']}")
        lines.append(f"   MACD: {r['macd']['histogram']:+.3f} | BB: ${r['bollinger']['lower']}-${r['bollinger']['upper']}")
        lines.append(f"   Vol: {r['volume']['ratio']:.1f}x avg | Support: ${r['support']} | Resistance: ${r['resistance']}")
        lines.append(f"   52W: ${r['52w_low']} — ${r['52w_high']}")

        if r["signals"]:
            lines.append(f"   Signals:")
            for s in r["signals"]:
                lines.append(f"     {s}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Technical analysis")
    parser.add_argument("tickers", nargs="+", help="Ticker symbols")
    parser.add_argument("--period", default="3mo", help="Data period (1mo, 3mo, 6mo, 1y)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = []
    for t in args.tickers:
        print(f"Analyzing {t.upper()}...", file=sys.stderr)
        results.append(analyze_ticker(t, args.period))

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_output(results))
