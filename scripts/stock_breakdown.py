#!/usr/bin/env python3
"""Comprehensive stock breakdown script combining yfinance, finvizfinance, edgartools, and ta."""

import argparse
import json
import sys
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe(fn, default=None):
    """Run fn(), return default on any exception."""
    try:
        return fn()
    except Exception:
        return default

def fmt_num(val, prefix="", suffix="", decimals=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    if isinstance(val, (int, float)):
        abs_val = abs(val)
        if abs_val >= 1e12:
            return f"{prefix}{val/1e12:,.{decimals}f}T{suffix}"
        if abs_val >= 1e9:
            return f"{prefix}{val/1e9:,.{decimals}f}B{suffix}"
        if abs_val >= 1e6:
            return f"{prefix}{val/1e6:,.{decimals}f}M{suffix}"
        return f"{prefix}{val:,.{decimals}f}{suffix}"
    return str(val)

def pct(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val:+.2f}%"

def stale_flag(days=30):
    """Return a warning string if data may be stale."""
    return f" ⚠️ (may be >30 days old)"

# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

def get_finviz_data(ticker):
    """Fetch finvizfinance data. Returns dict with keys: fundamentals, insider, ratings."""
    result = {"fundamentals": {}, "insider": None, "ratings": None, "error": None}
    try:
        from finvizfinance.quote import finvizfinance as fvf
        stock = fvf(ticker)
        result["fundamentals"] = stock.ticker_fundament()
        result["insider"] = safe(lambda: stock.ticker_inside_trader())
        result["ratings"] = safe(lambda: stock.ticker_outer_ratings())
    except Exception as e:
        result["error"] = str(e)
    return result

def get_edgar_data(ticker):
    """Fetch EDGAR data for insider trades."""
    result = {"insider_trades": [], "error": None}
    try:
        from edgar import set_identity, Company
        set_identity("BigClaw fixit@grandpapa.net")
        co = Company(ticker)
        filings = co.get_filings(form="4").latest(5)
        trades = []
        for f in filings:
            trades.append({
                "date": str(f.filing_date),
                "form": f.form,
                "description": getattr(f, "description", "Form 4 filing"),
            })
        result["insider_trades"] = trades
    except Exception as e:
        result["error"] = str(e)
    return result

def compute_technicals(hist):
    """Compute technical indicators from price history DataFrame."""
    result = {}
    if hist is None or hist.empty or len(hist) < 20:
        return result
    close = hist["Close"].squeeze() if isinstance(hist["Close"], pd.DataFrame) else hist["Close"]
    close = close.dropna()
    if len(close) < 20:
        return result

    # RSI(14)
    try:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        result["rsi"] = round(float(rsi.iloc[-1]), 2)
    except Exception:
        pass

    # MACD
    try:
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal = macd_line.ewm(span=9).mean()
        result["macd"] = round(float(macd_line.iloc[-1]), 4)
        result["macd_signal"] = round(float(signal.iloc[-1]), 4)
        result["macd_hist"] = round(float(macd_line.iloc[-1] - signal.iloc[-1]), 4)
    except Exception:
        pass

    # Bollinger Bands
    try:
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = sma20 + 2 * std20
        lower = sma20 - 2 * std20
        last_price = float(close.iloc[-1])
        result["bb_upper"] = round(float(upper.iloc[-1]), 2)
        result["bb_lower"] = round(float(lower.iloc[-1]), 2)
        result["bb_mid"] = round(float(sma20.iloc[-1]), 2)
        bb_range = float(upper.iloc[-1]) - float(lower.iloc[-1])
        if bb_range > 0:
            result["bb_position"] = round((last_price - float(lower.iloc[-1])) / bb_range * 100, 1)
    except Exception:
        pass

    # SMAs
    try:
        if len(close) >= 50:
            result["sma50"] = round(float(close.rolling(50).mean().iloc[-1]), 2)
        if len(close) >= 200:
            result["sma200"] = round(float(close.rolling(200).mean().iloc[-1]), 2)
        if "sma50" in result and "sma200" in result:
            if result["sma50"] > result["sma200"]:
                # Check if cross happened recently (50 SMA crossed above 200 SMA)
                sma50_series = close.rolling(50).mean()
                sma200_series = close.rolling(200).mean()
                diff = sma50_series - sma200_series
                diff_clean = diff.dropna()
                if len(diff_clean) > 1 and diff_clean.iloc[-1] > 0 and diff_clean.iloc[-2] <= 0:
                    result["cross"] = "🟢 Golden Cross (recent)"
                else:
                    result["cross"] = "🟢 50 SMA > 200 SMA (bullish)"
            else:
                result["cross"] = "🔴 50 SMA < 200 SMA (bearish)"
    except Exception:
        pass

    # Support / Resistance (simple pivot-based)
    try:
        recent = close.tail(20)
        result["support"] = round(float(recent.min()), 2)
        result["resistance"] = round(float(recent.max()), 2)
    except Exception:
        pass

    return result

def compute_performance(ticker_obj, info):
    """Compute price performance over various periods and vs S&P 500."""
    result = {}
    try:
        hist = ticker_obj.history(period="1y")
        if hist.empty:
            return result
        close = hist["Close"].squeeze() if isinstance(hist["Close"], pd.DataFrame) else hist["Close"]
        current = float(close.iloc[-1])
        result["current_price"] = current

        spy = yf.Ticker("SPY").history(period="1y")
        spy_close = spy["Close"].squeeze() if isinstance(spy["Close"], pd.DataFrame) else spy["Close"]

        periods = {"1mo": 21, "3mo": 63, "6mo": 126, "1yr": 252}
        now = datetime.now()
        # YTD
        ytd_start = datetime(now.year, 1, 1)
        ytd_data = close[close.index >= pd.Timestamp(ytd_start, tz=close.index.tz)]
        if len(ytd_data) > 1:
            result["YTD"] = round((current / float(ytd_data.iloc[0]) - 1) * 100, 2)
            spy_ytd = spy_close[spy_close.index >= pd.Timestamp(ytd_start, tz=spy_close.index.tz)]
            if len(spy_ytd) > 1:
                result["YTD_spy"] = round((float(spy_close.iloc[-1]) / float(spy_ytd.iloc[0]) - 1) * 100, 2)

        for label, days in periods.items():
            if len(close) > days:
                chg = (current / float(close.iloc[-days]) - 1) * 100
                result[label] = round(chg, 2)
                if len(spy_close) > days:
                    spy_chg = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-days]) - 1) * 100
                    result[f"{label}_spy"] = round(spy_chg, 2)
    except Exception:
        pass

    try:
        result["52w_high"] = info.get("fiftyTwoWeekHigh")
        result["52w_low"] = info.get("fiftyTwoWeekLow")
    except Exception:
        pass

    return result

# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(ticker):
    """Build full report dict for a single ticker."""
    report = {"ticker": ticker, "sections": {}, "errors": []}

    # --- yfinance ---
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        report["errors"].append(f"yfinance failed: {e}")
        info = {}
        t = None

    # --- finviz ---
    fv = get_finviz_data(ticker)
    if fv["error"]:
        report["errors"].append(f"finviz: {fv['error']}")
    fv_fund = fv["fundamentals"] or {}

    # --- EDGAR ---
    edgar = get_edgar_data(ticker)
    if edgar["error"]:
        report["errors"].append(f"EDGAR: {edgar['error']}")

    # ====== STEP 1 — Company Overview ======
    overview = {}
    overview["name"] = info.get("longName", ticker)
    overview["summary"] = info.get("longBusinessSummary", "N/A")
    overview["sector"] = info.get("sector", "N/A")
    overview["industry"] = info.get("industry", "N/A")
    overview["employees"] = info.get("fullTimeEmployees")
    report["sections"]["overview"] = overview

    # ====== STEP 2 — Key Financials ======
    fin = {}
    fin["revenue_ttm"] = info.get("totalRevenue")
    fin["net_income"] = info.get("netIncomeToCommon")
    fin["eps_trailing"] = info.get("trailingEps")
    fin["eps_forward"] = info.get("forwardEps")
    fin["pe"] = info.get("trailingPE")
    fin["forward_pe"] = info.get("forwardPE")
    fin["ps"] = info.get("priceToSalesTrailing12Months")
    fin["peg"] = info.get("pegRatio")
    fin["debt_to_equity"] = info.get("debtToEquity")
    fin["total_debt"] = info.get("totalDebt")
    fin["free_cash_flow"] = info.get("freeCashflow")
    fin["revenue_growth"] = info.get("revenueGrowth")
    fin["earnings_growth"] = info.get("earningsGrowth")
    # Quarterly revenue from financials
    try:
        q = t.quarterly_income_stmt
        if q is not None and not q.empty:
            if "Total Revenue" in q.index:
                rev_row = q.loc["Total Revenue"]
                fin["recent_q_revenue"] = float(rev_row.iloc[0])
                fin["recent_q_date"] = str(rev_row.index[0].date()) if hasattr(rev_row.index[0], 'date') else str(rev_row.index[0])
                if len(rev_row) >= 5:
                    fin["yoy_q_revenue"] = float(rev_row.iloc[4])
            if "Net Income" in q.index:
                ni_row = q.loc["Net Income"]
                fin["recent_q_net_income"] = float(ni_row.iloc[0])
                if len(ni_row) >= 5:
                    fin["yoy_q_net_income"] = float(ni_row.iloc[4])
    except Exception:
        pass
    # finviz supplements
    fin["finviz_pe"] = fv_fund.get("P/E")
    fin["finviz_fwd_pe"] = fv_fund.get("Forward P/E")
    fin["finviz_peg"] = fv_fund.get("PEG")
    report["sections"]["financials"] = fin

    # ====== STEP 3 — Stock Performance ======
    perf = compute_performance(t, info) if t else {}
    report["sections"]["performance"] = perf

    # ====== STEP 4 — Wall Street Consensus ======
    ws = {}
    ws["analyst_count"] = info.get("numberOfAnalystOpinions")
    ws["recommendation"] = info.get("recommendationKey")
    ws["target_mean"] = info.get("targetMeanPrice")
    ws["target_high"] = info.get("targetHighPrice")
    ws["target_low"] = info.get("targetLowPrice")
    ws["target_median"] = info.get("targetMedianPrice")
    # Buy/Hold/Sell from recommendations
    try:
        recs = t.recommendations
        if recs is not None and not recs.empty:
            row = recs.iloc[0]
            ws["strong_buy"] = int(row.get("strongBuy", 0))
            ws["buy"] = int(row.get("buy", 0))
            ws["hold"] = int(row.get("hold", 0))
            ws["sell"] = int(row.get("sell", 0))
            ws["strong_sell"] = int(row.get("strongSell", 0))
    except Exception:
        pass
    # finviz ratings
    if fv["ratings"] is not None:
        try:
            ws["finviz_ratings"] = fv["ratings"].head(5).to_dict("records")
        except Exception:
            pass
    report["sections"]["wall_street"] = ws

    # ====== STEP 5 — Institutional & Insider Activity ======
    inst = {}
    try:
        holders = t.institutional_holders
        if holders is not None and not holders.empty:
            inst["top_holders"] = holders.head(5).to_dict("records")
    except Exception:
        pass
    # Insider trades from EDGAR
    inst["edgar_insider"] = edgar.get("insider_trades", [])
    # Insider from finviz
    if fv["insider"] is not None:
        try:
            inst["finviz_insider"] = fv["insider"].head(5).to_dict("records")
        except Exception:
            pass
    report["sections"]["institutional"] = inst

    # ====== STEP 6 — Technical Snapshot ======
    try:
        hist = t.history(period="1y")
    except Exception:
        hist = pd.DataFrame()
    tech = compute_technicals(hist)
    report["sections"]["technicals"] = tech

    return report

# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------

def render_markdown(report):
    lines = []
    s = report["sections"]
    ticker = report["ticker"]
    ov = s.get("overview", {})
    fin = s.get("financials", {})
    perf = s.get("performance", {})
    ws = s.get("wall_street", {})
    inst = s.get("institutional", {})
    tech = s.get("technicals", {})

    lines.append(f"# 📊 {ov.get('name', ticker)} ({ticker}) — Full Breakdown")
    lines.append(f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} CST*\n")

    if report["errors"]:
        lines.append("**⚠️ Data Source Warnings:**")
        for e in report["errors"]:
            lines.append(f"- {e}")
        lines.append("")

    # --- Step 1 ---
    lines.append("## Step 1 — Company Overview")
    lines.append(f"**Sector:** {ov.get('sector', 'N/A')} | **Industry:** {ov.get('industry', 'N/A')}")
    if ov.get("employees"):
        lines.append(f"**Employees:** {ov['employees']:,}")
    summary = ov.get("summary", "N/A")
    if summary and summary != "N/A":
        # Truncate to ~500 chars
        if len(summary) > 500:
            summary = summary[:497] + "..."
        lines.append(f"\n{summary}")
    lines.append(f"\n*Source: yfinance*\n")

    # --- Step 2 ---
    lines.append("## Step 2 — Key Financials")
    lines.append(f"| Metric | Value | Source |")
    lines.append(f"|--------|-------|--------|")
    lines.append(f"| Revenue (TTM) | {fmt_num(fin.get('revenue_ttm'), prefix='$')} | yfinance |")
    if fin.get("recent_q_revenue"):
        q_label = fin.get("recent_q_date", "latest Q")
        lines.append(f"| Revenue (Q ending {q_label}) | {fmt_num(fin['recent_q_revenue'], prefix='$')} | yfinance |")
    lines.append(f"| Net Income | {fmt_num(fin.get('net_income'), prefix='$')} | yfinance |")
    lines.append(f"| EPS (TTM) | {fmt_num(fin.get('eps_trailing'), prefix='$')} | yfinance |")
    lines.append(f"| EPS (Forward) | {fmt_num(fin.get('eps_forward'), prefix='$')} | yfinance |")
    lines.append(f"| P/E | {fmt_num(fin.get('pe'))} | yfinance |")
    lines.append(f"| Forward P/E | {fmt_num(fin.get('forward_pe'))} | yfinance |")
    lines.append(f"| P/S | {fmt_num(fin.get('ps'))} | yfinance |")
    lines.append(f"| PEG Ratio | {fmt_num(fin.get('peg'))} | yfinance |")
    lines.append(f"| Debt/Equity | {fmt_num(fin.get('debt_to_equity'))} | yfinance |")
    lines.append(f"| Total Debt | {fmt_num(fin.get('total_debt'), prefix='$')} | yfinance |")
    lines.append(f"| Free Cash Flow (TTM) | {fmt_num(fin.get('free_cash_flow'), prefix='$')} | yfinance |")

    # YoY
    if fin.get("recent_q_revenue") and fin.get("yoy_q_revenue"):
        yoy_chg = (fin["recent_q_revenue"] / fin["yoy_q_revenue"] - 1) * 100
        lines.append(f"| Revenue YoY (Q) | {pct(yoy_chg)} | yfinance |")
    if fin.get("revenue_growth") is not None:
        lines.append(f"| Revenue Growth | {pct(fin['revenue_growth']*100)} | yfinance |")
    if fin.get("earnings_growth") is not None:
        lines.append(f"| Earnings Growth | {pct(fin['earnings_growth']*100)} | yfinance |")
    lines.append("")

    # --- Step 3 ---
    lines.append("## Step 3 — Stock Performance")
    if perf.get("current_price"):
        lines.append(f"**Current Price:** ${perf['current_price']:.2f}\n")
    lines.append("| Period | Stock | S&P 500 | vs S&P |")
    lines.append("|--------|-------|---------|--------|")
    for label in ["1mo", "3mo", "6mo", "1yr", "YTD"]:
        stock_chg = perf.get(label)
        spy_chg = perf.get(f"{label}_spy")
        diff = None
        if stock_chg is not None and spy_chg is not None:
            diff = stock_chg - spy_chg
        lines.append(f"| {label} | {pct(stock_chg)} | {pct(spy_chg)} | {pct(diff)} |")
    if perf.get("52w_high") or perf.get("52w_low"):
        lines.append(f"\n**52-Week Range:** ${perf.get('52w_low', 'N/A')} — ${perf.get('52w_high', 'N/A')}")
    lines.append(f"\n*Source: yfinance*\n")

    # --- Step 4 ---
    lines.append("## Step 4 — Wall Street Consensus")
    lines.append(f"- **Analyst Count:** {ws.get('analyst_count', 'N/A')}")
    lines.append(f"- **Consensus:** {ws.get('recommendation', 'N/A')}")
    if any(ws.get(k) is not None for k in ["strong_buy", "buy", "hold", "sell", "strong_sell"]):
        lines.append(f"- **Strong Buy:** {ws.get('strong_buy', 0)} | **Buy:** {ws.get('buy', 0)} | **Hold:** {ws.get('hold', 0)} | **Sell:** {ws.get('sell', 0)} | **Strong Sell:** {ws.get('strong_sell', 0)}")
    lines.append(f"- **Price Target — Mean:** ${ws.get('target_mean', 'N/A')} | Median: ${ws.get('target_median', 'N/A')} | High: ${ws.get('target_high', 'N/A')} | Low: ${ws.get('target_low', 'N/A')}")
    if ws.get("finviz_ratings") and len(ws["finviz_ratings"]) > 0:
        r = ws["finviz_ratings"][0]
        lines.append(f"- **Latest Rating:** {r.get('Outer','N/A')} — {r.get('Rating','N/A')} ({r.get('Status','')}, {r.get('Date','')}) {r.get('Price','')}")
    if ws.get("finviz_ratings"):
        lines.append(f"\n**Recent Analyst Actions** *(finviz)*:")
        for r in ws["finviz_ratings"][:5]:
            lines.append(f"  - {r.get('Date','')} | {r.get('Status','')} | {r.get('Outer','')} | {r.get('Rating','')} | {r.get('Price','')}")
    lines.append(f"\n*Sources: yfinance, finviz*\n")

    # --- Step 5 ---
    lines.append("## Step 5 — Institutional & Insider Activity")
    holders = inst.get("top_holders", [])
    if holders:
        lines.append("**Top 5 Institutional Holders** *(yfinance)*:")
        lines.append("| Holder | Shares | Value | Date Reported |")
        lines.append("|--------|--------|-------|---------------|")
        for h in holders[:5]:
            name = h.get("Holder", "N/A")
            shares = fmt_num(h.get("Shares", 0))
            value = fmt_num(h.get("Value", 0), prefix="$")
            date_rep = h.get("Date Reported", "N/A")
            if hasattr(date_rep, "strftime"):
                date_rep = date_rep.strftime("%Y-%m-%d")
            lines.append(f"| {name} | {shares} | {value} | {date_rep} |")
        lines.append("")
    else:
        lines.append("*No institutional holder data available.*\n")

    edgar_trades = inst.get("edgar_insider", [])
    if edgar_trades:
        lines.append("**Recent Insider Filings (Form 4)** *(EDGAR)*:")
        for tr in edgar_trades[:5]:
            lines.append(f"  - {tr.get('date','')} | {tr.get('description','')}")
        lines.append("")

    fv_insider = inst.get("finviz_insider", [])
    if fv_insider:
        lines.append("**Insider Trades** *(finviz)*:")
        for tr in fv_insider[:5]:
            lines.append(f"  - {tr.get('Date','')} | {tr.get('Insider Trading','')} ({tr.get('Relationship','')}) | {tr.get('Transaction','')} | {tr.get('Value ($)','N/A')}")
        lines.append("")

    # --- Step 6 ---
    lines.append("## Step 6 — Technical Snapshot")
    if not tech:
        lines.append("*Insufficient price history for technical analysis.*\n")
    else:
        lines.append(f"| Indicator | Value |")
        lines.append(f"|-----------|-------|")
        if "rsi" in tech:
            rsi_val = tech["rsi"]
            rsi_label = "Overbought" if rsi_val > 70 else ("Oversold" if rsi_val < 30 else "Neutral")
            lines.append(f"| RSI(14) | {rsi_val} ({rsi_label}) |")
        if "macd" in tech:
            macd_signal = "Bullish" if tech["macd_hist"] > 0 else "Bearish"
            lines.append(f"| MACD | {tech['macd']} (Signal: {tech['macd_signal']}, Hist: {tech['macd_hist']} — {macd_signal}) |")
        if "bb_position" in tech:
            lines.append(f"| Bollinger Band Position | {tech['bb_position']}% (Lower: {tech['bb_lower']}, Mid: {tech['bb_mid']}, Upper: {tech['bb_upper']}) |")
        if "sma50" in tech:
            lines.append(f"| 50-Day SMA | {tech['sma50']} |")
        if "sma200" in tech:
            lines.append(f"| 200-Day SMA | {tech['sma200']} |")
        if "cross" in tech:
            lines.append(f"| SMA Cross | {tech['cross']} |")
        if "support" in tech:
            lines.append(f"| Support (20d) | ${tech['support']} |")
        if "resistance" in tech:
            lines.append(f"| Resistance (20d) | ${tech['resistance']} |")
        lines.append(f"\n*Source: calculated from yfinance price history using standard TA formulas*\n")

    lines.append("---\n")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Deep Dive Sections (Steps 7-12)
# ---------------------------------------------------------------------------

# Common peer mappings for major stocks
PEER_MAP = {
    "AAPL": ["MSFT", "GOOGL", "DELL"],
    "MSFT": ["AAPL", "GOOGL", "ORCL"],
    "GOOGL": ["META", "MSFT", "AMZN"],
    "GOOG": ["META", "MSFT", "AMZN"],
    "AMZN": ["MSFT", "GOOGL", "WMT"],
    "META": ["GOOGL", "SNAP", "PINS"],
    "TSLA": ["F", "GM", "RIVN"],
    "NVDA": ["AMD", "INTC", "AVGO"],
    "AMD": ["NVDA", "INTC", "QCOM"],
    "INTC": ["AMD", "NVDA", "TXN"],
    "NFLX": ["DIS", "WBD", "PARA"],
    "JPM": ["BAC", "GS", "MS"],
    "BAC": ["JPM", "WFC", "C"],
    "V": ["MA", "PYPL", "SQ"],
    "MA": ["V", "PYPL", "AXP"],
    "JNJ": ["PFE", "MRK", "ABT"],
    "UNH": ["CI", "ELV", "HUM"],
    "XOM": ["CVX", "COP", "SLB"],
    "WMT": ["TGT", "COST", "AMZN"],
    "DIS": ["NFLX", "WBD", "PARA"],
    "CRM": ["NOW", "WDAY", "SAP"],
    "AVGO": ["NVDA", "QCOM", "TXN"],
}


def _safe_get(df, row_names, col_idx=0):
    """Try multiple row name variants to get a value from a DataFrame."""
    if df is None or df.empty:
        return None
    for name in (row_names if isinstance(row_names, list) else [row_names]):
        if name in df.index:
            try:
                val = df.loc[name].iloc[col_idx]
                if pd.notna(val):
                    return float(val)
            except Exception:
                pass
    return None


def _safe_get_row(df, row_names, n_cols=4):
    """Get up to n_cols values for a row (trying multiple name variants)."""
    if df is None or df.empty:
        return []
    for name in (row_names if isinstance(row_names, list) else [row_names]):
        if name in df.index:
            try:
                row = df.loc[name]
                vals = []
                for i in range(min(n_cols, len(row))):
                    v = row.iloc[i]
                    vals.append(float(v) if pd.notna(v) else None)
                return vals
            except Exception:
                return []
    return []


def build_deep_sections(report, ticker):
    """Add Steps 7-12 to the report dict."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        report["errors"].append(f"Deep dive yfinance init failed: {e}")
        return

    q_fin = safe(lambda: t.quarterly_income_stmt)
    q_bs = safe(lambda: t.quarterly_balance_sheet)
    q_cf = safe(lambda: t.quarterly_cashflow)

    # ====== STEP 7 — Income Statement Deep Dive ======
    step7 = {"quarters": [], "margins": [], "rd_pct": [], "trend": "N/A"}
    try:
        if q_fin is not None and not q_fin.empty:
            n = min(4, q_fin.shape[1])
            rev_row = _safe_get_row(q_fin, ["Total Revenue"], n)
            cogs_row = _safe_get_row(q_fin, ["Cost Of Revenue", "Cost Of Goods Sold"], n)
            op_income_row = _safe_get_row(q_fin, ["Operating Income", "EBIT"], n)
            net_income_row = _safe_get_row(q_fin, ["Net Income", "Net Income Common Stockholders"], n)
            rd_row = _safe_get_row(q_fin, ["Research And Development", "Research Development"], n)

            # Also get YoY data (quarters 4-7 if available)
            n_full = min(8, q_fin.shape[1])
            rev_row_full = _safe_get_row(q_fin, ["Total Revenue"], n_full)

            col_dates = []
            for i in range(n):
                try:
                    col_dates.append(str(q_fin.columns[i].date()))
                except Exception:
                    col_dates.append(str(q_fin.columns[i]))

            margins_list = []
            for i in range(n):
                rev = rev_row[i] if i < len(rev_row) else None
                cogs = cogs_row[i] if i < len(cogs_row) else None
                op_inc = op_income_row[i] if i < len(op_income_row) else None
                ni = net_income_row[i] if i < len(net_income_row) else None
                rd = rd_row[i] if i < len(rd_row) else None

                gross_margin = ((rev - cogs) / rev * 100) if rev and cogs and rev != 0 else None
                op_margin = (op_inc / rev * 100) if rev and op_inc and rev != 0 else None
                net_margin = (ni / rev * 100) if rev and ni and rev != 0 else None
                rd_pct = (rd / rev * 100) if rev and rd and rev != 0 else None

                # YoY growth
                yoy_rev_growth = None
                if i + 4 < len(rev_row_full) and rev_row_full[i + 4] and rev_row_full[i + 4] != 0 and rev:
                    yoy_rev_growth = (rev / rev_row_full[i + 4] - 1) * 100

                q_data = {
                    "date": col_dates[i] if i < len(col_dates) else "N/A",
                    "revenue": rev,
                    "yoy_growth": yoy_rev_growth,
                    "gross_margin": round(gross_margin, 2) if gross_margin is not None else None,
                    "op_margin": round(op_margin, 2) if op_margin is not None else None,
                    "net_margin": round(net_margin, 2) if net_margin is not None else None,
                    "rd_pct": round(rd_pct, 2) if rd_pct is not None else None,
                }
                margins_list.append(q_data)

            step7["quarters"] = margins_list

            # Trend analysis on gross margin
            gm_vals = [m["gross_margin"] for m in margins_list if m["gross_margin"] is not None]
            if len(gm_vals) >= 2:
                diff = gm_vals[0] - gm_vals[-1]  # most recent - oldest in window
                if abs(diff) < 1.0:
                    step7["trend"] = f"Stable (gross margin Δ {diff:+.1f}pp over {len(gm_vals)}Q)"
                elif diff > 0:
                    step7["trend"] = f"Expanding (gross margin +{diff:.1f}pp over {len(gm_vals)}Q)"
                else:
                    step7["trend"] = f"Compressing (gross margin {diff:.1f}pp over {len(gm_vals)}Q)"
    except Exception as e:
        report["errors"].append(f"Step 7: {e}")
    report["sections"]["income_deep"] = step7

    # ====== STEP 8 — Balance Sheet Health ======
    step8 = {}
    try:
        if q_bs is not None and not q_bs.empty:
            step8["total_assets"] = _safe_get(q_bs, ["Total Assets"])
            step8["total_liabilities"] = _safe_get(q_bs, ["Total Liabilities Net Minority Interest", "Total Liab"])
            step8["current_assets"] = _safe_get(q_bs, ["Current Assets"])
            step8["current_liabilities"] = _safe_get(q_bs, ["Current Liabilities"])
            step8["cash"] = _safe_get(q_bs, ["Cash And Cash Equivalents", "Cash"])
            step8["short_term_investments"] = _safe_get(q_bs, ["Other Short Term Investments", "Short Term Investments"])
            step8["short_term_debt"] = _safe_get(q_bs, ["Current Debt", "Short Long Term Debt", "Current Debt And Capital Lease Obligation"])
            step8["long_term_debt"] = _safe_get(q_bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"])
            step8["goodwill"] = _safe_get(q_bs, ["Goodwill"])
            step8["inventory"] = _safe_get(q_bs, ["Inventory"])
            step8["accounts_receivable"] = _safe_get(q_bs, ["Net Receivables", "Receivables", "Accounts Receivable"])

            # Computed metrics
            ca = step8.get("current_assets")
            cl = step8.get("current_liabilities")
            if ca and cl and cl != 0:
                step8["current_ratio"] = round(ca / cl, 2)
                inv = step8.get("inventory") or 0
                step8["quick_ratio"] = round((ca - inv) / cl, 2)

            cash_total = (step8.get("cash") or 0) + (step8.get("short_term_investments") or 0)
            step8["cash_and_investments"] = cash_total if cash_total > 0 else None

            st_debt = step8.get("short_term_debt") or 0
            lt_debt = step8.get("long_term_debt") or 0
            step8["total_debt"] = st_debt + lt_debt if (st_debt + lt_debt) > 0 else None

            ta = step8.get("total_assets")
            gw = step8.get("goodwill")
            if ta and gw and ta != 0:
                step8["goodwill_pct"] = round(gw / ta * 100, 2)
            else:
                step8["goodwill_pct"] = None
    except Exception as e:
        report["errors"].append(f"Step 8: {e}")
    report["sections"]["balance_sheet"] = step8

    # ====== STEP 9 — Cash Flow Reality Check ======
    step9 = {}
    try:
        if q_cf is not None and not q_cf.empty:
            n = min(4, q_cf.shape[1])
            ocf_row = _safe_get_row(q_cf, ["Operating Cash Flow", "Total Cash From Operating Activities"], n)
            capex_row = _safe_get_row(q_cf, ["Capital Expenditure", "Capital Expenditures"], n)
            buyback_row = _safe_get_row(q_cf, ["Repurchase Of Capital Stock", "Common Stock Repurchased"], n)
            div_row = _safe_get_row(q_cf, ["Common Stock Dividend Paid", "Cash Dividends Paid", "Payment Of Dividends And Other Cash Distributions"], n)
            acq_row = _safe_get_row(q_cf, ["Acquisitions And Disposals", "Net Business Purchase And Sale"], n)
            debt_repay_row = _safe_get_row(q_cf, ["Repayment Of Debt", "Long Term Debt Payments"], n)

            # TTM sums
            ocf_ttm = sum(v for v in ocf_row if v is not None) if ocf_row else None
            capex_ttm = sum(v for v in capex_row if v is not None) if capex_row else None

            step9["ocf_ttm"] = ocf_ttm
            step9["capex_ttm"] = capex_ttm
            if ocf_ttm is not None and capex_ttm is not None:
                step9["fcf_ttm"] = ocf_ttm + capex_ttm  # capex is negative
            rev_ttm = info.get("totalRevenue")
            if step9.get("fcf_ttm") and rev_ttm and rev_ttm != 0:
                step9["fcf_margin"] = round(step9["fcf_ttm"] / rev_ttm * 100, 2)

            # Cash allocation TTM
            step9["buybacks_ttm"] = sum(v for v in buyback_row if v is not None) if buyback_row else None
            step9["dividends_ttm"] = sum(v for v in div_row if v is not None) if div_row else None
            step9["acquisitions_ttm"] = sum(v for v in acq_row if v is not None) if acq_row else None
            step9["debt_repayment_ttm"] = sum(v for v in debt_repay_row if v is not None) if debt_repay_row else None

            # YoY OCF growth (need 8 quarters)
            n_full = min(8, q_cf.shape[1])
            ocf_full = _safe_get_row(q_cf, ["Operating Cash Flow", "Total Cash From Operating Activities"], n_full)
            if len(ocf_full) >= 8:
                ocf_current = sum(v for v in ocf_full[:4] if v is not None)
                ocf_prior = sum(v for v in ocf_full[4:8] if v is not None)
                if ocf_prior and ocf_prior != 0:
                    step9["ocf_yoy_growth"] = round((ocf_current / ocf_prior - 1) * 100, 2)
    except Exception as e:
        report["errors"].append(f"Step 9: {e}")
    report["sections"]["cash_flow"] = step9

    # ====== STEP 10 — Red Flags ======
    step10 = []
    try:
        rev_growth = info.get("revenueGrowth")
        rev_growth_pct = rev_growth * 100 if rev_growth is not None else None

        # Flag 1: Revenue growing but OCF declining
        ocf_yoy = step9.get("ocf_yoy_growth")
        if rev_growth_pct is not None and ocf_yoy is not None:
            is_red = rev_growth_pct > 0 and ocf_yoy < 0
            step10.append({
                "check": "Revenue growing but operating cash flow declining?",
                "flag": "⚠️" if is_red else "✅",
                "detail": f"Revenue growth: {rev_growth_pct:+.1f}%, OCF growth: {ocf_yoy:+.1f}%"
            })
        else:
            step10.append({"check": "Revenue growing but operating cash flow declining?", "flag": "❓", "detail": "Insufficient data"})

        # Flag 2: Debt growing faster than revenue
        # Compare current vs prior year balance sheet debt
        if q_bs is not None and not q_bs.empty and q_bs.shape[1] >= 5:
            debt_now_st = _safe_get(q_bs, ["Current Debt", "Current Debt And Capital Lease Obligation"], 0) or 0
            debt_now_lt = _safe_get(q_bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 0) or 0
            debt_now = debt_now_st + debt_now_lt
            debt_prev_st = _safe_get(q_bs, ["Current Debt", "Current Debt And Capital Lease Obligation"], 4) or 0
            debt_prev_lt = _safe_get(q_bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 4) or 0
            debt_prev = debt_prev_st + debt_prev_lt
            if debt_prev > 0:
                debt_growth = (debt_now / debt_prev - 1) * 100
                is_red = rev_growth_pct is not None and debt_growth > rev_growth_pct and debt_growth > 5
                step10.append({
                    "check": "Debt growing faster than revenue?",
                    "flag": "⚠️" if is_red else "✅",
                    "detail": f"Debt growth: {debt_growth:+.1f}%, Revenue growth: {pct(rev_growth_pct)}"
                })
            else:
                step10.append({"check": "Debt growing faster than revenue?", "flag": "✅", "detail": "No prior debt or zero base"})
        else:
            step10.append({"check": "Debt growing faster than revenue?", "flag": "❓", "detail": "Insufficient balance sheet data"})

        # Flag 3: AR growing faster than revenue
        if q_bs is not None and not q_bs.empty and q_bs.shape[1] >= 5:
            ar_now = _safe_get(q_bs, ["Net Receivables", "Receivables", "Accounts Receivable"], 0)
            ar_prev = _safe_get(q_bs, ["Net Receivables", "Receivables", "Accounts Receivable"], 4)
            if ar_now and ar_prev and ar_prev != 0:
                ar_growth = (ar_now / ar_prev - 1) * 100
                is_red = rev_growth_pct is not None and ar_growth > rev_growth_pct + 5
                step10.append({
                    "check": "Accounts receivable growing faster than revenue?",
                    "flag": "⚠️" if is_red else "✅",
                    "detail": f"AR growth: {ar_growth:+.1f}%, Revenue growth: {pct(rev_growth_pct)}"
                })
            else:
                step10.append({"check": "Accounts receivable growing faster than revenue?", "flag": "✅", "detail": "AR data not available or zero base"})
        else:
            step10.append({"check": "Accounts receivable growing faster than revenue?", "flag": "❓", "detail": "Insufficient data"})

        # Flag 4: Inventory buildup without revenue growth
        if q_bs is not None and not q_bs.empty and q_bs.shape[1] >= 5:
            inv_now = _safe_get(q_bs, ["Inventory"], 0)
            inv_prev = _safe_get(q_bs, ["Inventory"], 4)
            if inv_now and inv_prev and inv_prev != 0:
                inv_growth = (inv_now / inv_prev - 1) * 100
                is_red = (rev_growth_pct is not None and inv_growth > rev_growth_pct + 10) or (rev_growth_pct is not None and rev_growth_pct < 0 and inv_growth > 5)
                step10.append({
                    "check": "Inventory buildup without revenue growth?",
                    "flag": "⚠️" if is_red else "✅",
                    "detail": f"Inventory growth: {inv_growth:+.1f}%, Revenue growth: {pct(rev_growth_pct)}"
                })
            else:
                step10.append({"check": "Inventory buildup without revenue growth?", "flag": "✅", "detail": "No inventory tracked or zero base"})
        else:
            step10.append({"check": "Inventory buildup without revenue growth?", "flag": "❓", "detail": "Insufficient data"})

        # Flag 5: Frequent one-time charges (GAAP NI vs operating income divergence)
        if q_fin is not None and not q_fin.empty:
            n = min(4, q_fin.shape[1])
            op_row = _safe_get_row(q_fin, ["Operating Income", "EBIT"], n)
            ni_row = _safe_get_row(q_fin, ["Net Income", "Net Income Common Stockholders"], n)
            if op_row and ni_row and len(op_row) == len(ni_row):
                diffs = []
                for i in range(len(op_row)):
                    if op_row[i] and ni_row[i] and op_row[i] != 0:
                        diffs.append(abs((ni_row[i] - op_row[i]) / op_row[i] * 100))
                avg_diff = sum(diffs) / len(diffs) if diffs else 0
                is_red = avg_diff > 25
                step10.append({
                    "check": "Frequent large one-time charges?",
                    "flag": "⚠️" if is_red else "✅",
                    "detail": f"Avg gap between operating income and net income: {avg_diff:.1f}% of operating income"
                })
            else:
                step10.append({"check": "Frequent large one-time charges?", "flag": "❓", "detail": "Insufficient data"})
        else:
            step10.append({"check": "Frequent large one-time charges?", "flag": "❓", "detail": "Insufficient data"})
    except Exception as e:
        report["errors"].append(f"Step 10: {e}")
    report["sections"]["red_flags"] = step10

    # ====== STEP 11 — Green Flags ======
    step11 = []
    try:
        # Green 1: Improving margins QoQ
        quarters = step7.get("quarters", [])
        if len(quarters) >= 2:
            gm_improving = quarters[0].get("gross_margin") is not None and quarters[1].get("gross_margin") is not None and quarters[0]["gross_margin"] > quarters[1]["gross_margin"]
            om_improving = quarters[0].get("op_margin") is not None and quarters[1].get("op_margin") is not None and quarters[0]["op_margin"] > quarters[1]["op_margin"]
            any_improving = gm_improving or om_improving
            details = []
            if quarters[0].get("gross_margin") is not None and quarters[1].get("gross_margin") is not None:
                details.append(f"Gross margin: {quarters[0]['gross_margin']}% → {quarters[1]['gross_margin']}% (prev Q)")
            if quarters[0].get("op_margin") is not None and quarters[1].get("op_margin") is not None:
                details.append(f"Op margin: {quarters[0]['op_margin']}% → {quarters[1]['op_margin']}% (prev Q)")
            step11.append({
                "check": "Improving margins quarter over quarter",
                "flag": "🟢" if any_improving else "—",
                "detail": "; ".join(details) if details else "N/A"
            })
        # Green 2: Growing FCF
        fcf = step9.get("fcf_ttm")
        ocf_yoy = step9.get("ocf_yoy_growth")
        if fcf is not None:
            is_green = fcf > 0 and (ocf_yoy is None or ocf_yoy > 0)
            step11.append({
                "check": "Growing free cash flow",
                "flag": "🟢" if is_green else "—",
                "detail": f"FCF TTM: {fmt_num(fcf, prefix='$')}, OCF YoY: {pct(ocf_yoy)}"
            })
        # Green 3: Decreasing debt or increasing cash
        bs = report["sections"].get("balance_sheet", {})
        cash = bs.get("cash_and_investments")
        debt = bs.get("total_debt")
        # Compare with prior year if possible
        if q_bs is not None and not q_bs.empty and q_bs.shape[1] >= 5:
            cash_now = (bs.get("cash") or 0) + (bs.get("short_term_investments") or 0)
            cash_prev_val = (_safe_get(q_bs, ["Cash And Cash Equivalents", "Cash"], 4) or 0) + (_safe_get(q_bs, ["Other Short Term Investments", "Short Term Investments"], 4) or 0)
            debt_now_st = _safe_get(q_bs, ["Current Debt", "Current Debt And Capital Lease Obligation"], 0) or 0
            debt_now_lt = _safe_get(q_bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 0) or 0
            debt_prev_st = _safe_get(q_bs, ["Current Debt", "Current Debt And Capital Lease Obligation"], 4) or 0
            debt_prev_lt = _safe_get(q_bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 4) or 0
            debt_decreased = (debt_now_st + debt_now_lt) < (debt_prev_st + debt_prev_lt)
            cash_increased = cash_now > cash_prev_val
            is_green = debt_decreased or cash_increased
            step11.append({
                "check": "Decreasing debt or increasing cash reserves",
                "flag": "🟢" if is_green else "—",
                "detail": f"Debt: {fmt_num(debt_now_st + debt_now_lt, prefix='$')} (was {fmt_num(debt_prev_st + debt_prev_lt, prefix='$')}), Cash: {fmt_num(cash_now, prefix='$')} (was {fmt_num(cash_prev_val, prefix='$')})"
            })
        # Green 4: Consistent earnings quality
        if q_fin is not None and not q_fin.empty:
            n = min(4, q_fin.shape[1])
            op_row = _safe_get_row(q_fin, ["Operating Income", "EBIT"], n)
            ni_row = _safe_get_row(q_fin, ["Net Income", "Net Income Common Stockholders"], n)
            if op_row and ni_row:
                tracking = all(
                    abs(ni_row[i] - op_row[i]) / abs(op_row[i]) < 0.3
                    for i in range(min(len(op_row), len(ni_row)))
                    if op_row[i] and ni_row[i] and op_row[i] != 0
                )
                step11.append({
                    "check": "Consistent earnings quality (operating income tracking net income)",
                    "flag": "🟢" if tracking else "—",
                    "detail": f"Op income and net income within 30% across recent quarters"
                })
    except Exception as e:
        report["errors"].append(f"Step 11: {e}")
    report["sections"]["green_flags"] = step11

    # ====== STEP 12 — Peer Comparison ======
    step12 = {"peers": [], "comparison": []}
    try:
        sector = info.get("sector", "")
        industry = info.get("industry", "")

        # Get peers
        peers = PEER_MAP.get(ticker, [])
        if not peers:
            # Try finvizfinance screener
            try:
                from finvizfinance.screener.overview import Overview
                fscreen = Overview()
                filters = {}
                if industry:
                    filters["Industry"] = industry
                if filters:
                    fscreen.set_filter(filters_dict=filters)
                    df = fscreen.screener_view()
                    if df is not None and not df.empty:
                        candidates = df[df["Ticker"] != ticker].head(3)["Ticker"].tolist()
                        peers = candidates[:3]
            except Exception:
                pass

        if not peers:
            peers = []

        # Validate peers exist on yfinance
        valid_peers = []
        for p in peers[:5]:
            try:
                pt = yf.Ticker(p)
                pi = pt.info or {}
                if pi.get("regularMarketPrice") or pi.get("currentPrice"):
                    valid_peers.append(p)
                    if len(valid_peers) >= 3:
                        break
            except Exception:
                continue

        step12["peers"] = valid_peers

        # Build comparison table
        all_tickers = [ticker] + valid_peers
        for tk in all_tickers:
            try:
                tk_obj = yf.Ticker(tk)
                tk_info = tk_obj.info or {}
                row = {"ticker": tk}
                row["pe"] = tk_info.get("trailingPE")
                row["ps"] = tk_info.get("priceToSalesTrailing12Months")
                row["gross_margin"] = round(tk_info.get("grossMargins", 0) * 100, 2) if tk_info.get("grossMargins") else None
                row["op_margin"] = round(tk_info.get("operatingMargins", 0) * 100, 2) if tk_info.get("operatingMargins") else None
                row["net_margin"] = round(tk_info.get("profitMargins", 0) * 100, 2) if tk_info.get("profitMargins") else None
                row["de"] = tk_info.get("debtToEquity")
                row["rev_growth"] = round(tk_info.get("revenueGrowth", 0) * 100, 2) if tk_info.get("revenueGrowth") else None
                # FCF yield
                fcf_val = tk_info.get("freeCashflow")
                mcap = tk_info.get("marketCap")
                row["fcf_yield"] = round(fcf_val / mcap * 100, 2) if fcf_val and mcap and mcap != 0 else None
                row["source"] = "yfinance .info"
                step12["comparison"].append(row)
            except Exception:
                step12["comparison"].append({"ticker": tk, "error": "Failed to fetch"})
    except Exception as e:
        report["errors"].append(f"Step 12: {e}")
    report["sections"]["peer_comparison"] = step12


def render_deep_markdown(report):
    """Render Steps 7-12 as markdown."""
    lines = []
    s = report["sections"]

    # --- Step 7 ---
    lines.append("## Step 7 — Income Statement Deep Dive")
    step7 = s.get("income_deep", {})
    quarters = step7.get("quarters", [])
    if quarters:
        lines.append("| Quarter | Revenue | YoY Growth | Gross Margin | Op Margin | Net Margin | R&D % Rev |")
        lines.append("|---------|---------|------------|-------------|-----------|------------|-----------|")
        for q in quarters:
            lines.append(f"| {q['date']} | {fmt_num(q.get('revenue'), prefix='$')} | {pct(q.get('yoy_growth'))} | {pct(q.get('gross_margin')) if q.get('gross_margin') is not None else 'N/A'} | {pct(q.get('op_margin')) if q.get('op_margin') is not None else 'N/A'} | {pct(q.get('net_margin')) if q.get('net_margin') is not None else 'N/A'} | {fmt_num(q.get('rd_pct'), suffix='%') if q.get('rd_pct') is not None else 'N/A'} |")
        lines.append(f"\n**Trend:** {step7.get('trend', 'N/A')}")
    else:
        lines.append("*Quarterly income statement data not available.*")
    lines.append(f"\n*Source: yfinance quarterly_income_stmt*\n")

    # --- Step 8 ---
    lines.append("## Step 8 — Balance Sheet Health")
    bs = s.get("balance_sheet", {})
    if bs:
        lines.append(f"| Metric | Value | Source |")
        lines.append(f"|--------|-------|--------|")
        lines.append(f"| Total Assets | {fmt_num(bs.get('total_assets'), prefix='$')} | yfinance |")
        lines.append(f"| Total Liabilities | {fmt_num(bs.get('total_liabilities'), prefix='$')} | yfinance |")
        lines.append(f"| Current Ratio | {fmt_num(bs.get('current_ratio'))} | calculated |")
        lines.append(f"| Quick Ratio | {fmt_num(bs.get('quick_ratio'))} | calculated |")
        lines.append(f"| Cash & Short-Term Investments | {fmt_num(bs.get('cash_and_investments'), prefix='$')} | yfinance |")
        lines.append(f"| Total Debt (ST + LT) | {fmt_num(bs.get('total_debt'), prefix='$')} | yfinance |")
        gw_pct = bs.get("goodwill_pct")
        gw_flag = " ⚠️ >30%!" if gw_pct and gw_pct > 30 else ""
        lines.append(f"| Goodwill % of Total Assets | {fmt_num(gw_pct, suffix='%') if gw_pct is not None else 'N/A'}{gw_flag} | calculated |")
    else:
        lines.append("*Balance sheet data not available.*")
    lines.append(f"\n*Source: yfinance quarterly_balance_sheet*\n")

    # --- Step 9 ---
    lines.append("## Step 9 — Cash Flow Reality Check")
    cf = s.get("cash_flow", {})
    if cf:
        lines.append(f"| Metric | Value | Source |")
        lines.append(f"|--------|-------|--------|")
        lines.append(f"| Operating Cash Flow (TTM) | {fmt_num(cf.get('ocf_ttm'), prefix='$')} | yfinance |")
        lines.append(f"| CapEx (TTM) | {fmt_num(cf.get('capex_ttm'), prefix='$')} | yfinance |")
        lines.append(f"| Free Cash Flow (TTM) | {fmt_num(cf.get('fcf_ttm'), prefix='$')} | calculated |")
        lines.append(f"| FCF Margin | {fmt_num(cf.get('fcf_margin'), suffix='%') if cf.get('fcf_margin') is not None else 'N/A'} | calculated |")
        lines.append(f"| OCF YoY Growth | {pct(cf.get('ocf_yoy_growth'))} | calculated |")
        lines.append("")
        lines.append("**Cash Allocation (TTM):**")
        lines.append(f"- Buybacks: {fmt_num(cf.get('buybacks_ttm'), prefix='$')}")
        lines.append(f"- Dividends: {fmt_num(cf.get('dividends_ttm'), prefix='$')}")
        lines.append(f"- Acquisitions: {fmt_num(cf.get('acquisitions_ttm'), prefix='$')}")
        lines.append(f"- Debt Repayment: {fmt_num(cf.get('debt_repayment_ttm'), prefix='$')}")
    else:
        lines.append("*Cash flow data not available.*")
    lines.append(f"\n*Source: yfinance quarterly_cashflow*\n")

    # --- Step 10 ---
    lines.append("## Step 10 — Red Flags")
    red_flags = s.get("red_flags", [])
    if red_flags:
        for rf in red_flags:
            lines.append(f"- {rf['flag']} **{rf['check']}**")
            lines.append(f"  {rf['detail']}")
    else:
        lines.append("*No red flag checks could be performed.*")
    lines.append("")

    # --- Step 11 ---
    lines.append("## Step 11 — Green Flags")
    green_flags = s.get("green_flags", [])
    if green_flags:
        for gf in green_flags:
            lines.append(f"- {gf['flag']} **{gf['check']}**")
            lines.append(f"  {gf['detail']}")
    else:
        lines.append("*No green flag checks could be performed.*")
    lines.append("")

    # --- Step 12 ---
    lines.append("## Step 12 — Peer Comparison")
    step12 = s.get("peer_comparison", {})
    comp = step12.get("comparison", [])
    if comp:
        lines.append(f"**Peers:** {', '.join(step12.get('peers', []))}")
        lines.append("")
        lines.append("| Ticker | P/E | P/S | Gross Margin | Op Margin | Net Margin | D/E | FCF Yield | Rev Growth |")
        lines.append("|--------|-----|-----|-------------|-----------|------------|-----|-----------|------------|")
        for row in comp:
            if row.get("error"):
                lines.append(f"| {row['ticker']} | Error | | | | | | | |")
                continue
            lines.append(f"| {row['ticker']} | {fmt_num(row.get('pe'))} | {fmt_num(row.get('ps'))} | {fmt_num(row.get('gross_margin'), suffix='%') if row.get('gross_margin') is not None else 'N/A'} | {fmt_num(row.get('op_margin'), suffix='%') if row.get('op_margin') is not None else 'N/A'} | {fmt_num(row.get('net_margin'), suffix='%') if row.get('net_margin') is not None else 'N/A'} | {fmt_num(row.get('de'))} | {fmt_num(row.get('fcf_yield'), suffix='%') if row.get('fcf_yield') is not None else 'N/A'} | {fmt_num(row.get('rev_growth'), suffix='%') if row.get('rev_growth') is not None else 'N/A'} |")
        lines.append(f"\n*Source: yfinance .info for all metrics*")
    else:
        lines.append("*No peer comparison data available.*")
    lines.append("\n---\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON serializer helper
# ---------------------------------------------------------------------------

def make_serializable(obj):
    """Recursively convert numpy/pandas/Timestamp types to JSON-safe types."""
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_serializable(i) for i in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj) if not np.isnan(obj) else None
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return str(obj)
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    return obj

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# --compare: Comparison sections
# ---------------------------------------------------------------------------

def _get_compare_metrics(ticker_str):
    """Fetch comparison metrics for a single ticker."""
    try:
        t = yf.Ticker(ticker_str)
        info = t.info or {}
    except Exception:
        return {"ticker": ticker_str, "error": "Failed to fetch"}

    mcap = info.get("marketCap")
    fcf = info.get("freeCashflow")
    fcf_yield = round(fcf / mcap * 100, 2) if fcf and mcap and mcap != 0 else None

    return {
        "ticker": ticker_str,
        "name": info.get("longName", ticker_str),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "country": info.get("country", "N/A"),
        "market_cap": mcap,
        "pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "ps": info.get("priceToSalesTrailing12Months"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "peg": info.get("pegRatio"),
        "gross_margin": round(info["grossMargins"] * 100, 2) if info.get("grossMargins") else None,
        "op_margin": round(info["operatingMargins"] * 100, 2) if info.get("operatingMargins") else None,
        "net_margin": round(info["profitMargins"] * 100, 2) if info.get("profitMargins") else None,
        "de": info.get("debtToEquity"),
        "fcf_yield": fcf_yield,
        "rev_growth": round(info["revenueGrowth"] * 100, 2) if info.get("revenueGrowth") else None,
        "dividend_yield": round(info["dividendYield"] * 100, 2) if info.get("dividendYield") else None,
        "current_ratio": info.get("currentRatio"),
        "total_cash": info.get("totalCash"),
        "total_debt": info.get("totalDebt"),
        "earnings_growth": round(info["earningsGrowth"] * 100, 2) if info.get("earningsGrowth") else None,
    }


def build_compare_sections(report, primary_ticker, compare_tickers):
    """Build comparison data for --compare flag."""
    all_tickers = [primary_ticker] + [t.upper().strip() for t in compare_tickers]
    metrics = []
    for tk in all_tickers:
        print(f"  Fetching comparison data for {tk}...", file=sys.stderr)
        metrics.append(_get_compare_metrics(tk))
    report["sections"]["compare"] = {"tickers": all_tickers, "metrics": metrics}


def _best_worst(metrics, key, lower_is_better=True):
    """Find best/worst ticker for a metric. Returns (best_ticker, worst_ticker)."""
    valid = [(m["ticker"], m.get(key)) for m in metrics if m.get(key) is not None and not m.get("error")]
    if not valid:
        return None, None
    sorted_v = sorted(valid, key=lambda x: x[1])
    if lower_is_better:
        return sorted_v[0][0], sorted_v[-1][0]
    else:
        return sorted_v[-1][0], sorted_v[0][0]


def render_compare_markdown(report):
    """Render --compare sections as markdown."""
    lines = []
    comp = report["sections"].get("compare", {})
    metrics = comp.get("metrics", [])
    if not metrics:
        return ""

    valid = [m for m in metrics if not m.get("error")]

    lines.append("## 📊 Comparison Table")
    lines.append("")

    # Header
    cols = ["Ticker", "Market Cap", "P/E", "Fwd P/E", "P/S", "EV/EBITDA", "PEG",
            "Gross Margin", "Op Margin", "Net Margin", "D/E", "FCF Yield", "Rev Growth YoY", "Div Yield"]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("|" + "|".join(["---"] * len(cols)) + "|")

    for m in metrics:
        if m.get("error"):
            lines.append(f"| {m['ticker']} | " + " | ".join(["Error"] * (len(cols) - 1)) + " |")
            continue
        lines.append(f"| {m['ticker']} | {fmt_num(m.get('market_cap'), prefix='$')} | {fmt_num(m.get('pe'))} | {fmt_num(m.get('forward_pe'))} | {fmt_num(m.get('ps'))} | {fmt_num(m.get('ev_ebitda'))} | {fmt_num(m.get('peg'))} | {fmt_num(m.get('gross_margin'), suffix='%') if m.get('gross_margin') is not None else 'N/A'} | {fmt_num(m.get('op_margin'), suffix='%') if m.get('op_margin') is not None else 'N/A'} | {fmt_num(m.get('net_margin'), suffix='%') if m.get('net_margin') is not None else 'N/A'} | {fmt_num(m.get('de'))} | {fmt_num(m.get('fcf_yield'), suffix='%') if m.get('fcf_yield') is not None else 'N/A'} | {fmt_num(m.get('rev_growth'), suffix='%') if m.get('rev_growth') is not None else 'N/A'} | {fmt_num(m.get('dividend_yield'), suffix='%') if m.get('dividend_yield') is not None else 'N/A'} |")

    # Best/worst notes
    notes = []
    checks = [
        ("pe", "P/E", True), ("forward_pe", "Fwd P/E", True), ("ps", "P/S", True),
        ("ev_ebitda", "EV/EBITDA", True), ("peg", "PEG", True),
        ("gross_margin", "Gross Margin", False), ("op_margin", "Op Margin", False),
        ("net_margin", "Net Margin", False), ("de", "Debt/Equity", True),
        ("fcf_yield", "FCF Yield", False), ("rev_growth", "Revenue Growth", False),
    ]
    for key, label, lower_better in checks:
        best, worst = _best_worst(valid, key, lower_better)
        if best:
            notes.append(f"- **{label}:** Best = {best}" + (f", Worst = {worst}" if worst and worst != best else ""))
    if notes:
        lines.append("\n**Best/Worst by Category:**")
        lines.extend(notes)
    lines.append("")

    # Competitive Positioning
    lines.append("## 🏆 Competitive Positioning")
    for m in valid:
        lines.append(f"- **{m['ticker']}** — {m.get('sector', 'N/A')} / {m.get('industry', 'N/A')}")

    # Market cap ranking
    ranked = sorted([m for m in valid if m.get("market_cap")], key=lambda x: x["market_cap"], reverse=True)
    if ranked:
        lines.append("\n**Market Cap Ranking:**")
        for i, m in enumerate(ranked, 1):
            lines.append(f"  {i}. {m['ticker']} — {fmt_num(m['market_cap'], prefix='$')}")

    # Strongest margins
    best_gm, _ = _best_worst(valid, "gross_margin", False)
    best_val, _ = _best_worst(valid, "pe", True)
    best_grow, _ = _best_worst(valid, "rev_growth", False)
    notes2 = []
    if best_gm:
        notes2.append(f"**Strongest Margins:** {best_gm}")
    if best_val:
        notes2.append(f"**Cheapest Valuation (P/E):** {best_val}")
    if best_grow:
        notes2.append(f"**Best Growth:** {best_grow}")
    if notes2:
        lines.append("\n" + " | ".join(notes2))
    lines.append("")

    # The Ranking
    lines.append("## 🥇 The Ranking")

    # Best Value: lowest PEG, or P/S relative to growth
    def _value_score(m):
        peg = m.get("peg")
        ps = m.get("ps")
        grow = m.get("rev_growth") or 0
        if peg and peg > 0:
            return peg
        if ps and grow > 0:
            return ps / (grow / 100)
        return 9999
    value_sorted = sorted([m for m in valid if not m.get("error")], key=_value_score)
    if value_sorted:
        v = value_sorted[0]
        lines.append(f"- **Best Value:** {v['ticker']} (PEG: {fmt_num(v.get('peg'))}, P/S: {fmt_num(v.get('ps'))}, Rev Growth: {fmt_num(v.get('rev_growth'), suffix='%') if v.get('rev_growth') is not None else 'N/A'})")

    # Highest Growth
    growth_sorted = sorted([m for m in valid if m.get("rev_growth") is not None], key=lambda x: x["rev_growth"], reverse=True)
    if growth_sorted:
        g = growth_sorted[0]
        lines.append(f"- **Highest Growth:** {g['ticker']} (Revenue Growth: {fmt_num(g['rev_growth'], suffix='%')}, Earnings Growth: {fmt_num(g.get('earnings_growth'), suffix='%') if g.get('earnings_growth') is not None else 'N/A'})")

    # Safest Pick: lowest D/E, highest current ratio, most cash
    def _safety_score(m):
        de = m.get("de") or 0
        cr = m.get("current_ratio") or 1
        cash = m.get("total_cash") or 0
        debt = m.get("total_debt") or 1
        return de / max(cr, 0.01) - (cash / max(debt, 1)) * 10
    safety_sorted = sorted([m for m in valid], key=_safety_score)
    if safety_sorted:
        s = safety_sorted[0]
        lines.append(f"- **Safest Pick:** {s['ticker']} (D/E: {fmt_num(s.get('de'))}, Current Ratio: {fmt_num(s.get('current_ratio'))}, Cash: {fmt_num(s.get('total_cash'), prefix='$')})")

    # Overall Winner: weighted
    def _overall_score(m):
        score = 0
        # Value (lower PEG better)
        peg = m.get("peg")
        if peg and 0 < peg < 50:
            score += max(0, 5 - peg) * 2
        # Growth
        rg = m.get("rev_growth") or 0
        score += min(rg / 5, 10)
        # Margins
        gm = m.get("gross_margin") or 0
        score += gm / 10
        # Safety (low D/E)
        de = m.get("de") or 0
        if de < 100:
            score += (100 - de) / 20
        # FCF yield
        fcfy = m.get("fcf_yield") or 0
        score += fcfy
        return score
    overall_sorted = sorted(valid, key=_overall_score, reverse=True)
    if overall_sorted:
        w = overall_sorted[0]
        lines.append(f"- **Overall Winner: {w['ticker']}** — Best weighted combination of valuation, growth, margins, and balance sheet strength")

    lines.append("\n---\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# --risk: Risk report sections
# ---------------------------------------------------------------------------

def build_risk_section(report, ticker):
    """Build risk analysis data for --risk flag."""
    risk = {}
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        report["errors"].append(f"Risk: yfinance init failed: {e}")
        report["sections"]["risk"] = {"error": str(e)}
        return

    q_fin = safe(lambda: t.quarterly_income_stmt)
    q_bs = safe(lambda: t.quarterly_balance_sheet)
    q_cf = safe(lambda: t.quarterly_cashflow)

    # --- Financial Health Risks ---
    fhr = {}

    # Debt growth vs revenue growth
    rev_growth = info.get("revenueGrowth")
    rev_growth_pct = rev_growth * 100 if rev_growth is not None else None
    fhr["rev_growth_pct"] = rev_growth_pct

    if q_bs is not None and not q_bs.empty and q_bs.shape[1] >= 5:
        debt_now = (_safe_get(q_bs, ["Current Debt", "Current Debt And Capital Lease Obligation"], 0) or 0) + \
                   (_safe_get(q_bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 0) or 0)
        debt_prev = (_safe_get(q_bs, ["Current Debt", "Current Debt And Capital Lease Obligation"], 4) or 0) + \
                    (_safe_get(q_bs, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"], 4) or 0)
        if debt_prev > 0:
            fhr["debt_growth_pct"] = round((debt_now / debt_prev - 1) * 100, 2)
        else:
            fhr["debt_growth_pct"] = 0 if debt_now == 0 else None
        fhr["debt_faster_than_rev"] = (fhr.get("debt_growth_pct") is not None and rev_growth_pct is not None
                                        and fhr["debt_growth_pct"] > rev_growth_pct)
    else:
        fhr["debt_growth_pct"] = None
        fhr["debt_faster_than_rev"] = None

    # FCF trend (last 4 quarters)
    if q_cf is not None and not q_cf.empty:
        n = min(4, q_cf.shape[1])
        ocf_row = _safe_get_row(q_cf, ["Operating Cash Flow", "Total Cash From Operating Activities"], n)
        capex_row = _safe_get_row(q_cf, ["Capital Expenditure", "Capital Expenditures"], n)
        fcf_quarters = []
        for i in range(min(len(ocf_row), len(capex_row))):
            if ocf_row[i] is not None and capex_row[i] is not None:
                fcf_quarters.append(ocf_row[i] + capex_row[i])
            else:
                fcf_quarters.append(None)
        fhr["fcf_quarters"] = fcf_quarters
        valid_fcf = [f for f in fcf_quarters if f is not None]
        fhr["fcf_declining"] = len(valid_fcf) >= 2 and valid_fcf[0] < valid_fcf[-1]  # most recent < oldest = declining
    else:
        fhr["fcf_quarters"] = []
        fhr["fcf_declining"] = None

    # Margin trend
    if q_fin is not None and not q_fin.empty:
        n = min(4, q_fin.shape[1])
        rev_row = _safe_get_row(q_fin, ["Total Revenue"], n)
        op_row = _safe_get_row(q_fin, ["Operating Income", "EBIT"], n)
        margins = []
        for i in range(min(len(rev_row), len(op_row))):
            if rev_row[i] and op_row[i] and rev_row[i] != 0:
                margins.append(round(op_row[i] / rev_row[i] * 100, 2))
        fhr["op_margins_trend"] = margins
        fhr["margin_compressing"] = len(margins) >= 2 and margins[0] < margins[-1]
    else:
        fhr["op_margins_trend"] = []
        fhr["margin_compressing"] = None

    # Cash runway
    cash = info.get("totalCash") or 0
    fcf_ttm = info.get("freeCashflow")
    if fcf_ttm is not None and fcf_ttm < 0:
        quarterly_burn = abs(fcf_ttm) / 4
        fhr["cash_runway_months"] = round(cash / quarterly_burn, 1) if quarterly_burn > 0 else None
    else:
        fhr["cash_runway_months"] = None  # Not burning cash
        fhr["cash_runway_note"] = "FCF positive — not burning cash"
    fhr["cash_runway_flag"] = fhr.get("cash_runway_months") is not None and fhr["cash_runway_months"] < 24

    risk["financial_health"] = fhr

    # --- Insider & Short Interest (finviz) ---
    insider = {}
    try:
        from finvizfinance.quote import finvizfinance as fvf
        stock = fvf(ticker)
        fund = stock.ticker_fundament()
        insider["short_float"] = fund.get("Short Float")
        insider["insider_own"] = fund.get("Insider Own")
        insider["insider_trans"] = fund.get("Insider Trans")
        # Get recent insider trades
        ins_trades = safe(lambda: stock.ticker_inside_trader())
        if ins_trades is not None and not ins_trades.empty:
            insider["recent_trades"] = ins_trades.head(5).to_dict("records")
            # Net signal
            buys = len(ins_trades[ins_trades["Transaction"].str.contains("Buy", case=False, na=False)].head(10))
            sells = len(ins_trades[ins_trades["Transaction"].str.contains("Sale", case=False, na=False)].head(10))
            insider["net_signal"] = "Net Buying" if buys > sells else ("Net Selling" if sells > buys else "Mixed")
            insider["buys_10"] = buys
            insider["sells_10"] = sells
    except Exception as e:
        insider["error"] = str(e)
    risk["insider"] = insider

    # --- Concentration Risk ---
    concentration = {}
    concentration["sector"] = info.get("sector", "N/A")
    concentration["industry"] = info.get("industry", "N/A")
    concentration["country"] = info.get("country", "N/A")
    desc = info.get("longBusinessSummary", "")
    concentration["customer_concentration_hint"] = any(kw in desc.lower() for kw in
        ["largest customer", "significant customer", "major customer", "single customer",
         "concentration", "key customer", "primarily serves"])
    risk["concentration"] = concentration

    # --- Accounting Quality ---
    acct = {}
    if q_fin is not None and not q_fin.empty and q_cf is not None and not q_cf.empty:
        n = min(4, q_fin.shape[1])
        ni_row = _safe_get_row(q_fin, ["Net Income", "Net Income Common Stockholders"], n)
        op_row = _safe_get_row(q_fin, ["Operating Income", "EBIT"], n)
        ocf_row = _safe_get_row(q_cf, ["Operating Cash Flow", "Total Cash From Operating Activities"], min(4, q_cf.shape[1]))

        # GAAP NI vs Operating Income gap
        gaps = []
        for i in range(min(len(ni_row), len(op_row))):
            if ni_row[i] and op_row[i] and op_row[i] != 0:
                gaps.append(round(abs((ni_row[i] - op_row[i]) / op_row[i]) * 100, 1))
        acct["ni_vs_opinc_gaps"] = gaps
        acct["consistent_gap_over_20"] = len(gaps) >= 2 and all(g > 20 for g in gaps)

        # OCF / Net Income ratio
        ni_ttm = sum(v for v in ni_row if v is not None)
        ocf_ttm = sum(v for v in ocf_row if v is not None)
        if ni_ttm and ni_ttm != 0:
            acct["ocf_ni_ratio"] = round(ocf_ttm / ni_ttm, 2)
            acct["ocf_ni_flag"] = acct["ocf_ni_ratio"] < 0.8
        else:
            acct["ocf_ni_ratio"] = None
            acct["ocf_ni_flag"] = None
    risk["accounting"] = acct

    # --- Macro Sensitivity ---
    macro = {}
    beta = info.get("beta")
    macro["beta"] = beta
    if beta is not None:
        if beta < 0.8:
            macro["classification"] = "Defensive"
        elif beta <= 1.2:
            macro["classification"] = "Market-tracking"
        else:
            macro["classification"] = "Aggressive/Cyclical"
    risk["macro"] = macro

    # --- Overall Risk Rating ---
    risk_factors = []
    score = 0  # higher = riskier

    if fhr.get("debt_faster_than_rev"):
        risk_factors.append("Debt growing faster than revenue")
        score += 2
    if fhr.get("fcf_declining"):
        risk_factors.append("Declining free cash flow trend")
        score += 2
    if fhr.get("margin_compressing"):
        risk_factors.append("Operating margins compressing")
        score += 1
    if fhr.get("cash_runway_flag"):
        risk_factors.append(f"Low cash runway ({fhr.get('cash_runway_months', '?')} months)")
        score += 3
    if insider.get("net_signal") == "Net Selling":
        risk_factors.append("Net insider selling")
        score += 1
    short_str = insider.get("short_float", "")
    try:
        short_val = float(str(short_str).replace("%", ""))
        if short_val > 10:
            risk_factors.append(f"High short interest ({short_str})")
            score += 2
    except (ValueError, TypeError):
        pass
    if acct.get("consistent_gap_over_20"):
        risk_factors.append("Consistent >20% gap between net income and operating income")
        score += 1
    if acct.get("ocf_ni_flag"):
        risk_factors.append(f"Earnings not backed by cash flow (OCF/NI ratio: {acct.get('ocf_ni_ratio')})")
        score += 2
    if beta and beta > 1.5:
        risk_factors.append(f"High beta ({beta:.2f}) — sensitive to macro/rates")
        score += 1
    if concentration.get("customer_concentration_hint"):
        risk_factors.append("Potential customer concentration risk noted in business description")
        score += 1

    if score >= 6:
        rating = "High"
    elif score >= 3:
        rating = "Medium"
    else:
        rating = "Low"

    risk["overall"] = {
        "rating": rating,
        "score": score,
        "top_factors": risk_factors[:3],
        "biggest_risk": risk_factors[0] if risk_factors else "No major risk factors identified",
    }

    report["sections"]["risk"] = risk


def render_risk_markdown(report):
    """Render --risk section as markdown."""
    lines = []
    risk = report["sections"].get("risk", {})
    if risk.get("error"):
        lines.append(f"## ⚠️ Risk Report\n*Error: {risk['error']}*\n")
        return "\n".join(lines)

    lines.append("## 🛡️ Risk Report")
    lines.append("")

    # Financial Health
    fhr = risk.get("financial_health", {})
    lines.append("### Financial Health Risks")
    dg = fhr.get("debt_growth_pct")
    rg = fhr.get("rev_growth_pct")
    flag = " ⚠️ DEBT GROWING FASTER" if fhr.get("debt_faster_than_rev") else ""
    lines.append(f"- **Debt vs Revenue Growth:** Debt YoY: {pct(dg)}, Revenue YoY: {pct(rg)}{flag}")

    fcf_q = fhr.get("fcf_quarters", [])
    if fcf_q:
        fcf_str = " → ".join(fmt_num(f, prefix="$") for f in fcf_q)
        flag = " ⚠️ DECLINING" if fhr.get("fcf_declining") else " ✅"
        lines.append(f"- **FCF Trend (last 4Q):** {fcf_str}{flag}")

    margins = fhr.get("op_margins_trend", [])
    if margins:
        m_str = " → ".join(f"{m}%" for m in margins)
        flag = " ⚠️ COMPRESSING" if fhr.get("margin_compressing") else " ✅"
        lines.append(f"- **Op Margin Trend:** {m_str}{flag}")

    cr = fhr.get("cash_runway_months")
    if cr is not None:
        flag = " ⚠️ < 24 MONTHS" if fhr.get("cash_runway_flag") else ""
        lines.append(f"- **Cash Runway:** {cr} months{flag}")
    elif fhr.get("cash_runway_note"):
        lines.append(f"- **Cash Runway:** {fhr['cash_runway_note']} ✅")
    lines.append("")

    # Insider & Short Interest
    ins = risk.get("insider", {})
    lines.append("### Insider & Short Interest")
    if ins.get("error"):
        lines.append(f"*finviz error: {ins['error']}*")
    else:
        lines.append(f"- **Short Interest (% Float):** {ins.get('short_float', 'N/A')}")
        lines.append(f"- **Insider Ownership:** {ins.get('insider_own', 'N/A')}")
        lines.append(f"- **Insider Transactions:** {ins.get('insider_trans', 'N/A')}")
        lines.append(f"- **Net Signal (last 10 trades):** {ins.get('net_signal', 'N/A')} (Buys: {ins.get('buys_10', '?')}, Sells: {ins.get('sells_10', '?')})")
        trades = ins.get("recent_trades", [])
        if trades:
            lines.append("- **Recent Insider Trades:**")
            for tr in trades[:5]:
                lines.append(f"  - {tr.get('Date', '')} | {tr.get('Insider Trading', '')} ({tr.get('Relationship', '')}) | {tr.get('Transaction', '')} | {tr.get('Value ($)', 'N/A')}")
    lines.append("")

    # Concentration Risk
    conc = risk.get("concentration", {})
    lines.append("### Concentration Risk")
    lines.append(f"- **Sector/Industry:** {conc.get('sector', 'N/A')} / {conc.get('industry', 'N/A')} (single-sector exposure)")
    lines.append(f"- **Geographic:** {conc.get('country', 'N/A')}")
    if conc.get("customer_concentration_hint"):
        lines.append("- ⚠️ **Customer Concentration:** Business description suggests possible customer concentration")
    else:
        lines.append("- **Customer Concentration:** No obvious concentration keywords in description")
    lines.append("")

    # Accounting Quality
    acct = risk.get("accounting", {})
    lines.append("### Accounting Quality")
    gaps = acct.get("ni_vs_opinc_gaps", [])
    if gaps:
        gap_str = ", ".join(f"{g}%" for g in gaps)
        flag = " ⚠️ CONSISTENT >20% GAP" if acct.get("consistent_gap_over_20") else " ✅"
        lines.append(f"- **NI vs Operating Income Gap (by Q):** {gap_str}{flag}")
    ocf_ni = acct.get("ocf_ni_ratio")
    if ocf_ni is not None:
        flag = " ⚠️ EARNINGS NOT BACKED BY CASH FLOW" if acct.get("ocf_ni_flag") else " ✅"
        lines.append(f"- **OCF / Net Income Ratio:** {ocf_ni}{flag}")
    lines.append("")

    # Macro Sensitivity
    macro = risk.get("macro", {})
    lines.append("### Macro Sensitivity")
    beta = macro.get("beta")
    if beta is not None:
        lines.append(f"- **Beta:** {beta:.2f} — **{macro.get('classification', 'N/A')}**")
    else:
        lines.append("- **Beta:** N/A")
    lines.append("")

    # Overall Rating
    overall = risk.get("overall", {})
    lines.append("### 🎯 Overall Risk Rating")
    lines.append(f"**Rating: {overall.get('rating', 'N/A')}** (score: {overall.get('score', 0)})")
    top = overall.get("top_factors", [])
    if top:
        lines.append("\n**Top Risk Factors:**")
        for i, f in enumerate(top, 1):
            lines.append(f"  {i}. {f}")
    lines.append(f"\n**Single biggest reason NOT to invest:** {overall.get('biggest_risk', 'N/A')}")
    lines.append("\n---\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Comprehensive stock breakdown")
    parser.add_argument("tickers", nargs="+", help="Stock ticker(s) to analyze")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    parser.add_argument("--deep", action="store_true", help="Include deep dive sections (Steps 7-12)")
    parser.add_argument("--compare", nargs="+", metavar="TICKER", help="Compare primary ticker against 2-4 peers")
    parser.add_argument("--risk", action="store_true", help="Include focused risk report")
    args = parser.parse_args()

    all_reports = []
    for ticker in args.tickers:
        ticker = ticker.upper().strip()
        print(f"Analyzing {ticker}...", file=sys.stderr)
        report = build_report(ticker)
        if args.deep:
            print(f"  Deep dive for {ticker}...", file=sys.stderr)
            build_deep_sections(report, ticker)
        if args.risk:
            print(f"  Risk analysis for {ticker}...", file=sys.stderr)
            build_risk_section(report, ticker)
        if args.compare:
            print(f"  Comparison for {ticker}...", file=sys.stderr)
            build_compare_sections(report, ticker, args.compare[:4])
        all_reports.append(report)

    if args.json_output:
        print(json.dumps(make_serializable(all_reports), indent=2, default=str))
    else:
        for report in all_reports:
            print(render_markdown(report))
            if args.deep:
                print(render_deep_markdown(report))
            if args.risk:
                print(render_risk_markdown(report))
            if args.compare:
                print(render_compare_markdown(report))

if __name__ == "__main__":
    main()
