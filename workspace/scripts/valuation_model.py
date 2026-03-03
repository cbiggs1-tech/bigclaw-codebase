#!/usr/bin/env python3
"""
Multi-Method Stock Valuation Model
Usage:
  python3 valuation_model.py TSLA
  python3 valuation_model.py NVDA AAPL --json
"""

import argparse
import json
import sys
import warnings
import traceback
from datetime import datetime

import numpy as np
import yfinance as yf

warnings.filterwarnings("ignore")

# Peer mappings for major stocks
PEER_MAP = {
    "TSLA": ["GM", "F", "RIVN", "NIO", "LCID"],
    "AAPL": ["MSFT", "GOOGL", "AMZN", "META"],
    "MSFT": ["AAPL", "GOOGL", "AMZN", "META"],
    "GOOGL": ["AAPL", "MSFT", "AMZN", "META"],
    "GOOG": ["AAPL", "MSFT", "AMZN", "META"],
    "AMZN": ["AAPL", "MSFT", "GOOGL", "META"],
    "META": ["AAPL", "MSFT", "GOOGL", "AMZN"],
    "NVDA": ["AMD", "INTC", "AVGO", "QCOM"],
    "AMD": ["NVDA", "INTC", "AVGO", "QCOM"],
    "INTC": ["NVDA", "AMD", "AVGO", "QCOM"],
    "NFLX": ["DIS", "WBD", "PARA", "CMCSA"],
    "JPM": ["BAC", "GS", "MS", "C", "WFC"],
    "BAC": ["JPM", "GS", "MS", "C", "WFC"],
    "V": ["MA", "PYPL", "SQ", "AXP"],
    "MA": ["V", "PYPL", "SQ", "AXP"],
    "JNJ": ["PFE", "UNH", "ABBV", "MRK", "LLY"],
    "XOM": ["CVX", "COP", "SLB", "EOG"],
    "WMT": ["TGT", "COST", "AMZN", "KR"],
    "DIS": ["NFLX", "WBD", "PARA", "CMCSA"],
    "BA": ["LMT", "RTX", "GD", "NOC"],
    "COIN": ["HOOD", "MARA", "RIOT", "SQ"],
    "PLTR": ["SNOW", "AI", "DDOG", "NET"],
    "CRM": ["NOW", "ORCL", "SAP", "WDAY"],
    "UBER": ["LYFT", "DASH", "ABNB", "GRAB"],
}


def safe_get(d, *keys, default=None):
    """Safely traverse nested dict/object attributes."""
    val = d
    for k in keys:
        if val is None:
            return default
        if isinstance(val, dict):
            val = val.get(k, None)
        else:
            val = getattr(val, k, None)
    return val if val is not None else default


def fmt_price(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"${v:,.2f}"


def fmt_pct(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{v:,.1f}%"


def fmt_num(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    if abs(v) >= 1e12:
        return f"${v/1e12:,.2f}T"
    if abs(v) >= 1e9:
        return f"${v/1e9:,.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:,.2f}M"
    return f"${v:,.0f}"


def fmt_x(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "N/A"
    return f"{v:,.1f}x"


def get_risk_free_rate():
    """Get 10-year Treasury yield from ^TNX."""
    try:
        tnx = yf.Ticker("^TNX")
        hist = tnx.history(period="5d")
        if not hist.empty:
            rate = hist["Close"].iloc[-1]
            if rate > 1:  # comes as percentage
                rate = rate / 100.0
            return rate
    except:
        pass
    return 0.04  # fallback


def get_fcf_data(tk, info):
    """Extract FCF and revenue data from yfinance ticker."""
    result = {"fcf": None, "fcf_history": [], "revenue_history": [], "fcf_margins": []}

    try:
        cf = tk.cashflow
        fs = tk.financials
        if cf is None or cf.empty:
            return result

        # Try FreeCashFlow row first, then Operating - CapEx
        fcf_row = None
        for label in ["Free Cash Flow", "FreeCashFlow"]:
            if label in cf.index:
                fcf_row = cf.loc[label]
                break

        if fcf_row is None:
            op_cf = None
            for label in ["Operating Cash Flow", "Total Cash From Operating Activities"]:
                if label in cf.index:
                    op_cf = cf.loc[label]
                    break
            capex = None
            for label in ["Capital Expenditure", "Capital Expenditures"]:
                if label in cf.index:
                    capex = cf.loc[label]
                    break
            if op_cf is not None and capex is not None:
                fcf_row = op_cf + capex  # capex is typically negative

        if fcf_row is not None:
            vals = fcf_row.dropna().values
            result["fcf"] = float(vals[0]) if len(vals) > 0 else None
            result["fcf_history"] = [float(v) for v in vals[:4]]

        # Revenue
        if fs is not None and not fs.empty:
            for label in ["Total Revenue", "Revenue"]:
                if label in fs.index:
                    rev = fs.loc[label].dropna().values
                    result["revenue_history"] = [float(v) for v in rev[:4]]
                    break

        # FCF margins
        if result["fcf_history"] and result["revenue_history"]:
            n = min(len(result["fcf_history"]), len(result["revenue_history"]))
            result["fcf_margins"] = [
                result["fcf_history"][i] / result["revenue_history"][i]
                for i in range(n)
                if result["revenue_history"][i] != 0
            ]

    except Exception as e:
        result["error"] = str(e)

    return result


def get_growth_estimates(tk, info):
    """Get analyst growth estimates."""
    growth = {"yr1": None, "yr2": None, "hist_cagr": None}
    try:
        ge = tk.growth_estimates
        if ge is not None and not ge.empty:
            # Try to extract next year growth
            for col in ge.columns:
                if "stock" in str(col).lower() or tk.ticker in str(col):
                    vals = ge[col].dropna().values
                    if len(vals) >= 2:
                        growth["yr1"] = float(vals[0]) if not np.isnan(vals[0]) else None
                        growth["yr2"] = float(vals[1]) if not np.isnan(vals[1]) else None
                    elif len(vals) == 1:
                        growth["yr1"] = float(vals[0]) if not np.isnan(vals[0]) else None
    except:
        pass

    # Revenue growth estimates
    try:
        re = tk.revenue_estimate
        if re is not None and not re.empty:
            if "avg" in re.index:
                vals = re.loc["avg"].dropna().values
                # These are revenue estimates, not growth rates - compute growth from current
                rev = safe_get(info, "totalRevenue")
                if rev and len(vals) >= 1:
                    yr1_rev = float(vals[0]) if len(vals) > 0 else None
                    yr2_rev = float(vals[1]) if len(vals) > 1 else None
                    if yr1_rev and rev:
                        g1 = (yr1_rev / rev) - 1 if rev > 0 else None
                        if g1 is not None and growth["yr1"] is None:
                            growth["yr1"] = g1
                    if yr2_rev and yr1_rev:
                        g2 = (yr2_rev / yr1_rev) - 1 if yr1_rev > 0 else None
                        if g2 is not None and growth["yr2"] is None:
                            growth["yr2"] = g2
    except:
        pass

    # Fallback: use earnings growth from info
    if growth["yr1"] is None:
        eg = safe_get(info, "earningsGrowth")
        rg = safe_get(info, "revenueGrowth")
        if rg is not None:
            growth["yr1"] = rg
        elif eg is not None:
            growth["yr1"] = eg

    return growth


def calc_wacc(info, risk_free):
    """Calculate WACC."""
    beta = safe_get(info, "beta") or 1.0
    erp = 0.055  # equity risk premium
    cost_of_equity = risk_free + beta * erp

    # Cost of debt (approximate)
    total_debt = safe_get(info, "totalDebt") or 0
    market_cap = safe_get(info, "marketCap") or 1

    # Interest expense - try to get from financials
    cost_of_debt = 0.05  # default
    interest_exp = None

    if total_debt > 0 and interest_exp:
        cost_of_debt = abs(interest_exp) / total_debt
    elif total_debt > 0:
        cost_of_debt = 0.05  # assumption

    tax_rate = 0.21  # corporate tax rate assumption

    total_capital = market_cap + total_debt
    we = market_cap / total_capital if total_capital > 0 else 1.0
    wd = total_debt / total_capital if total_capital > 0 else 0.0

    wacc = we * cost_of_equity + wd * cost_of_debt * (1 - tax_rate)

    return {
        "wacc": wacc,
        "cost_of_equity": cost_of_equity,
        "cost_of_debt": cost_of_debt,
        "risk_free": risk_free,
        "beta": beta,
        "erp": erp,
        "tax_rate": tax_rate,
        "we": we,
        "wd": wd,
        "market_cap": market_cap,
        "total_debt": total_debt,
    }


def run_dcf(fcf, growth_rates, fcf_margin_adj, wacc, terminal_growth, shares, revenue=None):
    """Run DCF model. Returns implied price per share."""
    if fcf is None or fcf <= 0:
        # If FCF negative, try using revenue * margin
        if revenue and fcf is not None:
            # Use absolute FCF even if negative for projection with growth
            pass
        else:
            return None

    projected = []
    current_fcf = abs(fcf) if fcf > 0 else abs(fcf) * 0.5  # dampen negative FCF
    if fcf > 0:
        current_fcf = fcf

    for i, g in enumerate(growth_rates):
        current_fcf = current_fcf * (1 + g)
        if fcf_margin_adj and i >= 2:
            current_fcf *= (1 + fcf_margin_adj)
        projected.append(current_fcf)

    if not projected or wacc <= terminal_growth:
        return None

    terminal_value = projected[-1] * (1 + terminal_growth) / (wacc - terminal_growth)

    pv_fcfs = sum(projected[i] / (1 + wacc) ** (i + 1) for i in range(len(projected)))
    pv_terminal = terminal_value / (1 + wacc) ** len(projected)

    enterprise_value = pv_fcfs + pv_terminal

    if shares and shares > 0:
        return enterprise_value / shares
    return None


def get_peers(ticker, info):
    """Get peer tickers."""
    if ticker.upper() in PEER_MAP:
        return PEER_MAP[ticker.upper()]

    # Try finvizfinance screener
    try:
        from finvizfinance.screener.overview import Overview
        industry = safe_get(info, "industry")
        if industry:
            foverview = Overview()
            filters_dict = {"Industry": industry}
            foverview.set_filter(filters_dict=filters_dict)
            df = foverview.screener_view()
            if df is not None and not df.empty:
                peers = [t for t in df["Ticker"].tolist() if t != ticker.upper()][:5]
                if peers:
                    return peers
    except:
        pass

    return []


def get_peer_multiples(peers):
    """Get valuation multiples for peer companies."""
    data = []
    for p in peers:
        try:
            t = yf.Ticker(p)
            i = t.info
            data.append({
                "ticker": p,
                "pe": safe_get(i, "trailingPE"),
                "fwd_pe": safe_get(i, "forwardPE"),
                "ps": safe_get(i, "priceToSalesTrailing12Months"),
                "ev_ebitda": safe_get(i, "enterpriseToEbitda"),
                "market_cap": safe_get(i, "marketCap"),
            })
        except:
            pass
    return data


def calc_implied_from_multiples(info, peer_data):
    """Calculate implied price from peer average/median multiples."""
    results = {}
    eps = safe_get(info, "trailingEps")
    rev_per_share = None
    total_rev = safe_get(info, "totalRevenue")
    shares = safe_get(info, "sharesOutstanding")
    if total_rev and shares:
        rev_per_share = total_rev / shares

    for metric, key, base in [
        ("P/E", "pe", eps),
        ("Forward P/E", "fwd_pe", safe_get(info, "forwardEps")),
        ("P/S", "ps", rev_per_share),
    ]:
        vals = [d[key] for d in peer_data if d[key] and not np.isnan(d[key]) and d[key] > 0]
        if vals and base and base > 0:
            avg = np.mean(vals)
            med = np.median(vals)
            results[metric] = {
                "peer_avg": avg,
                "peer_median": med,
                "implied_avg": avg * base,
                "implied_median": med * base,
            }

    ev_ebitda_vals = [d["ev_ebitda"] for d in peer_data if d["ev_ebitda"] and not np.isnan(d["ev_ebitda"]) and d["ev_ebitda"] > 0]
    ebitda = safe_get(info, "ebitda")
    net_debt = (safe_get(info, "totalDebt") or 0) - (safe_get(info, "totalCash") or 0)
    if ev_ebitda_vals and ebitda and ebitda > 0 and shares:
        avg = np.mean(ev_ebitda_vals)
        med = np.median(ev_ebitda_vals)
        results["EV/EBITDA"] = {
            "peer_avg": avg,
            "peer_median": med,
            "implied_avg": (avg * ebitda - net_debt) / shares,
            "implied_median": (med * ebitda - net_debt) / shares,
        }

    return results


def get_historical_valuation(tk, info):
    """Get historical valuation data."""
    result = {
        "current_pe": safe_get(info, "trailingPE"),
        "forward_pe": safe_get(info, "forwardPE"),
        "high_52w": safe_get(info, "fiftyTwoWeekHigh"),
        "low_52w": safe_get(info, "fiftyTwoWeekLow"),
        "avg_pe_5y": None,
    }

    try:
        hist = tk.history(period="5y", interval="1mo")
        if not hist.empty:
            # Approximate historical P/E from current EPS
            eps = safe_get(info, "trailingEps")
            if eps and eps > 0:
                pe_series = hist["Close"] / eps
                result["avg_pe_5y"] = float(pe_series.mean())
                result["pe_high_52w"] = float((hist["Close"].tail(12) / eps).max())
                result["pe_low_52w"] = float((hist["Close"].tail(12) / eps).min())
    except:
        pass

    return result


def get_analyst_data(ticker):
    """Get analyst price targets from finvizfinance."""
    result = {"target_high": None, "target_low": None, "target_avg": None, "recommendations": []}
    try:
        from finvizfinance.quote import finvizfinance
        fq = finvizfinance(ticker)
        fundament = fq.ticker_fundament()
        if fundament:
            result["target_avg"] = float(fundament.get("Target Price", 0)) or None

        # Get analyst ratings
        try:
            outer = fq.ticker_outer_ratings()
            if outer is not None and not outer.empty:
                recs = []
                for _, row in outer.head(10).iterrows():
                    recs.append({
                        "date": str(row.get("Date", "")),
                        "firm": str(row.get("Outer", row.get("Analyst", ""))),
                        "action": f"{row.get('Status', '')} — {row.get('Rating', '')}",
                        "target": str(row.get("Price", "")),
                    })
                result["recommendations"] = recs
        except:
            pass
    except:
        pass

    # Supplement from yfinance
    try:
        tk = yf.Ticker(ticker)
        ti = tk.info
        result["target_high"] = result["target_high"] or safe_get(ti, "targetHighPrice")
        result["target_low"] = result["target_low"] or safe_get(ti, "targetLowPrice")
        result["target_avg"] = result["target_avg"] or safe_get(ti, "targetMeanPrice")
        result["num_analysts"] = safe_get(ti, "numberOfAnalystOpinions")
        result["recommendation"] = safe_get(ti, "recommendationKey")
    except:
        pass

    return result


def build_scenarios(base_dcf_price, growth_rates, fcf, wacc_data, shares, fcf_margin, current_price):
    """Build bull/base/bear scenarios."""
    scenarios = {}
    wacc = wacc_data["wacc"]

    # Base case = base DCF
    scenarios["base"] = {
        "price": base_dcf_price,
        "label": "Base Case (Consensus)",
    }

    # Bull case: growth +50%, margin +100bps
    bull_growth = [min(g * 1.5, g + 0.10) for g in growth_rates]
    bull_price = run_dcf(fcf, bull_growth, 0.01, wacc - 0.005, 0.03, shares)
    scenarios["bull"] = {
        "price": bull_price,
        "label": "Bull Case (Optimistic Growth)",
        "growth_rates": bull_growth,
    }

    # Bear case: growth halved, margin -200bps
    bear_growth = [g * 0.5 for g in growth_rates]
    bear_price = run_dcf(fcf, bear_growth, -0.02, wacc + 0.01, 0.02, shares)
    scenarios["bear"] = {
        "price": bear_price,
        "label": "Bear Case (Pessimistic)",
        "growth_rates": bear_growth,
    }

    # Probability-weighted
    prices = []
    weights = [0.25, 0.50, 0.25]
    for s, w in zip(["bull", "base", "bear"], weights):
        p = scenarios[s]["price"]
        if p:
            prices.append(p * w)
    scenarios["weighted"] = sum(prices) if prices else None

    # Upside/downside
    if current_price:
        for k in ["bull", "base", "bear"]:
            p = scenarios[k]["price"]
            if p:
                scenarios[k]["upside_pct"] = (p / current_price - 1) * 100
        if scenarios["weighted"]:
            scenarios["weighted_upside_pct"] = (scenarios["weighted"] / current_price - 1) * 100

    return scenarios


def analyze_ticker(ticker):
    """Run full valuation analysis for a ticker."""
    result = {"ticker": ticker.upper(), "timestamp": datetime.now().isoformat(), "errors": []}

    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
    except Exception as e:
        result["errors"].append(f"Failed to fetch data: {e}")
        return result

    current_price = safe_get(info, "currentPrice") or safe_get(info, "regularMarketPrice")
    shares = safe_get(info, "sharesOutstanding")
    company_name = safe_get(info, "longName") or safe_get(info, "shortName") or ticker.upper()

    result["company"] = company_name
    result["current_price"] = current_price
    result["shares"] = shares
    result["market_cap"] = safe_get(info, "marketCap")
    result["sector"] = safe_get(info, "sector")
    result["industry"] = safe_get(info, "industry")

    # ── Step 1: DCF ──
    risk_free = get_risk_free_rate()
    fcf_data = get_fcf_data(tk, info)
    growth_est = get_growth_estimates(tk, info)
    wacc_data = calc_wacc(info, risk_free)

    # Revenue CAGR
    rev_hist = fcf_data["revenue_history"]
    hist_cagr = None
    if len(rev_hist) >= 3:
        latest, oldest = rev_hist[0], rev_hist[-1]
        if oldest > 0 and latest > 0:
            hist_cagr = (latest / oldest) ** (1.0 / (len(rev_hist) - 1)) - 1
    growth_est["hist_cagr"] = hist_cagr

    # Build 5-year growth rates
    yr1 = growth_est["yr1"] or hist_cagr or 0.05
    yr2 = growth_est["yr2"] or yr1 * 0.9
    anchor = hist_cagr or yr1 * 0.7
    yr3 = yr2 * 0.7 + anchor * 0.3
    yr4 = yr2 * 0.5 + anchor * 0.5
    yr5 = yr2 * 0.3 + anchor * 0.7
    growth_rates = [yr1, yr2, yr3, yr4, yr5]

    fcf_margin = np.mean(fcf_data["fcf_margins"]) if fcf_data["fcf_margins"] else None
    terminal_growth = 0.025

    dcf_price = run_dcf(fcf_data["fcf"], growth_rates, None, wacc_data["wacc"], terminal_growth, shares)

    # Sensitivity table
    sensitivity = {}
    for wacc_adj in [-0.01, 0, 0.01]:
        for tg in [0.02, 0.025, 0.03]:
            w = wacc_data["wacc"] + wacc_adj
            p = run_dcf(fcf_data["fcf"], growth_rates, None, w, tg, shares)
            sensitivity[(w, tg)] = p

    result["dcf"] = {
        "fcf": fcf_data["fcf"],
        "fcf_margin": fcf_margin,
        "fcf_margin_trend": "improving" if fcf_data["fcf_margins"] and len(fcf_data["fcf_margins"]) >= 2 and fcf_data["fcf_margins"][0] > fcf_data["fcf_margins"][-1] else "declining" if fcf_data["fcf_margins"] and len(fcf_data["fcf_margins"]) >= 2 else "insufficient data",
        "growth_rates": growth_rates,
        "growth_sources": growth_est,
        "wacc": wacc_data,
        "terminal_growth": terminal_growth,
        "implied_price": dcf_price,
        "sensitivity": {f"WACC={k[0]:.1%}_TG={k[1]:.1%}": v for k, v in sensitivity.items()},
    }

    # ── Step 2: Comps ──
    peers = get_peers(ticker, info)
    peer_data = get_peer_multiples(peers) if peers else []
    implied_multiples = calc_implied_from_multiples(info, peer_data) if peer_data else {}

    result["comps"] = {
        "peers": peer_data,
        "implied": implied_multiples,
        "target_pe": safe_get(info, "trailingPE"),
        "target_fwd_pe": safe_get(info, "forwardPE"),
        "target_ps": safe_get(info, "priceToSalesTrailing12Months"),
        "target_ev_ebitda": safe_get(info, "enterpriseToEbitda"),
    }

    # ── Step 3: Historical Valuation ──
    result["historical"] = get_historical_valuation(tk, info)

    # ── Step 4: Analyst Targets ──
    result["analyst"] = get_analyst_data(ticker)

    # ── Step 5: Scenarios ──
    result["scenarios"] = build_scenarios(
        dcf_price, growth_rates, fcf_data["fcf"], wacc_data, shares,
        fcf_margin, current_price
    )

    # ── Final Verdict ──
    weighted = result["scenarios"].get("weighted")
    if weighted and current_price:
        diff_pct = (weighted / current_price - 1) * 100
        if diff_pct > 15:
            verdict = "Undervalued"
        elif diff_pct < -15:
            verdict = "Overvalued"
        else:
            verdict = "Fairly Valued"

        bull_p = safe_get(result["scenarios"], "bull", "price") or weighted
        bear_p = safe_get(result["scenarios"], "bear", "price") or weighted
        spread = abs(bull_p - bear_p) / current_price * 100 if current_price else 100
        if spread < 40:
            confidence = "High"
        elif spread < 80:
            confidence = "Medium"
        else:
            confidence = "Low"

        result["verdict"] = {
            "rating": verdict,
            "diff_pct": diff_pct,
            "confidence": confidence,
            "weighted_price": weighted,
            "biggest_variable": "Revenue growth trajectory" if abs(yr1) > 0.15 else "FCF margin sustainability" if fcf_margin and fcf_margin < 0.1 else "Multiple compression/expansion",
        }
    else:
        result["verdict"] = {"rating": "Insufficient Data", "confidence": "Low"}

    return result


def format_markdown(r):
    """Format analysis result as markdown."""
    lines = []
    a = lines.append

    a(f"# {r['ticker']} — Stock Valuation Analysis")
    a(f"**{r.get('company', r['ticker'])}** | {r.get('sector', 'N/A')} — {r.get('industry', 'N/A')}")
    a(f"**Current Price:** {fmt_price(r.get('current_price'))} | **Market Cap:** {fmt_num(r.get('market_cap'))}")
    a(f"*Generated: {r['timestamp'][:19]}*")
    a("")

    # ── VERDICT (top) ──
    v = r.get("verdict", {})
    if v.get("rating"):
        emoji = {"Undervalued": "🟢", "Overvalued": "🔴", "Fairly Valued": "🟡"}.get(v["rating"], "⚪")
        a(f"## {emoji} Verdict: {v['rating']} ({fmt_pct(v.get('diff_pct'))} vs weighted target)")
        a(f"- **Probability-Weighted Fair Value:** {fmt_price(v.get('weighted_price'))}")
        a(f"- **Confidence:** {v.get('confidence', 'N/A')}")
        a(f"- **Biggest Variable:** {v.get('biggest_variable', 'N/A')}")
        a("")

    # ── DCF ──
    dcf = r.get("dcf", {})
    a("## 1. Discounted Cash Flow (DCF)")
    a("")
    a(f"**Most Recent FCF:** {fmt_num(dcf.get('fcf'))}")
    m = dcf.get("fcf_margin")
    a(f"**3-Year Avg FCF Margin:** {fmt_pct(m*100) if m else 'N/A'} (trend: {dcf.get('fcf_margin_trend', 'N/A')})")
    a("")

    # WACC
    w = dcf.get("wacc", {})
    a("### WACC Calculation")
    a(f"- Risk-free rate: {fmt_pct(w.get('risk_free', 0)*100)} [Source: 10Y Treasury ^TNX]")
    a(f"- Beta: {w.get('beta', 'N/A')}")
    a(f"- Equity Risk Premium: 5.5% [ASSUMPTION — historical average]")
    a(f"- Cost of Equity: {fmt_pct(w.get('cost_of_equity', 0)*100)}")
    a(f"- Cost of Debt: {fmt_pct(w.get('cost_of_debt', 0)*100)} (after-tax)")
    a(f"- Equity Weight: {fmt_pct(w.get('we', 0)*100)} | Debt Weight: {fmt_pct(w.get('wd', 0)*100)}")
    a(f"- **WACC: {fmt_pct(w.get('wacc', 0)*100)}**")
    a("")

    # Growth
    gr = dcf.get("growth_rates", [])
    gs = dcf.get("growth_sources", {})
    a("### Revenue Growth Assumptions")
    labels = [
        f"Yr1: analyst consensus" if gs.get("yr1") else "Yr1: historical CAGR",
        f"Yr2: analyst consensus" if gs.get("yr2") else "Yr2: faded from Yr1",
        "Yr3: fading to historical avg [ASSUMPTION]",
        "Yr4: fading to historical avg [ASSUMPTION]",
        "Yr5: near historical avg [ASSUMPTION]",
    ]
    for i, g in enumerate(gr):
        a(f"- **Year {i+1}:** {fmt_pct(g*100)} — {labels[i] if i < len(labels) else '[ASSUMPTION]'}")
    hc = gs.get("hist_cagr")
    if hc:
        a(f"- *3-Year Historical Revenue CAGR: {fmt_pct(hc*100)}*")
    a(f"- Terminal Growth: {fmt_pct(dcf.get('terminal_growth', 0.025)*100)} [ASSUMPTION — long-run GDP growth]")
    a("")

    a(f"### **DCF Implied Price: {fmt_price(dcf.get('implied_price'))}**")
    cp = r.get("current_price")
    ip = dcf.get("implied_price")
    if cp and ip:
        a(f"*{fmt_pct((ip/cp-1)*100)} vs current price*")
    a("")

    # Sensitivity
    sens = dcf.get("sensitivity", {})
    if sens:
        a("### Sensitivity Table (WACC × Terminal Growth)")
        # Parse
        wacc_base = w.get("wacc", 0.10)
        waccs = [wacc_base - 0.01, wacc_base, wacc_base + 0.01]
        tgs = [0.02, 0.025, 0.03]
        a(f"| | TG=2.0% | TG=2.5% | TG=3.0% |")
        a(f"|---|---|---|---|")
        for wv in waccs:
            row = f"| WACC={wv:.1%} |"
            for tg in tgs:
                key = f"WACC={wv:.1%}_TG={tg:.1%}"
                val = sens.get(key)
                row += f" {fmt_price(val)} |"
            a(row)
        a("")

    # ── COMPS ──
    comps = r.get("comps", {})
    a("## 2. Comparable Company Analysis")
    peers = comps.get("peers", [])
    if peers:
        a(f"| Ticker | P/E | Fwd P/E | P/S | EV/EBITDA |")
        a(f"|---|---|---|---|---|")
        a(f"| **{r['ticker']}** | {fmt_x(comps.get('target_pe'))} | {fmt_x(comps.get('target_fwd_pe'))} | {fmt_x(comps.get('target_ps'))} | {fmt_x(comps.get('target_ev_ebitda'))} |")
        for p in peers:
            a(f"| {p['ticker']} | {fmt_x(p.get('pe'))} | {fmt_x(p.get('fwd_pe'))} | {fmt_x(p.get('ps'))} | {fmt_x(p.get('ev_ebitda'))} |")
        a("")

        implied = comps.get("implied", {})
        if implied:
            a("### Implied Prices at Peer Multiples")
            for metric, d in implied.items():
                a(f"- **{metric}:** Peer Avg {fmt_x(d['peer_avg'])} → {fmt_price(d['implied_avg'])} | Peer Median {fmt_x(d['peer_median'])} → {fmt_price(d['implied_median'])}")
            a("")
    else:
        a("*No comparable companies found.*\n")

    # ── HISTORICAL ──
    hist = r.get("historical", {})
    a("## 3. Historical Valuation")
    a(f"- Current P/E: {fmt_x(hist.get('current_pe'))}")
    a(f"- Forward P/E: {fmt_x(hist.get('forward_pe'))}")
    a(f"- 5-Year Avg P/E (approx): {fmt_x(hist.get('avg_pe_5y'))}")
    if hist.get("avg_pe_5y") and hist.get("current_pe"):
        diff = (hist["current_pe"] / hist["avg_pe_5y"] - 1) * 100
        a(f"- Current vs 5Y Avg: {'+' if diff > 0 else ''}{diff:.1f}% {'premium' if diff > 0 else 'discount'}")
    a(f"- 52-Week Range: {fmt_price(hist.get('low_52w'))} — {fmt_price(hist.get('high_52w'))}")
    if hist.get("pe_high_52w"):
        a(f"- 52-Week P/E Range: {fmt_x(hist.get('pe_low_52w'))} — {fmt_x(hist.get('pe_high_52w'))}")
    a("")

    # ── ANALYST ──
    an = r.get("analyst", {})
    a("## 4. Analyst Price Targets")
    a(f"- **Target High:** {fmt_price(an.get('target_high'))}")
    a(f"- **Target Low:** {fmt_price(an.get('target_low'))}")
    a(f"- **Target Average:** {fmt_price(an.get('target_avg'))}")
    a(f"- **# Analysts:** {an.get('num_analysts', 'N/A')} | **Consensus:** {an.get('recommendation', 'N/A')}")
    recs = an.get("recommendations", [])
    if recs:
        a("")
        a("### Recent Analyst Actions")
        for rec in recs[:8]:
            a(f"- {rec.get('date', '')} — **{rec.get('firm', '')}**: {rec.get('action', '')} {rec.get('target', '')}")
    a("")

    # ── SCENARIOS ──
    sc = r.get("scenarios", {})
    a("## 5. Scenario Analysis")
    for key, label, weight in [("bull", "🐂 Bull", "25%"), ("base", "📊 Base", "50%"), ("bear", "🐻 Bear", "25%")]:
        s = sc.get(key, {})
        price = fmt_price(s.get("price"))
        upside = s.get("upside_pct")
        upside_str = f" ({'+' if upside > 0 else ''}{upside:.1f}%)" if upside is not None else ""
        a(f"- **{label} ({weight}):** {price}{upside_str}")

    wt = sc.get("weighted")
    wt_up = sc.get("weighted_upside_pct")
    a(f"- **Probability-Weighted Target:** {fmt_price(wt)}" + (f" ({'+' if wt_up > 0 else ''}{wt_up:.1f}%)" if wt_up else ""))
    a("- *Weights: Bull 25% / Base 50% / Bear 25%* [ASSUMPTION]")
    a("")

    # ── ERRORS ──
    if r.get("errors"):
        a("## ⚠️ Errors")
        for e in r["errors"]:
            a(f"- {e}")
        a("")

    a("---")
    a("*Data: yfinance, finvizfinance | All assumptions marked [ASSUMPTION]*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Multi-method stock valuation model")
    parser.add_argument("tickers", nargs="+", help="Stock ticker(s) to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = []
    for ticker in args.tickers:
        try:
            r = analyze_ticker(ticker)
            results.append(r)
        except Exception as e:
            results.append({"ticker": ticker, "error": str(e), "traceback": traceback.format_exc()})

    if args.json:
        # Convert numpy types for JSON serialization
        def default_ser(o):
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return float(o)
            if isinstance(o, np.ndarray):
                return o.tolist()
            return str(o)
        print(json.dumps(results, indent=2, default=default_ser))
    else:
        for r in results:
            if "error" in r and "dcf" not in r:
                print(f"# {r['ticker']} — ERROR\n{r['error']}\n{r.get('traceback', '')}")
            else:
                print(format_markdown(r))
                print()


if __name__ == "__main__":
    main()
