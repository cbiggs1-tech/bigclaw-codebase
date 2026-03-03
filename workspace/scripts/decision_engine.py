#!/usr/bin/env python3
"""Portfolio Decision Engine — analyzes holdings and generates actionable signals."""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
import yfinance as yf
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator

DB_PATH = "/home/cbiggs90/bigclaw-ai/src/portfolios.db"

# Bond score weights by portfolio type
BOND_WEIGHTS = {
    "Income Dividends": 1.5,
    "Innovation Fund": 1.25,
    "Nuclear Energy": 1.0,
    "Value Picks": 0.5,
    "Defense & Aerospace": 0.25,
    "Momentum Plays": 0.75,
    "Growth Value": 0.75,
}
DEFAULT_BOND_WEIGHT = 0.75

EXPERT_OVERRIDES_PATH = os.path.expanduser("~/.openclaw/workspace/config/expert_overrides.json")
PORTFOLIO_UNIVERSES_PATH = os.path.expanduser("~/.openclaw/workspace/config/portfolio_universes.json")

# Portfolio concentration limits
MAX_HOLDINGS = 7
MIN_HOLDINGS = 5
SWAP_THRESHOLD = 3  # Candidate must outscore holding by this much to trigger swap

SECTOR_ETF_MAP = {
    "Technology": "XLK", "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Healthcare": "XLV", "Financial Services": "XLF", "Financials": "XLF",
    "Energy": "XLE", "Industrials": "XLI", "Basic Materials": "XLB",
    "Communication Services": "XLC", "Utilities": "XLU", "Real Estate": "XLRE",
}


def load_portfolios(filter_name=None):
    """Load portfolios and holdings from SQLite."""
    conn = sqlite3.connect(DB_PATH)
    q = """SELECT p.id, p.name, p.current_cash, h.ticker, h.shares, h.avg_cost
           FROM portfolios p JOIN holdings h ON p.id = h.portfolio_id WHERE p.is_active = 1"""
    if filter_name:
        q += " AND p.name = ?"
        rows = conn.execute(q, (filter_name,)).fetchall()
    else:
        rows = conn.execute(q).fetchall()
    conn.close()

    portfolios = {}
    for pid, pname, cash, ticker, shares, avg_cost in rows:
        if pname not in portfolios:
            portfolios[pname] = {"cash": cash, "holdings": []}
        portfolios[pname]["holdings"].append({"ticker": ticker, "shares": shares, "avg_cost": avg_cost})
    return portfolios


def get_all_tickers(portfolios):
    tickers = set()
    for p in portfolios.values():
        for h in p["holdings"]:
            tickers.add(h["ticker"])
    return sorted(tickers)


def fetch_market_data(tickers):
    """Fetch price history and info for all tickers."""
    data = {}
    # Need ~250 trading days for 200-day SMA + buffer
    end = datetime.now()
    start = end - timedelta(days=400)
    
    # Batch download price data
    all_tickers = list(tickers)
    # Add sector ETFs
    sector_etfs = set(SECTOR_ETF_MAP.values())
    download_tickers = list(set(all_tickers) | sector_etfs)
    
    print(f"Fetching price data for {len(download_tickers)} tickers...", file=sys.stderr)
    prices = yf.download(download_tickers, start=start, end=end, progress=False, auto_adjust=True)
    
    for ticker in all_tickers:
        try:
            if len(download_tickers) == 1:
                close = prices["Close"].dropna()
            else:
                close = prices["Close"][ticker].dropna()
            if len(close) < 20:
                print(f"  ⚠ {ticker}: insufficient price data", file=sys.stderr)
                continue
            data[ticker] = {"close": close}
        except Exception as e:
            print(f"  ⚠ {ticker}: price data error: {e}", file=sys.stderr)

    # Store sector ETF data
    for etf in sector_etfs:
        try:
            if len(download_tickers) == 1:
                close = prices["Close"].dropna()
            else:
                close = prices["Close"][etf].dropna()
            if len(close) > 0:
                data[etf] = {"close": close}
        except:
            pass

    # Fetch info per ticker
    for ticker in all_tickers:
        if ticker not in data:
            continue
        print(f"  Fetching info: {ticker}", file=sys.stderr)
        try:
            t = yf.Ticker(ticker)
            data[ticker]["info"] = t.info or {}
        except:
            data[ticker]["info"] = {}
        # Earnings dates
        try:
            cal = yf.Ticker(ticker).calendar
            if isinstance(cal, dict) and "Earnings Date" in cal:
                dates = cal["Earnings Date"]
                if isinstance(dates, list) and dates:
                    data[ticker]["next_earnings"] = pd.Timestamp(dates[0])
                elif dates:
                    data[ticker]["next_earnings"] = pd.Timestamp(dates)
        except:
            pass

    return data, prices


def fetch_finviz_data(ticker):
    """Fetch finvizfinance data (short interest, insider activity)."""
    result = {"short_pct": None, "insider_buys": 0, "insider_sells": 0}
    try:
        from finvizfinance.quote import finvizfinance as fvf
        stock = fvf(ticker)
        fundament = stock.ticker_fundament()
        short_str = fundament.get("Short Float", fundament.get("Short Float / Ratio", ""))
        if isinstance(short_str, str) and "%" in short_str:
            result["short_pct"] = float(short_str.replace("%", "").strip())
        elif isinstance(short_str, (int, float)):
            result["short_pct"] = float(short_str)
    except Exception as e:
        pass

    try:
        from finvizfinance.quote import finvizfinance as fvf
        stock = fvf(ticker)
        insider = stock.ticker_inside_trader()
        if insider is not None and len(insider) > 0:
            # Look at recent transactions (last ~20)
            for _, row in insider.head(20).iterrows():
                trans = str(row.get("Transaction", "")).lower()
                if "buy" in trans or "purchase" in trans:
                    result["insider_buys"] += 1
                elif "sale" in trans or "sell" in trans:
                    result["insider_sells"] += 1
    except:
        pass

    return result


def analyze_technicals(close):
    """Return technical signals as list of (signal_name, score, description)."""
    signals = []
    current = close.iloc[-1]

    # RSI
    rsi_series = RSIIndicator(close, window=14).rsi()
    rsi = rsi_series.iloc[-1]
    if rsi < 30:
        signals.append(("RSI", 1, f"RSI {rsi:.0f} oversold"))
    elif rsi > 70:
        signals.append(("RSI", -1, f"RSI {rsi:.0f} overbought"))
    else:
        signals.append(("RSI", 0, f"RSI {rsi:.0f}"))

    # MACD
    macd_ind = MACD(close)
    macd_line = macd_ind.macd().iloc[-1]
    signal_line = macd_ind.macd_signal().iloc[-1]
    macd_prev = macd_ind.macd().iloc[-2]
    signal_prev = macd_ind.macd_signal().iloc[-2]
    if macd_prev < signal_prev and macd_line > signal_line:
        signals.append(("MACD", 1, "MACD bullish crossover"))
    elif macd_prev > signal_prev and macd_line < signal_line:
        signals.append(("MACD", -1, "MACD bearish crossover"))
    elif macd_line > signal_line:
        signals.append(("MACD", 0, "MACD above signal"))
    else:
        signals.append(("MACD", 0, "MACD below signal"))

    # 50-day SMA
    if len(close) >= 50:
        sma50 = SMAIndicator(close, window=50).sma_indicator().iloc[-1]
        if current > sma50:
            signals.append(("SMA50", 1, f"above 50-day SMA"))
        else:
            signals.append(("SMA50", -1, f"below 50-day SMA"))
    
    # 200-day SMA
    if len(close) >= 200:
        sma200 = SMAIndicator(close, window=200).sma_indicator().iloc[-1]
        if current > sma200:
            signals.append(("SMA200", 1, f"above 200-day SMA"))
        else:
            signals.append(("SMA200", -1, f"below 200-day SMA"))
        
        # Golden/Death cross
        sma50 = SMAIndicator(close, window=50).sma_indicator().iloc[-1]
        if sma50 > sma200:
            signals.append(("Cross", 1, "golden cross (50>200)"))
        else:
            signals.append(("Cross", -1, "death cross (50<200)"))

    return signals


def analyze_fundamentals(info, finviz):
    """Return fundamental signals."""
    signals = []

    # Earnings growth
    eg = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
    if eg is not None:
        if eg < 0:
            signals.append(("EarningsGrowth", -1, f"earnings growth {eg:.0%}"))
        else:
            signals.append(("EarningsGrowth", 1, f"earnings growth {eg:.0%}"))

    # Revenue growth
    rg = info.get("revenueGrowth")
    if rg is not None:
        if rg < 0:
            signals.append(("RevenueGrowth", -1, f"revenue growth {rg:.0%}"))
        else:
            signals.append(("RevenueGrowth", 0, f"revenue growth {rg:.0%}"))

    # P/E comparison
    trailing = info.get("trailingPE")
    forward = info.get("forwardPE")
    if trailing and forward and trailing > 0 and forward > 0:
        if forward > trailing:
            signals.append(("PE", -1, f"forward P/E ({forward:.1f}) > trailing ({trailing:.1f})"))
        else:
            signals.append(("PE", 0, f"P/E improving"))

    # Debt/equity
    de = info.get("debtToEquity")
    if de is not None and de > 100:
        signals.append(("DebtEquity", -1, f"D/E ratio {de:.0f}"))

    # Short interest
    if finviz.get("short_pct") is not None and finviz["short_pct"] > 10:
        signals.append(("ShortInterest", -1, f"short interest {finviz['short_pct']:.1f}%"))

    return signals


def analyze_insider(finviz):
    signals = []
    buys = finviz.get("insider_buys", 0)
    sells = finviz.get("insider_sells", 0)
    if buys > sells and buys > 0:
        signals.append(("Insider", 1, f"insider net buying ({buys}B/{sells}S)"))
    elif sells > buys and sells > 0:
        signals.append(("Insider", -1, f"insider net selling ({buys}B/{sells}S)"))
    return signals


def analyze_earnings_proximity(ticker_data):
    signals = []
    flags = []
    next_e = ticker_data.get("next_earnings")
    if next_e:
        now = pd.Timestamp.now()
        if hasattr(next_e, "tz") and next_e.tz:
            now = pd.Timestamp.now(tz=next_e.tz)
        days = (next_e - now).days
        if 0 <= days <= 14:
            signals.append(("Earnings", 0, f"EARNINGS APPROACHING ({days}d)"))
            flags.append({"date": next_e.strftime("%b %d"), "days": days})
    return signals, flags


def analyze_relative_strength(ticker, ticker_data, market_data):
    signals = []
    info = ticker_data.get("info", {})
    sector = info.get("sector", "")
    etf = SECTOR_ETF_MAP.get(sector)
    if not etf or etf not in market_data:
        return signals
    
    close = ticker_data["close"]
    etf_close = market_data[etf]["close"]
    
    # 1-month return (~21 trading days)
    n = min(21, len(close) - 1, len(etf_close) - 1)
    if n < 5:
        return signals
    
    stock_ret = (close.iloc[-1] / close.iloc[-n]) - 1
    etf_ret = (etf_close.iloc[-1] / etf_close.iloc[-n]) - 1
    
    diff = stock_ret - etf_ret
    if diff > 0.02:
        signals.append(("RelStrength", 1, f"outperforming {etf} by {diff:.1%}"))
    elif diff < -0.02:
        signals.append(("RelStrength", -1, f"underperforming {etf} by {abs(diff):.1%}"))
    else:
        signals.append(("RelStrength", 0, f"in line with {etf}"))
    
    return signals


def portfolio_level_checks(portfolios, market_data):
    """Check overlap, correlation, concentration."""
    # Overlap
    ticker_portfolios = defaultdict(list)
    for pname, pdata in portfolios.items():
        for h in pdata["holdings"]:
            ticker_portfolios[h["ticker"]].append(pname)
    overlap = {t: ps for t, ps in ticker_portfolios.items() if len(ps) > 1}

    # Concentration per portfolio
    concentration = []
    for pname, pdata in portfolios.items():
        total_value = pdata["cash"]
        holding_values = []
        for h in pdata["holdings"]:
            t = h["ticker"]
            if t in market_data and "close" in market_data[t]:
                price = market_data[t]["close"].iloc[-1]
                val = h["shares"] * price
            else:
                val = h["shares"] * h["avg_cost"]
            holding_values.append((t, val))
            total_value += val
        
        for t, val in holding_values:
            pct = val / total_value * 100 if total_value > 0 else 0
            if pct > 15:
                concentration.append({"ticker": t, "portfolio": pname, "pct": pct})

    # Correlation (3-month daily returns)
    all_tickers = list(set(t for p in portfolios.values() for h in p["holdings"] for t in [h["ticker"]] if t in market_data))
    corr_flags = []
    if len(all_tickers) >= 2:
        n = 63  # ~3 months
        returns = {}
        for t in all_tickers:
            c = market_data[t]["close"]
            if len(c) > n:
                r = c.iloc[-n:].pct_change().dropna()
                returns[t] = r
        
        tickers_with_returns = list(returns.keys())
        for i in range(len(tickers_with_returns)):
            for j in range(i + 1, len(tickers_with_returns)):
                t1, t2 = tickers_with_returns[i], tickers_with_returns[j]
                try:
                    # Align on common dates
                    common = returns[t1].index.intersection(returns[t2].index)
                    if len(common) > 20:
                        corr = returns[t1].loc[common].corr(returns[t2].loc[common])
                        if corr > 0.8:
                            corr_flags.append({"t1": t1, "t2": t2, "corr": corr})
                except:
                    pass

    return overlap, concentration, corr_flags


def load_expert_overrides():
    """Load domain expert conviction overrides from JSON config."""
    try:
        with open(EXPERT_OVERRIDES_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def analyze_value_override(ticker, close, info, technical_signals, prices):
    """Dimension 8: Value Override — catches undervalued stocks with bad technicals.
    
    Returns (score, components_dict, summary_string).
    components_dict has individual scores and reasons for JSON output.
    """
    components = {}
    score = 0
    reasons = []

    current_price = float(close.iloc[-1])

    # 1. Price vs analyst consensus target
    target = info.get("targetMeanPrice")
    if target and target > 0:
        discount = (target - current_price) / target
        if discount > 0.25:
            components["analyst_target"] = {"score": 2, "reason": f"{discount:.0%} below analyst target ${target:.2f}"}
            score += 2
            reasons.append(f"{discount:.0%} below target")
        elif discount > 0.15:
            components["analyst_target"] = {"score": 1, "reason": f"{discount:.0%} below analyst target ${target:.2f}"}
            score += 1
            reasons.append(f"{discount:.0%} below target")

    # 2. RSI oversold (extract from already-calculated technicals)
    rsi_val = None
    for name, _, desc in technical_signals:
        if name == "RSI":
            # Parse RSI value from description like "RSI 28 oversold"
            try:
                rsi_val = float(desc.split()[1])
            except (IndexError, ValueError):
                pass
            break
    
    if rsi_val is not None:
        if rsi_val < 30:
            components["rsi_oversold"] = {"score": 2, "reason": f"RSI {rsi_val:.0f} deeply oversold"}
            score += 2
            reasons.append(f"RSI {rsi_val:.0f} oversold")
        elif rsi_val < 40:
            components["rsi_oversold"] = {"score": 1, "reason": f"RSI {rsi_val:.0f} oversold territory"}
            score += 1
            reasons.append(f"RSI {rsi_val:.0f} oversold")

    # 3. Capitulation volume (>3x 20-day avg on down day)
    try:
        if prices is not None and len(close) >= 21:
            if hasattr(prices, "columns") and isinstance(prices.columns, pd.MultiIndex):
                vol = prices["Volume"][ticker].dropna()
            else:
                vol = prices["Volume"].dropna()
            if len(vol) >= 21:
                latest_vol = vol.iloc[-1]
                avg_vol_20 = vol.iloc[-21:-1].mean()
                price_change = close.iloc[-1] - close.iloc[-2]
                if avg_vol_20 > 0 and latest_vol > 3 * avg_vol_20 and price_change < 0:
                    components["capitulation"] = {"score": 1, "reason": f"volume {latest_vol/avg_vol_20:.1f}x avg on down day (capitulation)"}
                    score += 1
                    reasons.append("capitulation volume")
    except Exception:
        pass

    # 4. Forward P/E vs sector median (>30% cheaper)
    forward_pe = info.get("forwardPE")
    industry = info.get("industry", "")
    if forward_pe and forward_pe > 0 and industry:
        try:
            industry_pe = info.get("industryForwardPE")  # Not always available
            # Fallback: use sector PE from yfinance
            sector_pe = info.get("sectorForwardPE")
            compare_pe = industry_pe or sector_pe
            if compare_pe and compare_pe > 0:
                discount_pe = (compare_pe - forward_pe) / compare_pe
                if discount_pe > 0.30:
                    components["pe_discount"] = {"score": 1, "reason": f"forward P/E {forward_pe:.1f} vs sector median {compare_pe:.1f} ({discount_pe:.0%} cheaper)"}
                    score += 1
                    reasons.append(f"P/E {discount_pe:.0%} below sector")
        except Exception:
            pass

    # 5. Price below book value
    pb = info.get("priceToBook")
    if pb is not None and 0.01 < pb < 1.0:
        components["below_book"] = {"score": 1, "reason": f"P/B {pb:.2f} (below book value)"}
        score += 1
        reasons.append(f"P/B {pb:.2f}")

    # 6. Expert override
    expert_overrides = load_expert_overrides()
    if ticker in expert_overrides:
        eo = expert_overrides[ticker]
        eo_score = eo.get("override_score", 0)
        eo_reason = eo.get("reason", "expert conviction")
        eo_by = eo.get("set_by", "unknown")
        components["expert_override"] = {"score": eo_score, "reason": f"{eo_reason} (set by {eo_by})", "date": eo.get("date", "")}
        score += eo_score
        reasons.append(f"🧠 Expert: {eo_reason}")

    summary = ""
    if score > 0:
        summary = f"⚡ VALUE OVERRIDE: +{score} ({', '.join(reasons)})"

    return score, components, summary


def fetch_bond_score():
    """Fetch bond market signals (calls macro_scanner's bond function)."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from macro_scanner import get_bond_signals
        bond = get_bond_signals()
        return bond
    except Exception as e:
        print(f"  ⚠ Bond signals error: {e}", file=sys.stderr)
        return {"combined_score": 0, "scores": {}}


def get_position_size_recommendation(score):
    """Return position size range based on score."""
    if score >= 5:
        return "full", "12-15%"
    elif score >= 3:
        return "standard", "8-12%"
    elif score >= 1:
        return "starter", "5-8%"
    else:
        return "review", "0% (flag for review)"


def load_portfolio_universes():
    """Load candidate universes for rescreen."""
    try:
        with open(PORTFOLIO_UNIVERSES_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def score_ticker(ticker, market_data, prices, bond_combined, bond_weight):
    """Score a single ticker. Returns result dict or None if no data."""
    if ticker not in market_data:
        return {"ticker": ticker, "score": 0, "signals": [], "reasons": ["no data"], "label": "⚪ HOLD"}

    td = market_data[ticker]
    close = td["close"]
    info = td.get("info", {})

    finviz = fetch_finviz_data(ticker)

    all_signals = []
    all_signals.extend(analyze_technicals(close))
    all_signals.extend(analyze_fundamentals(info, finviz))
    all_signals.extend(analyze_insider(finviz))

    earn_signals, earn_flags = analyze_earnings_proximity(td)
    all_signals.extend(earn_signals)

    all_signals.extend(analyze_relative_strength(ticker, td, market_data))

    # Bond market signals
    bond_adj = round(bond_combined * bond_weight * 0.5)
    if bond_adj != 0:
        all_signals.append(("BondMkt", bond_adj, f"bond mkt {bond_combined:+d} (wt {bond_weight}x)"))

    base_score = sum(s[1] for s in all_signals)

    # Value Override
    tech_signals = analyze_technicals(close)
    vo_score, vo_components, vo_summary = analyze_value_override(ticker, close, info, tech_signals, prices)
    if vo_score > 0:
        all_signals.append(("ValueOverride", vo_score, vo_summary))

    score = sum(s[1] for s in all_signals)
    reasons = [s[2] for s in all_signals if s[1] != 0] or [s[2] for s in all_signals[:3]]

    if bond_combined <= -2 and 1 <= score <= 2 and vo_score < 3:
        score = 0
        reasons.insert(0, "⚠️ bond headwinds override marginal buy")

    if base_score <= -5 and vo_score > 0 and vo_score < 3:
        score = base_score + vo_score
        if score > -3:
            score = -3

    if score >= 3:
        label = "🟢 STRONG BUY / ADD"
    elif score >= 1:
        label = "🟢 BUY / HOLD"
    elif score == 0:
        label = "⚪ HOLD"
    elif score >= -2:
        label = "🟡 WATCH / CAUTION"
    else:
        label = "🔴 SELL / TRIM"

    result_entry = {
        "ticker": ticker, "score": score, "signals": all_signals,
        "reasons": reasons, "label": label,
        "price": float(close.iloc[-1]),
        "sector": info.get("sector", ""),
    }
    if vo_score > 0:
        result_entry["value_override"] = {
            "total_score": vo_score,
            "base_score_before": base_score,
            "components": vo_components,
            "summary": vo_summary,
        }

    size_cat, size_range = get_position_size_recommendation(score)
    result_entry["position_size"] = {"category": size_cat, "range": size_range}

    return result_entry, earn_flags


def build_portfolio_optimization(portfolios, results_by_ticker, market_data, candidate_scores=None):
    """Build portfolio optimization recommendations."""
    optimization = {}

    for pname, pdata in portfolios.items():
        holdings = pdata["holdings"]
        num_holdings = len(holdings)

        # Rank holdings by score
        ranked = []
        for h in holdings:
            ticker = h["ticker"]
            r = results_by_ticker.get(ticker)
            score = r["score"] if r else 0
            # Get current value
            if ticker in market_data and "close" in market_data[ticker]:
                price = float(market_data[ticker]["close"].iloc[-1])
                value = h["shares"] * price
            else:
                price = h["avg_cost"]
                value = h["shares"] * h["avg_cost"]
            size_cat, size_range = get_position_size_recommendation(score)
            ranked.append({
                "ticker": ticker, "score": score, "shares": h["shares"],
                "price": price, "value": value,
                "position_size": {"category": size_cat, "range": size_range},
                "label": r["label"] if r else "⚪ HOLD",
            })

        ranked.sort(key=lambda x: x["score"], reverse=True)

        # Trim recommendations
        trim_list = []
        if num_holdings > MAX_HOLDINGS:
            for item in ranked[MAX_HOLDINGS:]:
                item["action"] = "TRIM (over capacity)"
                trim_list.append(item)

        # Flag holdings with score <= 0 for review
        review_list = [item for item in ranked if item["score"] <= 0 and item not in trim_list]

        opt_entry = {
            "portfolio": pname,
            "num_holdings": num_holdings,
            "over_limit": num_holdings > MAX_HOLDINGS,
            "under_limit": num_holdings < MIN_HOLDINGS,
            "ranked_holdings": ranked,
            "trim_recommendations": trim_list,
            "review_flags": review_list,
            "swap_recommendations": [],
        }

        # Swap recommendations from candidates
        if candidate_scores and pname in candidate_scores:
            weakest_score = ranked[-1]["score"] if ranked else 999
            for cand in candidate_scores[pname]:
                # Find weakest current holding
                for held in reversed(ranked):
                    if cand["score"] - held["score"] >= SWAP_THRESHOLD:
                        opt_entry["swap_recommendations"].append({
                            "sell": held["ticker"],
                            "sell_score": held["score"],
                            "buy": cand["ticker"],
                            "buy_score": cand["score"],
                            "score_diff": cand["score"] - held["score"],
                        })
                        break  # One swap per candidate

        optimization[pname] = opt_entry

    return optimization


def run_analysis(portfolio_filter=None, rescreen=False):
    portfolios = load_portfolios(portfolio_filter)
    if not portfolios:
        print("No portfolios found.", file=sys.stderr)
        return None

    all_tickers = get_all_tickers(portfolios)

    # If rescreen, also fetch candidate tickers
    candidate_tickers = set()
    universes = {}
    if rescreen:
        universes = load_portfolio_universes()
        for pname, candidates in universes.items():
            for t in candidates:
                if t not in all_tickers:
                    candidate_tickers.add(t)

    fetch_tickers = sorted(set(all_tickers) | candidate_tickers)
    market_data, _prices = fetch_market_data(fetch_tickers)

    # Fetch bond signals
    print("Fetching bond market signals...", file=sys.stderr)
    bond_data = fetch_bond_score()
    bond_combined = bond_data.get("combined_score", 0)

    # Build ticker->portfolio mapping for bond weight lookup
    ticker_portfolios = {}
    for pname, pdata in portfolios.items():
        for h in pdata["holdings"]:
            if h["ticker"] not in ticker_portfolios:
                ticker_portfolios[h["ticker"]] = []
            ticker_portfolios[h["ticker"]].append(pname)

    # Per-ticker analysis
    results = []
    results_by_ticker = {}
    earnings_calendar = []

    for ticker in fetch_tickers:
        if ticker not in market_data:
            entry = {"ticker": ticker, "score": 0, "signals": [], "reasons": ["no data"], "label": "⚪ HOLD",
                     "position_size": {"category": "review", "range": "0% (flag for review)"}}
            results.append(entry)
            results_by_ticker[ticker] = entry
            continue

        print(f"  Analyzing: {ticker}", file=sys.stderr)

        port_names = ticker_portfolios.get(ticker, [])
        bond_weight = max((BOND_WEIGHTS.get(pn, DEFAULT_BOND_WEIGHT) for pn in port_names), default=DEFAULT_BOND_WEIGHT)

        result_entry, earn_flags = score_ticker(ticker, market_data, _prices, bond_combined, bond_weight)

        for ef in earn_flags:
            earnings_calendar.append({"ticker": ticker, **ef})

        results.append(result_entry)
        results_by_ticker[ticker] = result_entry

    # Portfolio-level
    overlap, concentration, corr_flags = portfolio_level_checks(portfolios, market_data)

    # Add correlation info to reasons
    corr_map = defaultdict(list)
    for cf in corr_flags:
        corr_map[cf["t1"]].append(f"correlated with {cf['t2']} ({cf['corr']:.2f})")
        corr_map[cf["t2"]].append(f"correlated with {cf['t1']} ({cf['corr']:.2f})")
    for r in results:
        if r["ticker"] in corr_map:
            r["reasons"].extend(corr_map[r["ticker"]])

    # Portfolio optimization / concentration management
    candidate_scores = {}
    if rescreen and universes:
        for pname, candidates in universes.items():
            scored = []
            for t in candidates:
                r = results_by_ticker.get(t)
                if r:
                    scored.append({"ticker": t, "score": r["score"], "label": r["label"],
                                   "price": r.get("price", 0)})
            scored.sort(key=lambda x: x["score"], reverse=True)
            candidate_scores[pname] = scored

    portfolio_optimization = build_portfolio_optimization(
        portfolios, results_by_ticker, market_data, candidate_scores if rescreen else None
    )

    return {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "signals": results,
        "earnings": earnings_calendar,
        "overlap": [{"ticker": t, "portfolios": ps} for t, ps in overlap.items()],
        "concentration": concentration,
        "correlations": corr_flags,
        "bond_signals": bond_data,
        "portfolio_optimization": portfolio_optimization,
    }


def format_markdown(data):
    lines = [f"# 📊 Daily Decision Dashboard", f"*Generated {data['date']}*", ""]

    # Group by category
    sell = [r for r in data["signals"] if r["score"] <= -3]
    watch = [r for r in data["signals"] if -2 <= r["score"] <= -1]
    buy = [r for r in data["signals"] if r["score"] >= 2]
    hold = [r for r in data["signals"] if 0 <= r["score"] <= 1]

    def _format_signal_line(r, prefix):
        vo = r.get("value_override")
        vo_line = f"\n  {vo['summary']}" if vo else ""
        return f"- {prefix}: {r['ticker']} (score: {'+' if r['score'] > 0 else ''}{r['score']}) — {', '.join(r['reasons'][:4])}{vo_line}"

    if sell:
        lines.append("## 🔴 Action Required")
        for r in sorted(sell, key=lambda x: x["score"]):
            action = "SELL" if r["score"] <= -4 else "TRIM"
            lines.append(_format_signal_line(r, action))
        lines.append("")

    if watch:
        lines.append("## 🟡 Watch List")
        for r in sorted(watch, key=lambda x: x["score"]):
            lines.append(_format_signal_line(r, "WATCH"))
        lines.append("")

    if buy:
        lines.append("## 🟢 Opportunities")
        for r in sorted(buy, key=lambda x: -x["score"]):
            action = "ADD" if r["score"] >= 3 else "BUY"
            lines.append(_format_signal_line(r, action))
        lines.append("")

    if hold:
        lines.append("## ⚪ Hold (no action needed)")
        for r in sorted(hold, key=lambda x: -x["score"]):
            lines.append(_format_signal_line(r, r["ticker"]))
        lines.append("")

    if data["earnings"]:
        lines.append("## 📅 Earnings Calendar (next 14 days)")
        for e in sorted(data["earnings"], key=lambda x: x["days"]):
            lines.append(f"- {e['ticker']}: {e['date']} ({e['days']} days)")
        lines.append("")

    if data["overlap"]:
        lines.append("## 🔗 Portfolio Overlap")
        for o in data["overlap"]:
            lines.append(f"- {o['ticker']}: appears in {' AND '.join(o['portfolios'])}")
        lines.append("")

    if data["concentration"]:
        lines.append("## ⚠️ Concentration Alerts")
        for c in data["concentration"]:
            lines.append(f"- {c['ticker']}: {c['pct']:.0f}% of {c['portfolio']} (>15% threshold)")
        lines.append("")

    if data["correlations"]:
        lines.append("## 🔗 High Correlations")
        for c in data["correlations"]:
            lines.append(f"- {c['t1']} ↔ {c['t2']}: {c['corr']:.2f}")
        lines.append("")

    # Portfolio Optimization section
    opt = data.get("portfolio_optimization", {})
    needs_optimization = {k: v for k, v in opt.items() if v.get("over_limit") or v.get("trim_recommendations") or v.get("swap_recommendations")}
    if needs_optimization or opt:
        lines.append("## 📐 Portfolio Optimization")
        lines.append("")
        for pname, popt in sorted(opt.items()):
            num = popt["num_holdings"]
            status = ""
            if popt["over_limit"]:
                status = f" ⚠️ OVER LIMIT ({num}/{MAX_HOLDINGS})"
            elif popt["under_limit"]:
                status = f" 📉 UNDER-DIVERSIFIED ({num}/{MIN_HOLDINGS} min)"
            else:
                status = f" ✅ ({num}/{MAX_HOLDINGS})"

            lines.append(f"### {pname}{status}")
            lines.append("")

            # Ranked holdings
            lines.append("**Holdings by score:**")
            for i, h in enumerate(popt["ranked_holdings"], 1):
                trim_marker = ""
                if i > MAX_HOLDINGS and popt["over_limit"]:
                    trim_marker = " 🔻 **TRIM**"
                review_marker = ""
                if h["score"] <= 0:
                    review_marker = " ⚠️ review"
                size = h["position_size"]
                lines.append(f"  {i}. **{h['ticker']}** — score: {h['score']:+d} | ${h['value']:,.0f} | {h['label']} | size: {size['range']}{trim_marker}{review_marker}")
            lines.append("")

            # Trim recommendations
            if popt["trim_recommendations"]:
                lines.append("**Trim recommendations (over capacity):**")
                for t in popt["trim_recommendations"]:
                    lines.append(f"  - 🔻 **{t['ticker']}** (score: {t['score']:+d}) — lowest ranked, trim to reach {MAX_HOLDINGS} holdings")
                lines.append("")

            # Swap recommendations
            if popt["swap_recommendations"]:
                lines.append("**Swap recommendations:**")
                for s in popt["swap_recommendations"]:
                    lines.append(f"  - 🔄 SWAP: sell **{s['sell']}** ({s['sell_score']:+d}) → buy **{s['buy']}** ({s['buy_score']:+d}) | +{s['score_diff']} score advantage")
                lines.append("")

    return "\n".join(lines)


def format_json(data):
    # Make JSON-serializable
    signals_out = []
    for r in data["signals"]:
        entry = {"ticker": r["ticker"], "score": r["score"], "label": r["label"],
                 "reasons": r["reasons"], "price": r.get("price")}
        if "value_override" in r:
            entry["value_override"] = r["value_override"]
        signals_out.append(entry)
    # Serialize portfolio optimization
    port_opt = {}
    for pname, popt in data.get("portfolio_optimization", {}).items():
        port_opt[pname] = {
            "num_holdings": popt["num_holdings"],
            "over_limit": popt["over_limit"],
            "under_limit": popt["under_limit"],
            "ranked_holdings": [
                {"ticker": h["ticker"], "score": h["score"], "value": h["value"],
                 "position_size": h["position_size"], "label": h["label"]}
                for h in popt["ranked_holdings"]
            ],
            "trim_recommendations": [
                {"ticker": t["ticker"], "score": t["score"]}
                for t in popt["trim_recommendations"]
            ],
            "swap_recommendations": popt["swap_recommendations"],
        }

    out = {
        "date": data["date"],
        "signals": signals_out,
        "earnings": data["earnings"],
        "overlap": data["overlap"],
        "concentration": data["concentration"],
        "bond_signals": data.get("bond_signals"),
        "portfolio_optimization": port_opt,
    }
    return json.dumps(out, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Portfolio Decision Engine")
    parser.add_argument("--portfolio", type=str, default=None, help="Filter to a specific portfolio")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--rescreen", action="store_true", help="Score candidate universe for swap recommendations")
    args = parser.parse_args()

    data = run_analysis(args.portfolio, rescreen=args.rescreen)
    if not data:
        sys.exit(1)

    if args.json:
        print(format_json(data))
    else:
        print(format_markdown(data))


if __name__ == "__main__":
    main()
