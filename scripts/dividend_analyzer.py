#!/usr/bin/env python3
"""Dividend Analyzer — Comprehensive dividend/income investment analysis."""

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")


# ── Peer mappings ──
PEER_MAP = {
    "JNJ": ["PG", "KO", "PEP", "ABT", "MRK"],
    "PG": ["JNJ", "KO", "CL", "KMB", "CHD"],
    "KO": ["PEP", "MDLZ", "KDP", "STZ", "MO"],
    "PEP": ["KO", "MDLZ", "KDP", "STZ", "MO"],
    "AAPL": ["MSFT", "GOOG", "AVGO", "CSCO", "TXN"],
    "MSFT": ["AAPL", "GOOG", "AVGO", "CSCO", "ORCL"],
    "ABT": ["JNJ", "MDT", "BDX", "SYK", "BAX"],
    "MRK": ["PFE", "LLY", "ABBV", "BMY", "AMGN"],
    "MO": ["PM", "BTI", "KO", "PEP", "STZ"],
    "T": ["VZ", "TMUS", "CMCSA", "CHTR", "BCE"],
    "VZ": ["T", "TMUS", "CMCSA", "CHTR", "BCE"],
    "XOM": ["CVX", "COP", "EOG", "SLB", "PSX"],
    "CVX": ["XOM", "COP", "EOG", "SLB", "PSX"],
    "O": ["NNN", "WPC", "STOR", "ADC", "EPRT"],
    "MMM": ["HON", "ITW", "EMR", "ETN", "ROK"],
    "IBM": ["CSCO", "ORCL", "ACN", "TXN", "INTC"],
}


def safe_get(info: dict, key: str, default=None):
    v = info.get(key)
    return default if v is None else v


def fmt_pct(v, digits=2):
    if v is None:
        return "N/A"
    return f"{v * 100:.{digits}f}%"


def fmt_money(v, digits=2):
    if v is None:
        return "N/A"
    return f"${v:,.{digits}f}"


def fmt_ratio(v, digits=2):
    if v is None:
        return "N/A"
    return f"{v:.{digits}f}x"


def get_annual_dividends(dividends: pd.Series) -> pd.Series:
    """Group dividends by year, return annual totals."""
    if dividends.empty:
        return pd.Series(dtype=float)
    annual = dividends.groupby(dividends.index.year).sum()
    # Drop current year if incomplete (< 6 months in)
    now = datetime.now()
    if now.month < 7 and now.year in annual.index:
        annual = annual.drop(now.year)
    return annual


def calc_cagr(annual: pd.Series, years: int) -> Optional[float]:
    """CAGR of annual dividend over N years."""
    if len(annual) < years + 1:
        return None
    recent = annual.iloc[-1]
    past = annual.iloc[-(years + 1)]
    if past <= 0 or recent <= 0:
        return None
    return (recent / past) ** (1.0 / years) - 1


def detect_frequency(dividends: pd.Series) -> str:
    if len(dividends) < 4:
        return "Unknown"
    cutoff = pd.Timestamp.now(tz=dividends.index.tz) - pd.DateOffset(years=2)
    recent = dividends[dividends.index >= cutoff]
    if len(recent) < 2:
        return "Unknown"
    avg_gap = recent.index.to_series().diff().dropna().dt.days.median()
    if avg_gap < 45:
        return "Monthly"
    if avg_gap < 100:
        return "Quarterly"
    if avg_gap < 200:
        return "Semi-Annual"
    return "Annual"


def consecutive_increases(annual: pd.Series) -> int:
    """Count consecutive years of dividend increases from most recent going back."""
    if len(annual) < 2:
        return 0
    count = 0
    for i in range(len(annual) - 1, 0, -1):
        if annual.iloc[i] > annual.iloc[i - 1]:
            count += 1
        else:
            break
    return count


def find_cuts_freezes(annual: pd.Series) -> list:
    events = []
    for i in range(1, len(annual)):
        yr = annual.index[i]
        prev = annual.iloc[i - 1]
        cur = annual.iloc[i]
        if prev > 0:
            chg = (cur - prev) / prev
            if chg < -0.01:
                events.append(f"{yr}: Cut {chg*100:.1f}%")
            elif abs(chg) < 0.005:
                events.append(f"{yr}: Freeze")
    return events


def largest_increase(annual: pd.Series) -> Optional[tuple]:
    best_yr, best_pct = None, 0
    for i in range(1, len(annual)):
        prev = annual.iloc[i - 1]
        if prev > 0:
            pct = (annual.iloc[i] - prev) / prev
            if pct > best_pct:
                best_pct = pct
                best_yr = annual.index[i]
    return (best_yr, best_pct) if best_yr else None


def get_fcf_payout(ticker_obj) -> Optional[float]:
    """Dividends paid / FCF from cashflow statement."""
    try:
        cf = ticker_obj.cashflow
        if cf is None or cf.empty:
            return None
        # Find dividends paid row
        div_row = None
        for label in ["Cash Dividends Paid", "Common Stock Dividend Paid",
                       "Payment Of Dividends", "Dividends Paid"]:
            if label in cf.index:
                div_row = label
                break
        # Find FCF components
        ocf_row = None
        for label in ["Operating Cash Flow", "Total Cash From Operating Activities",
                       "Cash Flow From Continuing Operating Activities"]:
            if label in cf.index:
                ocf_row = label
                break
        capex_row = None
        for label in ["Capital Expenditure", "Capital Expenditures"]:
            if label in cf.index:
                capex_row = label
                break
        if ocf_row is None:
            return None
        ocf = cf.loc[ocf_row].iloc[0]
        capex = cf.loc[capex_row].iloc[0] if capex_row else 0
        fcf = ocf + capex  # capex is negative
        if fcf <= 0:
            return None
        if div_row:
            divs = abs(cf.loc[div_row].iloc[0])
        else:
            return None
        return divs / fcf
    except Exception:
        return None


def get_fcf_payout_history(ticker_obj) -> list:
    """Return list of (year, fcf_payout) for available years."""
    try:
        cf = ticker_obj.cashflow
        if cf is None or cf.empty:
            return []
        div_row = ocf_row = capex_row = None
        for label in ["Cash Dividends Paid", "Common Stock Dividend Paid",
                       "Payment Of Dividends", "Dividends Paid"]:
            if label in cf.index:
                div_row = label
                break
        for label in ["Operating Cash Flow", "Total Cash From Operating Activities",
                       "Cash Flow From Continuing Operating Activities"]:
            if label in cf.index:
                ocf_row = label
                break
        for label in ["Capital Expenditure", "Capital Expenditures"]:
            if label in cf.index:
                capex_row = label
                break
        if not (div_row and ocf_row):
            return []
        results = []
        for col in cf.columns:
            try:
                ocf = cf.loc[ocf_row, col]
                capex = cf.loc[capex_row, col] if capex_row else 0
                fcf = ocf + capex
                divs = abs(cf.loc[div_row, col])
                if fcf > 0:
                    yr = col.year if hasattr(col, 'year') else col
                    results.append((yr, divs / fcf))
            except Exception:
                pass
        return results
    except Exception:
        return []


def get_debt_ebitda(info: dict, ticker_obj) -> Optional[float]:
    try:
        total_debt = safe_get(info, "totalDebt")
        if total_debt is None:
            return None
        fin = ticker_obj.financials
        if fin is None or fin.empty:
            return None
        ebitda = safe_get(info, "ebitda")
        if ebitda and ebitda > 0:
            return total_debt / ebitda
        # Try computing from financials
        ebit = None
        for label in ["EBIT", "Operating Income"]:
            if label in fin.index:
                ebit = fin.loc[label].iloc[0]
                break
        da = None
        for label in ["Reconciled Depreciation", "Depreciation And Amortization"]:
            if label in fin.index:
                da = fin.loc[label].iloc[0]
                break
        if ebit is not None:
            ebitda_val = ebit + (da or 0)
            if ebitda_val > 0:
                return total_debt / ebitda_val
        return None
    except Exception:
        return None


def get_interest_coverage(info: dict, ticker_obj) -> Optional[float]:
    try:
        fin = ticker_obj.financials
        if fin is None or fin.empty:
            return None
        ebit = None
        for label in ["EBIT", "Operating Income"]:
            if label in fin.index:
                ebit = fin.loc[label].iloc[0]
                break
        interest = None
        for label in ["Interest Expense", "Net Interest Income"]:
            if label in fin.index:
                val = fin.loc[label].iloc[0]
                interest = abs(val) if val else None
                break
        if ebit and interest and interest > 0:
            return ebit / interest
        return None
    except Exception:
        return None


def get_peers(ticker: str) -> list:
    """Get peer tickers."""
    t = ticker.upper()
    if t in PEER_MAP:
        return PEER_MAP[t]
    # Try finvizfinance for sector peers
    try:
        from finvizfinance.quote import finvizfinance as fvf
        stock = fvf(t)
        fund = stock.ticker_fundament()
        sector = fund.get("Sector", "")
        if sector:
            from finvizfinance.screener.overview import Overview
            scr = Overview()
            scr.set_filter(filters_dict={"Sector": sector, "Dividend Yield": "Over 1%"})
            df = scr.screener_view()
            if df is not None and not df.empty:
                peers = [row for row in df["Ticker"].tolist() if row != t][:5]
                if peers:
                    return peers
    except Exception:
        pass
    return []


def get_peer_metrics(ticker: str) -> dict:
    """Quick metrics for peer comparison."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        annual = get_annual_dividends(t.dividends)
        dy = safe_get(info, "dividendYield")
        if dy and dy > 0.5:
            dy = dy / 100.0
        pr = safe_get(info, "payoutRatio")
        return {
            "ticker": ticker,
            "yield": dy,
            "payout": pr,
            "5yr_growth": calc_cagr(annual, 5),
            "fcf_payout": get_fcf_payout(t),
            "debt_ebitda": get_debt_ebitda(info, t),
        }
    except Exception:
        return {"ticker": ticker}


def drip_projection(initial_investment: float, current_price: float,
                    annual_div_per_share: float, div_growth_rate: float,
                    price_growth_rate: float, years: int) -> list:
    """Year-by-year DRIP projection."""
    if not all([current_price, annual_div_per_share]) or current_price <= 0:
        return []
    shares = initial_investment / current_price
    price = current_price
    div_per_share = annual_div_per_share
    rows = []
    for yr in range(1, years + 1):
        div_per_share *= (1 + div_growth_rate)
        price *= (1 + price_growth_rate)
        annual_income = shares * div_per_share
        shares += annual_income / price  # DRIP reinvestment
        yoc = (shares * div_per_share) / initial_investment
        rows.append({
            "year": yr,
            "shares": round(shares, 2),
            "div_per_share": round(div_per_share, 4),
            "annual_income": round(annual_income, 2),
            "yield_on_cost": round(yoc, 4),
            "portfolio_value": round(shares * price, 2),
        })
    return rows


def analyze_ticker(ticker: str) -> dict:
    """Full dividend analysis for one ticker."""
    result = {"ticker": ticker.upper(), "errors": [], "warnings": []}

    try:
        t = yf.Ticker(ticker)
        info = t.info
        if not info or info.get("regularMarketPrice") is None:
            result["errors"].append(f"Could not fetch data for {ticker}")
            return result
    except Exception as e:
        result["errors"].append(f"Failed to fetch {ticker}: {e}")
        return result

    name = safe_get(info, "shortName", ticker)
    price = safe_get(info, "regularMarketPrice") or safe_get(info, "currentPrice", 0)
    result["name"] = name
    result["price"] = price
    result["sector"] = safe_get(info, "sector", "N/A")
    result["industry"] = safe_get(info, "industry", "N/A")

    # ── Step 1: Current Dividend Profile ──
    div_rate = safe_get(info, "dividendRate")
    div_yield = safe_get(info, "dividendYield")
    # yfinance sometimes returns yield as percentage (2.58) vs fraction (0.0258)
    # yfinance may return yield as percentage (e.g. 2.58 vs 0.0258); >0.5 = likely pct
    if div_yield and div_yield > 0.5:
        div_yield = div_yield / 100.0
    ex_date_ts = safe_get(info, "exDividendDate")
    ex_date = None
    if ex_date_ts:
        try:
            if isinstance(ex_date_ts, (int, float)):
                ex_date = datetime.fromtimestamp(ex_date_ts, tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                ex_date = str(ex_date_ts)
        except Exception:
            ex_date = str(ex_date_ts)

    dividends = t.dividends
    freq = detect_frequency(dividends)

    result["profile"] = {
        "annual_dividend": div_rate,
        "yield": div_yield,
        "frequency": freq,
        "ex_dividend_date": ex_date,
    }

    # ── Step 2: Growth Track Record ──
    annual = get_annual_dividends(dividends)
    growth = {}
    for n, label in [(1, "1yr"), (3, "3yr"), (5, "5yr"), (10, "10yr")]:
        growth[label] = calc_cagr(annual, n)

    consec = consecutive_increases(annual)
    cuts = find_cuts_freezes(annual)
    largest = largest_increase(annual)

    status = None
    if consec >= 50:
        status = "Dividend King (50+ years)"
    elif consec >= 25:
        status = "Dividend Aristocrat (25+ years)"

    result["growth"] = {
        "cagr": growth,
        "consecutive_increases": consec,
        "status": status,
        "cuts_freezes": cuts,
        "largest_increase": {"year": largest[0], "pct": largest[1]} if largest else None,
        "years_of_data": len(annual),
    }

    # ── Step 3: Sustainability ──
    payout_ratio = safe_get(info, "payoutRatio")
    # Don't normalize payout ratio - values >1 (>100%) are legitimate
    fcf_payout = get_fcf_payout(t)
    fcf_history = get_fcf_payout_history(t)
    debt_ebitda = get_debt_ebitda(info, t)
    interest_cov = get_interest_coverage(info, t)

    # Payout trend
    payout_trend = "N/A"
    if len(fcf_history) >= 3:
        recent = [x[1] for x in fcf_history[:3]]
        if recent[0] > recent[-1]:
            payout_trend = "Rising (worsening)"
        elif recent[0] < recent[-1]:
            payout_trend = "Falling (improving)"
        else:
            payout_trend = "Stable"

    flags = []
    if payout_ratio and payout_ratio > 0.75:
        flags.append(f"⚠️ High earnings payout ratio: {fmt_pct(payout_ratio)}")
    if fcf_payout and fcf_payout > 0.75:
        flags.append(f"⚠️ High FCF payout ratio: {fmt_pct(fcf_payout)}")

    result["sustainability"] = {
        "earnings_payout": payout_ratio,
        "fcf_payout": fcf_payout,
        "fcf_payout_history": fcf_history,
        "payout_trend": payout_trend,
        "debt_ebitda": debt_ebitda,
        "interest_coverage": interest_cov,
        "flags": flags,
    }

    # ── Step 4: Peer Comparison ──
    peers = get_peers(ticker)
    peer_data = []
    if peers:
        for p in peers[:5]:
            pm = get_peer_metrics(p)
            peer_data.append(pm)
    own_metrics = {
        "ticker": ticker.upper(),
        "yield": div_yield,
        "payout": payout_ratio,
        "5yr_growth": growth.get("5yr"),
        "fcf_payout": fcf_payout,
        "debt_ebitda": debt_ebitda,
    }
    result["peers"] = {"own": own_metrics, "peers": peer_data}

    # ── Step 5: DRIP Projection ──
    div_growth_5yr = growth.get("5yr") or 0.03
    price_growth = 0.05  # assume 5% price appreciation
    projections = {}
    for amt in [10000, 50000, 100000]:
        if price and price > 0 and div_rate:
            proj = drip_projection(amt, price, div_rate, div_growth_5yr, price_growth, 20)
            projections[amt] = proj
    result["drip"] = {
        "assumptions": {
            "div_growth_rate": div_growth_5yr,
            "price_growth_rate": price_growth,
            "current_price": price,
            "current_annual_div": div_rate,
        },
        "projections": projections,
    }

    # ── Step 6: Risk Assessment ──
    risks = []
    earnings_buffer = None
    if payout_ratio and payout_ratio > 0:
        earnings_buffer = max(0, (1 - payout_ratio) / payout_ratio)
        if payout_ratio > 0.90:
            risks.append("Payout ratio very close to 100% — minimal buffer")
        elif payout_ratio > 0.75:
            risks.append("Elevated payout ratio — limited room for earnings decline")

    if fcf_history and len(fcf_history) >= 2:
        if fcf_history[0][1] > fcf_history[-1][1] * 1.2:
            risks.append("FCF payout ratio has been rising — watch for cash flow pressure")

    if debt_ebitda and debt_ebitda > 3.5:
        risks.append(f"High leverage (Debt/EBITDA: {fmt_ratio(debt_ebitda)}) — debt service could crowd out dividends")

    commitment = "Unknown"
    if payout_ratio and payout_ratio < 0.50:
        commitment = "Strong implicit commitment (conservative payout < 50%)"
    elif payout_ratio and payout_ratio < 0.65:
        commitment = "Moderate commitment (payout 50-65%)"
    elif payout_ratio and payout_ratio < 0.80:
        commitment = "Watch closely (payout 65-80%)"

    result["risk"] = {
        "risks": risks,
        "earnings_buffer": earnings_buffer,
        "commitment": commitment,
    }

    # ── Verdict ──
    score = 0
    # Yield
    if div_yield and div_yield > 0.015:
        score += 1
    # Growth
    if growth.get("5yr") and growth["5yr"] > 0.03:
        score += 1
    # Consecutive increases
    if consec >= 10:
        score += 1
    if consec >= 25:
        score += 1
    # Payout safety
    if payout_ratio and payout_ratio < 0.65:
        score += 1
    if fcf_payout and fcf_payout < 0.65:
        score += 1
    # Low debt
    if debt_ebitda and debt_ebitda < 2.5:
        score += 1
    # No cuts
    if not cuts:
        score += 1

    if score >= 6:
        verdict = "Strong Income Stock"
    elif score >= 3:
        verdict = "Moderate Income Stock"
    else:
        verdict = "Risky Income Stock"

    # Best suited for
    if div_yield and div_yield > 0.035 and (not growth.get("5yr") or growth["5yr"] < 0.04):
        suited = "Income investors (high current yield)"
    elif growth.get("5yr") and growth["5yr"] > 0.06:
        suited = "Growth-oriented dividend investors"
    else:
        suited = "Total Return investors (balanced yield + growth)"

    explanation_parts = []
    if div_yield:
        explanation_parts.append(f"yields {fmt_pct(div_yield)}")
    if consec:
        explanation_parts.append(f"{consec} consecutive years of increases")
    if payout_ratio:
        explanation_parts.append(f"payout ratio of {fmt_pct(payout_ratio)}")

    result["verdict"] = {
        "rating": verdict,
        "explanation": f"{name} {', '.join(explanation_parts)}.",
        "suited_for": suited,
        "score": score,
    }

    return result


def format_markdown(data: dict) -> str:
    """Format analysis as clean markdown."""
    lines = []
    t = data["ticker"]
    name = data.get("name", t)

    if data.get("errors"):
        lines.append(f"# ❌ {t} — Error")
        for e in data["errors"]:
            lines.append(f"- {e}")
        return "\n".join(lines)

    lines.append(f"# 📊 Dividend Analysis: {name} ({t})")
    lines.append(f"**Price:** {fmt_money(data.get('price'))} | **Sector:** {data.get('sector')} | **Industry:** {data.get('industry')}")
    lines.append("")

    # Step 1
    p = data.get("profile", {})
    lines.append("## 1. Current Dividend Profile")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Annual Dividend/Share | {fmt_money(p.get('annual_dividend'))} |")
    lines.append(f"| Current Yield | {fmt_pct(p.get('yield'))} |")
    lines.append(f"| Payment Frequency | {p.get('frequency', 'N/A')} |")
    lines.append(f"| Ex-Dividend Date | {p.get('ex_dividend_date', 'N/A')} |")
    lines.append("")

    # Step 2
    g = data.get("growth", {})
    cagr = g.get("cagr", {})
    lines.append("## 2. Dividend Growth Track Record")
    lines.append(f"**Data:** {g.get('years_of_data', 'N/A')} years of dividend history")
    lines.append("")
    lines.append("| Period | CAGR |")
    lines.append("|--------|------|")
    for period in ["1yr", "3yr", "5yr", "10yr"]:
        lines.append(f"| {period} | {fmt_pct(cagr.get(period))} |")
    lines.append("")
    lines.append(f"- **Consecutive Years of Increases:** {g.get('consecutive_increases', 0)}")
    if g.get("status"):
        lines.append(f"- **🏆 {g['status']}**")
    lg = g.get("largest_increase")
    if lg:
        lines.append(f"- **Largest Single-Year Increase:** {fmt_pct(lg['pct'])} ({lg['year']})")
    cuts = g.get("cuts_freezes", [])
    if cuts:
        lines.append(f"- **⚠️ Cuts/Freezes:** {', '.join(cuts)}")
    else:
        lines.append("- **No dividend cuts or freezes detected**")
    lines.append("")

    # Step 3
    s = data.get("sustainability", {})
    lines.append("## 3. Sustainability Check")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Earnings Payout Ratio | {fmt_pct(s.get('earnings_payout'))} |")
    lines.append(f"| FCF Payout Ratio | {fmt_pct(s.get('fcf_payout'))} |")
    lines.append(f"| Payout Trend | {s.get('payout_trend', 'N/A')} |")
    lines.append(f"| Debt/EBITDA | {fmt_ratio(s.get('debt_ebitda'))} |")
    lines.append(f"| Interest Coverage | {fmt_ratio(s.get('interest_coverage'))} |")
    flags = s.get("flags", [])
    if flags:
        lines.append("")
        for f in flags:
            lines.append(f"- {f}")
    lines.append("")

    # Step 4
    peers = data.get("peers", {})
    peer_list = peers.get("peers", [])
    if peer_list:
        own = peers.get("own", {})
        lines.append("## 4. Peer Comparison")
        lines.append("| Ticker | Yield | 5yr Growth | Payout | FCF Payout | Debt/EBITDA |")
        lines.append("|--------|-------|------------|--------|------------|-------------|")
        for row in [own] + peer_list:
            lines.append(f"| **{row.get('ticker', '?')}** | {fmt_pct(row.get('yield'))} | {fmt_pct(row.get('5yr_growth'))} | {fmt_pct(row.get('payout'))} | {fmt_pct(row.get('fcf_payout'))} | {fmt_ratio(row.get('debt_ebitda'))} |")

        # Rankings
        all_data = [own] + peer_list
        valid_yield = [(d["ticker"], d["yield"]) for d in all_data if d.get("yield")]
        valid_growth = [(d["ticker"], d["5yr_growth"]) for d in all_data if d.get("5yr_growth")]
        valid_payout = [(d["ticker"], d.get("payout") or 999) for d in all_data if d.get("payout") is not None]

        lines.append("")
        if valid_yield:
            best_y = max(valid_yield, key=lambda x: x[1])
            lines.append(f"- **Best Yield:** {best_y[0]} ({fmt_pct(best_y[1])})")
        if valid_growth:
            best_g = max(valid_growth, key=lambda x: x[1])
            lines.append(f"- **Best Growth:** {best_g[0]} ({fmt_pct(best_g[1])})")
        if valid_payout:
            best_s = min(valid_payout, key=lambda x: x[1])
            lines.append(f"- **Most Sustainable:** {best_s[0]} ({fmt_pct(best_s[1])} payout)")
    lines.append("")

    # Step 5
    drip = data.get("drip", {})
    assumptions = drip.get("assumptions", {})
    proj_10k = drip.get("projections", {}).get(10000, [])
    if proj_10k:
        lines.append("## 5. DRIP Income Projection")
        lines.append(f"**Assumptions:** Current price {fmt_money(assumptions.get('current_price'))}, "
                      f"Annual div {fmt_money(assumptions.get('current_annual_div'))}, "
                      f"Div growth {fmt_pct(assumptions.get('div_growth_rate'))}/yr, "
                      f"Price growth {fmt_pct(assumptions.get('price_growth_rate'))}/yr")
        lines.append("")
        lines.append("### $10,000 Initial Investment")
        lines.append("| Year | Shares | Annual Income | Yield on Cost | Portfolio Value |")
        lines.append("|------|--------|---------------|---------------|-----------------|")
        for row in proj_10k:
            yr = row["year"]
            if yr in [1, 2, 3, 5, 10, 15, 20]:
                lines.append(f"| {yr} | {row['shares']} | {fmt_money(row['annual_income'])} | {fmt_pct(row['yield_on_cost'])} | {fmt_money(row['portfolio_value'])} |")

        # Summary for larger amounts
        lines.append("")
        lines.append("### Summary at Other Investment Amounts")
        lines.append("| Investment | Yr 5 Income | Yr 10 Income | Yr 20 Income | Yr 20 Value |")
        lines.append("|------------|-------------|--------------|--------------|-------------|")
        for amt in [10000, 50000, 100000]:
            proj = drip.get("projections", {}).get(amt, [])
            if proj:
                y5 = proj[4] if len(proj) >= 5 else {}
                y10 = proj[9] if len(proj) >= 10 else {}
                y20 = proj[19] if len(proj) >= 20 else {}
                lines.append(f"| {fmt_money(amt, 0)} | {fmt_money(y5.get('annual_income'))} | {fmt_money(y10.get('annual_income'))} | {fmt_money(y20.get('annual_income'))} | {fmt_money(y20.get('portfolio_value'))} |")
    lines.append("")

    # Step 6
    risk = data.get("risk", {})
    lines.append("## 6. Risk Assessment")
    risk_items = risk.get("risks", [])
    if risk_items:
        for r in risk_items:
            lines.append(f"- ⚠️ {r}")
    else:
        lines.append("- ✅ No major risk flags detected")

    eb = risk.get("earnings_buffer")
    if eb is not None:
        lines.append(f"- **Earnings Buffer:** Earnings could decline {fmt_pct(eb)} before payout exceeds 100%")
    lines.append(f"- **Management Commitment:** {risk.get('commitment', 'N/A')}")
    lines.append("")

    # Verdict
    v = data.get("verdict", {})
    rating = v.get("rating", "N/A")
    emoji = "🟢" if "Strong" in rating else ("🟡" if "Moderate" in rating else "🔴")
    lines.append(f"## {emoji} Verdict: {rating}")
    lines.append(f"{v.get('explanation', '')}")
    lines.append(f"**Best suited for:** {v.get('suited_for', 'N/A')}")
    lines.append("")
    lines.append("---")
    lines.append("*Data: yfinance, finvizfinance | Analysis is informational, not financial advice.*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Dividend/Income Investment Analyzer")
    parser.add_argument("tickers", nargs="+", help="Stock ticker(s) to analyze")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of markdown")
    args = parser.parse_args()

    results = []
    for ticker in args.tickers:
        print(f"Analyzing {ticker.upper()}...", file=sys.stderr)
        data = analyze_ticker(ticker)
        results.append(data)

    if args.json:
        # Clean up non-serializable items
        print(json.dumps(results, indent=2, default=str))
    else:
        for data in results:
            print(format_markdown(data))
            print()


if __name__ == "__main__":
    main()
