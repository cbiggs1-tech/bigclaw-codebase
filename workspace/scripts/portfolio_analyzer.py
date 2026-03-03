#!/usr/bin/env python3
"""Portfolio Analyzer — risk, diversification, and optimization analysis."""

import argparse
import json
import sqlite3
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import ffn

warnings.filterwarnings("ignore")

DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"

STRESS_PERIODS = {
    "COVID Crash": ("2020-02-19", "2020-03-23"),
    "2022 Bear Market": ("2022-01-03", "2022-10-12"),
}

CAP_THRESHOLDS = {"Large": 10e9, "Mid": 2e9}


def get_portfolio_from_db(name):
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT h.ticker, h.shares FROM holdings h JOIN portfolios p "
        "ON h.portfolio_id = p.id WHERE p.name = ? AND h.shares > 0",
        (name,),
    ).fetchall()
    conn.close()
    if not rows:
        print(f"Error: Portfolio '{name}' not found or empty.", file=sys.stderr)
        sys.exit(1)
    tickers = [r[0] for r in rows]
    quantities = [r[1] for r in rows]
    # Get current prices to calculate weights
    prices = {}
    for t in tickers:
        try:
            tk = yf.Ticker(t)
            p = tk.fast_info.get("lastPrice") or tk.info.get("currentPrice") or tk.info.get("regularMarketPrice")
            prices[t] = p if p else 0
        except:
            prices[t] = 0
    values = [quantities[i] * prices[tickers[i]] for i in range(len(tickers))]
    total = sum(values)
    if total == 0:
        print("Error: Could not determine portfolio values.", file=sys.stderr)
        sys.exit(1)
    weights = [v / total * 100 for v in values]
    return tickers, weights


def fetch_info(tickers):
    """Fetch yfinance .info for all tickers."""
    info = {}
    for t in tickers:
        try:
            info[t] = yf.Ticker(t).info
        except Exception as e:
            print(f"  ⚠ Could not fetch info for {t}: {e}", file=sys.stderr)
            info[t] = {}
    return info


def fetch_prices(tickers, years=6):
    """Fetch price history. Default 6 years to cover stress test periods back to 2020."""
    end = datetime.now()
    start = end - timedelta(days=years * 365)
    all_tickers = list(tickers) + ["SPY"]
    data = yf.download(all_tickers, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), progress=False)
    # Handle multi-level columns
    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"] if "Close" in data.columns.get_level_values(0) else data["Adj Close"]
    else:
        prices = data
    return prices.dropna(how="all")


def get_risk_free_rate():
    try:
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(period="5d")
        if not hist.empty:
            return hist["Close"].iloc[-1] / 100
    except:
        pass
    return 0.04


def classify_cap(mc):
    if mc is None:
        return "Unknown"
    if mc > CAP_THRESHOLDS["Large"]:
        return "Large Cap"
    if mc > CAP_THRESHOLDS["Mid"]:
        return "Mid Cap"
    return "Small Cap"


def classify_style(info_dict):
    pe = info_dict.get("trailingPE") or info_dict.get("forwardPE")
    growth = info_dict.get("revenueGrowth") or info_dict.get("earningsGrowth")
    if pe is None:
        return "Blend"
    if growth and growth > 0.2 and (pe > 25):
        return "Growth"
    if pe < 15:
        return "Value"
    return "Blend"


def step1_allocation(tickers, weights, info):
    """Allocation breakdown."""
    w = {t: weights[i] / 100 for i, t in enumerate(tickers)}
    # Sector
    sectors = {}
    for t in tickers:
        s = info.get(t, {}).get("sector", "Unknown")
        sectors[s] = sectors.get(s, 0) + w[t] * 100
    sector_flags = [s for s, v in sectors.items() if v > 30]

    # Geography
    countries = {}
    for t in tickers:
        c = info.get(t, {}).get("country", "Unknown")
        countries[c] = countries.get(c, 0) + w[t] * 100
    us_pct = countries.get("United States", 0)
    intl_pct = 100 - us_pct

    # Market cap
    caps = {}
    cap_detail = {}
    for t in tickers:
        mc = info.get(t, {}).get("marketCap")
        label = classify_cap(mc)
        cap_detail[t] = label
        caps[label] = caps.get(label, 0) + w[t] * 100

    # Style
    styles = {}
    style_detail = {}
    for t in tickers:
        s = classify_style(info.get(t, {}))
        style_detail[t] = s
        styles[s] = styles.get(s, 0) + w[t] * 100

    return {
        "sectors": sectors,
        "sector_flags": sector_flags,
        "countries": countries,
        "domestic_pct": round(us_pct, 1),
        "international_pct": round(intl_pct, 1),
        "market_cap": caps,
        "cap_detail": cap_detail,
        "styles": styles,
        "style_detail": style_detail,
    }


def step2_holdings(tickers, weights, info):
    holdings = sorted(zip(tickers, weights), key=lambda x: -x[1])
    concentrated = [t for t, w in holdings if w > 10]
    display = holdings[:10] if len(holdings) > 10 else holdings
    return {
        "holdings": holdings,
        "display": display,
        "concentrated": concentrated,
        "total": len(holdings),
    }


def step3_risk(tickers, weights, prices):
    w = np.array(weights) / 100
    # Use last 3 years for risk metrics
    cutoff = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")
    p3 = prices.loc[cutoff:]
    ticker_prices = p3[[t for t in tickers if t in p3.columns]]
    spy_prices = p3["SPY"] if "SPY" in p3.columns else None

    returns = ticker_prices.pct_change().dropna()
    available = [t for t in tickers if t in returns.columns]
    w_avail = np.array([weights[tickers.index(t)] for t in available]) / 100
    w_avail = w_avail / w_avail.sum()

    port_returns = (returns[available] * w_avail).sum(axis=1)
    rf = get_risk_free_rate()

    # Beta
    beta = None
    if spy_prices is not None:
        spy_ret = spy_prices.pct_change().dropna()
        aligned = pd.concat([port_returns, spy_ret], axis=1).dropna()
        aligned.columns = ["port", "spy"]
        if len(aligned) > 30:
            cov = np.cov(aligned["port"], aligned["spy"])
            beta = round(cov[0, 1] / cov[1, 1], 3)

    ann_vol = round(port_returns.std() * np.sqrt(252) * 100, 2)
    ann_ret = round(port_returns.mean() * 252 * 100, 2)

    # Sharpe
    sharpe = round((port_returns.mean() * 252 - rf) / (port_returns.std() * np.sqrt(252)), 3) if port_returns.std() > 0 else None

    # Sortino
    downside = port_returns[port_returns < 0]
    sortino = round((port_returns.mean() * 252 - rf) / (downside.std() * np.sqrt(252)), 3) if len(downside) > 0 and downside.std() > 0 else None

    # Max drawdown via ffn
    cum = (1 + port_returns).cumprod()
    cum.name = "Portfolio"
    perf = ffn.core.PerformanceStats(cum)
    max_dd = round(perf.max_drawdown * 100, 2)

    # Drawdown dates
    running_max = cum.cummax()
    drawdown = cum / running_max - 1
    dd_end = drawdown.idxmin()
    dd_start = cum.loc[:dd_end].idxmax()

    # Correlation
    corr = returns[available].corr()
    high_corr = []
    for i in range(len(available)):
        for j in range(i + 1, len(available)):
            c = corr.iloc[i, j]
            if c > 0.8:
                high_corr.append((available[i], available[j], round(c, 3)))

    return {
        "beta": beta,
        "annualized_volatility": ann_vol,
        "annualized_return": ann_ret,
        "max_drawdown": max_dd,
        "max_dd_start": str(dd_start.date()) if dd_start is not None else None,
        "max_dd_end": str(dd_end.date()) if dd_end is not None else None,
        "sharpe": sharpe,
        "sortino": sortino,
        "risk_free_rate": round(rf * 100, 2),
        "correlation": {t: {t2: round(corr.loc[t, t2], 3) for t2 in available} for t in available},
        "high_correlation_pairs": high_corr,
    }


def step4_cost(tickers, weights, info):
    costs = {}
    for t in tickers:
        er = info.get(t, {}).get("annualReportExpenseRatio") or info.get(t, {}).get("totalExpenseRatio")
        costs[t] = er
    w = {t: weights[i] / 100 for i, t in enumerate(tickers)}
    etf_tickers = {t: c for t, c in costs.items() if c is not None}
    weighted_er = sum(w[t] * c for t, c in etf_tickers.items()) if etf_tickers else 0
    return {
        "expense_ratios": costs,
        "weighted_avg_er": round(weighted_er * 100, 4),
        "annual_cost_10k": round(weighted_er * 10000, 2),
        "annual_cost_50k": round(weighted_er * 50000, 2),
        "annual_cost_100k": round(weighted_er * 100000, 2),
    }


def step5_income(tickers, weights, info):
    yields_ = {}
    for t in tickers:
        dy = info.get(t, {}).get("trailingAnnualDividendYield")  # decimal, e.g. 0.004 = 0.4%
        yields_[t] = dy
    w = {t: weights[i] / 100 for i, t in enumerate(tickers)}
    blended = sum(w[t] * (y or 0) for t, y in yields_.items())
    payers = [t for t, y in yields_.items() if y and y > 0]
    non_payers = [t for t, y in yields_.items() if not y or y == 0]
    return {
        "dividend_yields": {t: round(y * 100, 2) if y else 0 for t, y in yields_.items()},
        "blended_yield": round(blended * 100, 2),
        "annual_income_10k": round(blended * 10000, 2),
        "annual_income_50k": round(blended * 50000, 2),
        "annual_income_100k": round(blended * 100000, 2),
        "payers": payers,
        "non_payers": non_payers,
    }


def step6_stress(tickers, weights, prices):
    w_arr = np.array(weights) / 100
    available = [t for t in tickers if t in prices.columns]
    w_avail = np.array([weights[tickers.index(t)] for t in available]) / 100
    w_avail = w_avail / w_avail.sum()

    results = {}
    for name, (start, end) in STRESS_PERIODS.items():
        try:
            period = prices.loc[start:end]
            if period.empty or len(period) < 2:
                results[name] = {"error": "Insufficient data"}
                continue
            port_ret = 0
            for i, t in enumerate(available):
                if t in period.columns and len(period[t].dropna()) >= 2:
                    t_ret = (period[t].dropna().iloc[-1] / period[t].dropna().iloc[0] - 1)
                    port_ret += w_avail[i] * t_ret

            spy_ret = None
            if "SPY" in period.columns and len(period["SPY"].dropna()) >= 2:
                spy_ret = round((period["SPY"].dropna().iloc[-1] / period["SPY"].dropna().iloc[0] - 1) * 100, 2)

            # Recovery: find when portfolio recovered to pre-period level after end date
            recovery_days = None
            try:
                pre_level = prices.loc[:start][available].iloc[-1]
                post = prices.loc[end:]
                port_vals_post = (post[available] * w_avail).sum(axis=1)
                pre_val = (pre_level * w_avail).sum()
                recovered = port_vals_post[port_vals_post >= pre_val]
                if not recovered.empty:
                    recovery_days = (recovered.index[0] - pd.Timestamp(end)).days
            except:
                pass

            results[name] = {
                "portfolio_return": round(port_ret * 100, 2),
                "spy_return": spy_ret,
                "recovery_days": recovery_days,
            }
        except Exception as e:
            results[name] = {"error": str(e)}
    return results


def step7_optimization(tickers, weights, prices):
    from pypfopt import expected_returns, risk_models, EfficientFrontier

    available = [t for t in tickers if t in prices.columns]
    cutoff = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")
    p = prices.loc[cutoff:][available].dropna()
    if len(p) < 60:
        return {"error": "Insufficient price data for optimization"}

    mu = expected_returns.mean_historical_return(p)
    S = risk_models.sample_cov(p)
    rf = get_risk_free_rate()

    current_w = {t: weights[tickers.index(t)] / 100 for t in available}
    # Normalize
    total_w = sum(current_w.values())
    current_w = {t: v / total_w for t, v in current_w.items()}

    # Current Sharpe
    curr_ret = sum(mu[t] * current_w[t] for t in available)
    curr_vol = np.sqrt(np.dot(list(current_w.values()), np.dot(S.loc[available, available], list(current_w.values()))))
    curr_sharpe = round((curr_ret - rf) / curr_vol, 3) if curr_vol > 0 else 0

    # Max Sharpe
    try:
        ef = EfficientFrontier(mu, S)
        ef.max_sharpe(risk_free_rate=rf)
        max_sharpe_w = ef.clean_weights()
        perf = ef.portfolio_performance(risk_free_rate=rf)
        max_sharpe_ret, max_sharpe_vol, max_sharpe_ratio = perf
    except Exception as e:
        max_sharpe_w = {}
        max_sharpe_ratio = None

    # Min Vol
    try:
        ef2 = EfficientFrontier(mu, S)
        ef2.min_volatility()
        min_vol_w = ef2.clean_weights()
        perf2 = ef2.portfolio_performance(risk_free_rate=rf)
        min_vol_ret, min_vol_vol, min_vol_sharpe = perf2
    except Exception as e:
        min_vol_w = {}
        min_vol_sharpe = None

    # Suggestions
    suggestions = []
    if max_sharpe_w:
        diffs = [(t, current_w.get(t, 0) * 100, max_sharpe_w.get(t, 0) * 100) for t in available]
        diffs.sort(key=lambda x: abs(x[2] - x[1]), reverse=True)
        for t, curr, opt in diffs[:3]:
            if opt > curr:
                suggestions.append(f"Increase {t} from {curr:.1f}% to {opt:.1f}%")
            else:
                suggestions.append(f"Reduce {t} from {curr:.1f}% to {opt:.1f}%")

    return {
        "current_sharpe": curr_sharpe,
        "max_sharpe": round(max_sharpe_ratio, 3) if max_sharpe_ratio else None,
        "min_vol_sharpe": round(min_vol_sharpe, 3) if min_vol_sharpe else None,
        "current_weights": {t: round(v * 100, 1) for t, v in current_w.items()},
        "max_sharpe_weights": {t: round(v * 100, 1) for t, v in max_sharpe_w.items() if v > 0.001},
        "min_vol_weights": {t: round(v * 100, 1) for t, v in min_vol_w.items() if v > 0.001},
        "suggestions": suggestions,
    }


def format_markdown(tickers, weights, alloc, holdings, risk, cost, income, stress, optim):
    lines = []
    lines.append("# 📊 Portfolio Analysis Report")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Holdings:** {', '.join(tickers)}")
    lines.append("")

    # Step 1
    lines.append("## 1. Allocation Breakdown")
    lines.append("")
    lines.append("### Sector Allocation")
    for s, v in sorted(alloc["sectors"].items(), key=lambda x: -x[1]):
        flag = " ⚠️ CONCENTRATED" if s in alloc["sector_flags"] else ""
        lines.append(f"- **{s}:** {v:.1f}%{flag}")

    lines.append("")
    lines.append("### Geographic Exposure")
    lines.append(f"- 🇺🇸 Domestic: {alloc['domestic_pct']}%")
    lines.append(f"- 🌍 International: {alloc['international_pct']}%")

    lines.append("")
    lines.append("### Market Cap")
    for c, v in sorted(alloc["market_cap"].items(), key=lambda x: -x[1]):
        lines.append(f"- {c}: {v:.1f}%")

    lines.append("")
    lines.append("### Investment Style")
    for s, v in sorted(alloc["styles"].items(), key=lambda x: -x[1]):
        lines.append(f"- {s}: {v:.1f}%")

    # Step 2
    lines.append("")
    lines.append("## 2. Holdings Analysis")
    lines.append("")
    lines.append("| Ticker | Weight | Cap | Style |")
    lines.append("|--------|--------|-----|-------|")
    for t, w in holdings["display"]:
        flag = " ⚠️" if t in holdings["concentrated"] else ""
        cap = alloc["cap_detail"].get(t, "?")
        style = alloc["style_detail"].get(t, "?")
        lines.append(f"| {t} | {w:.1f}%{flag} | {cap} | {style} |")
    if holdings["total"] > 10:
        lines.append(f"\n*Showing top 10 of {holdings['total']} holdings*")
    if holdings["concentrated"]:
        lines.append(f"\n⚠️ **Concentrated positions (>10%):** {', '.join(holdings['concentrated'])}")

    # Step 3
    lines.append("")
    lines.append("## 3. Risk Metrics")
    lines.append("")
    lines.append(f"- **Beta (vs SPY):** {risk['beta']}")
    lines.append(f"- **Annualized Return:** {risk['annualized_return']}%")
    lines.append(f"- **Annualized Volatility:** {risk['annualized_volatility']}%")
    lines.append(f"- **Max Drawdown:** {risk['max_drawdown']}% ({risk['max_dd_start']} → {risk['max_dd_end']})")
    lines.append(f"- **Sharpe Ratio:** {risk['sharpe']} (rf={risk['risk_free_rate']}%)")
    lines.append(f"- **Sortino Ratio:** {risk['sortino']}")

    lines.append("")
    lines.append("### Correlation Matrix")
    tks = list(risk["correlation"].keys())
    lines.append("| | " + " | ".join(tks) + " |")
    lines.append("|" + "---|" * (len(tks) + 1))
    for t in tks:
        row = [str(risk["correlation"][t][t2]) for t2 in tks]
        lines.append(f"| **{t}** | " + " | ".join(row) + " |")
    if risk["high_correlation_pairs"]:
        lines.append("")
        lines.append("⚠️ **Highly correlated pairs (>0.8) — not truly diversified:**")
        for t1, t2, c in risk["high_correlation_pairs"]:
            lines.append(f"- {t1} ↔ {t2}: {c}")

    # Step 4
    lines.append("")
    lines.append("## 4. Cost Analysis")
    lines.append("")
    has_etf = any(v is not None for v in cost["expense_ratios"].values())
    if has_etf:
        for t, er in cost["expense_ratios"].items():
            if er is not None:
                lines.append(f"- {t}: {er*100:.2f}%")
            else:
                lines.append(f"- {t}: no expense ratio (direct equity)")
        lines.append(f"\n**Weighted Avg ER:** {cost['weighted_avg_er']}%")
        lines.append(f"- Annual cost on $10K: ${cost['annual_cost_10k']}")
        lines.append(f"- Annual cost on $50K: ${cost['annual_cost_50k']}")
        lines.append(f"- Annual cost on $100K: ${cost['annual_cost_100k']}")
    else:
        lines.append("All holdings are direct equities — no expense ratios apply.")

    # Step 5
    lines.append("")
    lines.append("## 5. Income Analysis")
    lines.append("")
    for t, y in income["dividend_yields"].items():
        lines.append(f"- {t}: {y}%")
    lines.append(f"\n**Blended Yield:** {income['blended_yield']}%")
    lines.append(f"- Annual income on $10K: ${income['annual_income_10k']}")
    lines.append(f"- Annual income on $50K: ${income['annual_income_50k']}")
    lines.append(f"- Annual income on $100K: ${income['annual_income_100k']}")
    if income["non_payers"]:
        lines.append(f"\n*Non-dividend payers: {', '.join(income['non_payers'])}*")

    # Step 6
    lines.append("")
    lines.append("## 6. Stress Testing")
    lines.append("")
    for name, data in stress.items():
        lines.append(f"### {name}")
        if "error" in data:
            lines.append(f"  ⚠ {data['error']}")
        else:
            lines.append(f"- Portfolio return: **{data['portfolio_return']}%**")
            if data.get("spy_return") is not None:
                lines.append(f"- SPY return: {data['spy_return']}%")
            if data.get("recovery_days") is not None:
                lines.append(f"- Recovery: {data['recovery_days']} days after trough")
        lines.append("")

    # Step 7
    lines.append("## 7. Portfolio Optimization")
    lines.append("")
    if "error" in optim:
        lines.append(f"⚠ {optim['error']}")
    else:
        lines.append(f"**Current Sharpe:** {optim['current_sharpe']}")
        lines.append(f"**Max Sharpe (optimal):** {optim['max_sharpe']}")
        lines.append(f"**Min Volatility Sharpe:** {optim['min_vol_sharpe']}")
        lines.append("")
        lines.append("| Ticker | Current | Max Sharpe | Min Vol |")
        lines.append("|--------|---------|------------|---------|")
        all_t = set(list(optim["current_weights"].keys()) + list(optim["max_sharpe_weights"].keys()) + list(optim["min_vol_weights"].keys()))
        for t in sorted(all_t):
            c = optim["current_weights"].get(t, 0)
            ms = optim["max_sharpe_weights"].get(t, 0)
            mv = optim["min_vol_weights"].get(t, 0)
            lines.append(f"| {t} | {c:.1f}% | {ms:.1f}% | {mv:.1f}% |")
        if optim["suggestions"]:
            lines.append("")
            lines.append("### 💡 Suggested Changes")
            for i, s in enumerate(optim["suggestions"], 1):
                lines.append(f"{i}. {s}")

    lines.append("")
    lines.append("---")
    lines.append("*Data: yfinance, ffn, PyPortfolioOpt | Analysis is informational, not financial advice.*")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Portfolio Analyzer")
    parser.add_argument("--tickers", help="Comma-separated tickers")
    parser.add_argument("--weights", help="Comma-separated weights (%%)")
    parser.add_argument("--portfolio", help="Portfolio name from SQLite DB")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.portfolio:
        tickers, weights = get_portfolio_from_db(args.portfolio)
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
        if args.weights:
            weights = [float(w.strip()) for w in args.weights.split(",")]
        else:
            weights = [100 / len(tickers)] * len(tickers)
        if len(tickers) != len(weights):
            print("Error: tickers and weights must have same length", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    # Normalize weights
    total_w = sum(weights)
    weights = [w / total_w * 100 for w in weights]

    print("Fetching ticker info...", file=sys.stderr)
    info = fetch_info(tickers)

    print("Downloading price history...", file=sys.stderr)
    prices = fetch_prices(tickers)

    print("Analyzing allocation...", file=sys.stderr)
    alloc = step1_allocation(tickers, weights, info)

    print("Analyzing holdings...", file=sys.stderr)
    hold = step2_holdings(tickers, weights, info)

    print("Calculating risk metrics...", file=sys.stderr)
    risk = step3_risk(tickers, weights, prices)

    print("Analyzing costs...", file=sys.stderr)
    cost = step4_cost(tickers, weights, info)

    print("Analyzing income...", file=sys.stderr)
    income = step5_income(tickers, weights, info)

    print("Running stress tests...", file=sys.stderr)
    stress = step6_stress(tickers, weights, prices)

    print("Optimizing portfolio...", file=sys.stderr)
    optim = step7_optimization(tickers, weights, prices)

    if args.json:
        output = {
            "tickers": tickers,
            "weights": weights,
            "allocation": alloc,
            "holdings": hold,
            "risk": risk,
            "cost": cost,
            "income": income,
            "stress": stress,
            "optimization": optim,
        }
        # Convert non-serializable
        print(json.dumps(output, indent=2, default=str))
    else:
        print(format_markdown(tickers, weights, alloc, hold, risk, cost, income, stress, optim))


if __name__ == "__main__":
    main()
