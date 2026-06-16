#!/usr/bin/env python3
"""BigClaw Style Gate Checks — hard pre-buy filters for portfolio style fidelity.

Gate checks are the FIRST layer of style enforcement. They run BEFORE scoring.
If a ticker fails the gate for a portfolio, it is blocked regardless of score.

The gates answer: "Is this stock even ELIGIBLE for this portfolio?"
The scoring answers: "Among eligible stocks, which is best?"

Usage:
    from style_gates import passes_style_gate

    result = passes_style_gate("PLTR", "Nuclear Renaissance", info)
    if not result["pass"]:
        print(f"Blocked: {result['reason']}")

    # Or check all portfolios at once:
    results = check_all_gates("PLTR", info)
    eligible = [p for p, r in results.items() if r["pass"]]
"""

import os
import sys
import json
import logging

log = logging.getLogger("style_gates")

# ─── Sector / Industry Classification ───────────────────────────────────────
# These are yfinance sector and industry strings used for thematic portfolio gates.

NUCLEAR_SECTORS = {"Utilities", "Energy", "Industrials", "Basic Materials"}
NUCLEAR_INDUSTRIES = {
    # Direct nuclear
    "Utilities—Regulated Electric", "Utilities—Diversified",
    "Utilities—Independent Power Producers",
    "Uranium", "Nuclear Energy",
    # Nuclear services / fuel / engineering
    "Specialty Industrial Machinery", "Aerospace & Defense",
    "Engineering & Construction",
}
NUCLEAR_TICKERS = {
    # Full IPS whitelist (April 2026) — manually curated, yfinance sector unreliable
    # Nuclear utilities
    "CEG", "VST", "EXC", "SO", "D", "PEG", "ETR", "TLN",
    "DUK", "NEE", "XEL", "PNW", "PCG", "EVRG", "AEP", "AEE",
    # Uranium mining/fuel
    "CCJ", "UEC", "UUUU", "NXE", "DNN", "LEU", "URG",
    # Nuclear manufacturing/services
    "BWXT", "GEV", "FLR", "J", "CW",
    # SMR developers
    "OKLO", "SMR",
    # Watchlist (below $3B cap but tracked)
    "NNE",
    # ETF benchmarks (not for purchase)
    "URA", "URNM", "NLR",
}
NUCLEAR_SPECULATIVE = {"LEU", "OKLO", "SMR", "NNE", "DNN", "UEC", "UUUU", "NXE", "URG"}
NUCLEAR_UTILITIES = {"CEG", "VST", "EXC", "SO", "D", "PEG", "ETR", "TLN", "DUK", "NEE", "XEL", "PNW", "PCG", "EVRG", "AEP", "AEE"}

DEFENSE_SECTORS = {"Industrials", "Technology", "Communication Services"}
DEFENSE_INDUSTRIES = {
    "Aerospace & Defense",
    "Information Technology Services",
    "Software—Infrastructure", "Software—Application",
    "Scientific & Technical Instruments",
    "Security & Protection Services",
    "Communication Equipment",
}
DEFENSE_TICKERS = {
    # Full IPS whitelist (April 2026)
    "PLTR", "KTOS", "AVAV", "LDOS",  # Tier 1: Genuine AI/Autonomous
    "NOC", "LHX", "RTX", "BAH",      # Tier 2: Strong AI Pivot
    "LMT", "GD", "TXT",              # Tier 3: Traditional + AI Upside
    "RCAT", "AXON",                   # Tier 4: Speculative
}

INNOVATION_PLATFORMS = {
    # Platform 1: AI / ML / Compute
    "ai_ml": {
        "industries": {"Semiconductors", "Software—Infrastructure", "Software—Application",
                       "Information Technology Services", "Electronic Components"},
        "tickers": {"NVDA", "AMD", "PLTR", "GOOG", "GOOGL", "MSFT", "META", "AMZN",
                     "SNOW", "DDOG", "PATH", "AI", "SMCI", "ARM", "TSM"},
    },
    # Platform 2: Robotics / Autonomous Systems
    "robotics": {
        "industries": {"Auto Manufacturers", "Farm & Heavy Construction Machinery",
                       "Aerospace & Defense", "Specialty Industrial Machinery"},
        "tickers": {"TSLA", "DE", "ISRG", "JOBY", "ACHR", "IRVR"},
    },
    # Platform 3: Energy Storage / Clean Energy
    "energy_storage": {
        "industries": {"Solar", "Utilities—Renewable", "Electrical Equipment & Parts",
                       "Auto Manufacturers"},
        "tickers": {"TSLA", "ENPH", "SEDG", "QS", "FSLR", "BE", "PLUG"},
    },
    # Platform 4: Genomics / Multiomics / Precision Medicine
    "genomics": {
        "industries": {"Biotechnology", "Diagnostics & Research",
                       "Medical Instruments & Supplies", "Drug Manufacturers—General"},
        "tickers": {"CRSP", "NTLA", "BEAM", "EDIT", "EXAS", "TEM", "CRCL",
                     "TWST", "PACB", "IONS", "FATE"},
    },
    # Platform 5: Blockchain / Fintech / Next-Gen Internet
    "blockchain_fintech": {
        "industries": {"Software—Application", "Software—Infrastructure",
                       "Capital Markets", "Financial Data & Stock Exchanges",
                       "Credit Services", "Internet Content & Information"},
        "tickers": {"COIN", "HOOD", "SQ", "SHOP", "AFRM", "SOFI", "ROKU",
                     "RBLX", "U", "DKNG", "NET", "TWLO"},
    },
}

# Legacy/traditional businesses that are NOT innovation (Wood would never buy these)
LEGACY_INDUSTRIES = {
    "Tobacco", "Packaged Foods", "Household & Personal Products",
    "Insurance—Diversified", "Insurance—Life", "Insurance—Property & Casualty",
    "Banks—Regional", "Banks—Diversified", "Savings & Cooperative Banking",
    "Utilities—Regulated Electric", "Utilities—Regulated Gas",
    "Utilities—Regulated Water", "Oil & Gas Integrated",
    "Oil & Gas E&P", "Oil & Gas Midstream", "Oil & Gas Refining & Marketing",
    "Beverages—Non-Alcoholic", "Beverages—Brewers", "Beverages—Wineries & Distilleries",
    "Food Distribution", "Grocery Stores", "Department Stores",
    "Discount Stores", "Home Improvement Retail",
}


# ─── Gate Check Functions ────────────────────────────────────────────────────

def _gate_value_picks(ticker, info):
    """Value Picks — Buffett/Graham IPS gate checks (April 2026).

    G1: Positive earnings
    G3: ROE >= 15%
    G4: Positive FCF (Energy/Financial/Utility exempt)
    G5: P/E <= 25
    G6: D/E <= 1.5 (non-financial, non-utility)
    G7: Gross margin >= 30% (exempt Energy, Financial, Utility)
    G9: P/E x P/B <= 22.5 (skip if P/B unavailable/negative)
    """
    sector = info.get("sector", "")

    # G1: Positive earnings
    eps = info.get("trailingEps")
    if eps is not None and eps <= 0:
        return {"pass": False, "reason": f"REJECT: EPS ${eps:.2f} <= 0", "severity": "gate"}

    # G3: ROE >= 15%
    roe = info.get("returnOnEquity")
    if roe is not None and roe < 0.15:
        return {"pass": False, "reason": f"REJECT: ROE {roe:.0%} < 15%", "severity": "gate"}

    # G4: Positive FCF (exempt Energy, Financial, Utility)
    fcf = info.get("freeCashflow")
    if fcf is not None and fcf <= 0 and sector not in ("Financial Services", "Utilities", "Energy"):
        return {"pass": False, "reason": f"REJECT: FCF ${fcf/1e6:.0f}M <= 0", "severity": "gate"}

    # G5: P/E <= 25
    pe = info.get("trailingPE")
    if pe is not None and pe > 25:
        return {"pass": False, "reason": f"REJECT: P/E {pe:.0f} > 25", "severity": "gate"}

    # G6: D/E <= 1.5 (non-financial, non-utility)
    de = info.get("debtToEquity")
    if de is not None and sector not in ("Financial Services", "Utilities"):
        de_ratio = de / 100 if de > 10 else de
        if de_ratio > 1.5:
            return {"pass": False, "reason": f"REJECT: D/E {de_ratio:.1f} > 1.5", "severity": "gate"}

    # G7: Gross margin >= 30% (exempt Energy, Financial, Utility)
    gm = info.get("grossMargins")
    if gm is not None and gm < 0.30 and sector not in ("Financial Services", "Utilities", "Energy"):
        return {"pass": False, "reason": f"REJECT: GM {gm:.0%} < 30%", "severity": "gate"}

    # G9: P/E x P/B <= 22.5
    pb = info.get("priceToBook")
    if pe is not None and pb is not None and pe > 0 and pb > 0:
        combined = pe * pb
        if combined > 22.5:
            return {"pass": False, "reason": f"REJECT: PExPB {combined:.1f} > 22.5", "severity": "gate"}

    # Market cap
    mcap = info.get("marketCap", 0) or 0
    if mcap > 0 and mcap < 3e9:
        return {"pass": False, "reason": f"REJECT: mcap ${mcap/1e9:.1f}B < $3B", "severity": "gate"}

    return {"pass": True, "reason": "passes Value Picks (Buffett/Graham) IPS gates"}


def _gate_growth_value(ticker, info):
    """Growth Value — Peter Lynch GARP IPS gate checks (April 2026).

    G1: Positive earnings
    G2: PEG < 1.0 (Lynch fair value)
    G3: P/E between 5 and 40
    G4: EPS growth 10-50%
    G5: D/E < 0.80 (financial exempt)
    G6: Positive FCF
    """
    sector = info.get("sector", "")

    # G1: Positive earnings
    eps = info.get("trailingEps")
    if eps is not None and eps <= 0:
        return {"pass": False, "reason": f"REJECT: EPS ${eps:.2f} <= 0", "severity": "gate"}

    # G2: PEG < 1.0
    peg = info.get("pegRatio")
    if peg is not None:
        if peg <= 0:
            return {"pass": False, "reason": f"REJECT: PEG {peg:.2f} <= 0", "severity": "gate"}
        if peg >= 1.0:
            return {"pass": False, "reason": f"REJECT: PEG {peg:.2f} >= 1.0", "severity": "gate"}

    # G3: P/E 5-40
    pe = info.get("trailingPE")
    if pe is not None and (pe < 5 or pe > 40):
        return {"pass": False, "reason": f"REJECT: P/E {pe:.0f} outside 5-40", "severity": "gate"}

    # G4: EPS growth 10-50%
    eg = info.get("earningsGrowth")
    if eg is not None:
        if eg < 0.10:
            return {"pass": False, "reason": f"REJECT: EPS growth {eg:.0%} < 10%", "severity": "gate"}
        if eg > 0.50:
            return {"pass": False, "reason": f"REJECT: EPS growth {eg:.0%} > 50%", "severity": "gate"}

    # G5: D/E < 0.80 (financial exempt)
    de = info.get("debtToEquity")
    if de is not None and sector not in ("Financial Services",):
        de_ratio = de / 100 if de > 10 else de
        if de_ratio > 0.80:
            return {"pass": False, "reason": f"REJECT: D/E {de_ratio:.2f} > 0.80", "severity": "gate"}

    # G6: Positive FCF
    fcf = info.get("freeCashflow")
    if fcf is not None and fcf <= 0:
        return {"pass": False, "reason": f"REJECT: FCF ${fcf/1e6:.0f}M <= 0", "severity": "gate"}

    # Market cap
    mcap = info.get("marketCap", 0) or 0
    if mcap > 0 and mcap < 3e9:
        return {"pass": False, "reason": f"REJECT: mcap ${mcap/1e9:.1f}B < $3B", "severity": "gate"}

    return {"pass": True, "reason": "passes Growth Value (Lynch/GARP) IPS gates"}


def _gate_income_dividends(ticker, info):
    """Income Dividends — IPS gate checks (April 2026).

    G1: Must pay dividend (yield > 0)
    G2: Yield >= 1.5%
    G4: Positive earnings
    G5: Positive FCF (REIT/utility exempt)
    G6: Payout ratio <= 75% (REIT/utility exempt)
    G7: Common equity (not ETF)
    """
    # G1 + G2: Dividend yield >= 1.5%
    dy = info.get("dividendYield", 0) or 0
    if dy < 0.015:
        if dy <= 0:
            return {"pass": False, "reason": "REJECT: no dividend", "severity": "reject"}
        return {"pass": False, "reason": f"REJECT: yield {dy:.1%} < 1.5%", "severity": "gate"}

    # G4: Positive earnings
    eps = info.get("trailingEps")
    if eps is not None and eps <= 0:
        return {"pass": False, "reason": f"REJECT: EPS ${eps:.2f} <= 0", "severity": "gate"}

    # G5: Positive FCF (REIT/utility exempt)
    sector = info.get("sector", "")
    fcf = info.get("freeCashflow")
    if fcf is not None and fcf <= 0 and sector not in ("Real Estate", "Utilities"):
        return {"pass": False, "reason": f"REJECT: FCF ${fcf/1e6:.0f}M <= 0", "severity": "gate"}

    # G6: Payout ratio <= 75%
    pr = info.get("payoutRatio")
    if pr is not None and pr > 0.75 and sector not in ("Real Estate", "Utilities"):
        return {"pass": False, "reason": f"REJECT: payout {pr:.0%} > 75%", "severity": "gate"}

    # Market cap
    mcap = info.get("marketCap", 0) or 0
    if mcap > 0 and mcap < 3e9:
        return {"pass": False, "reason": f"REJECT: mcap ${mcap/1e9:.1f}B < $3B", "severity": "gate"}

    return {"pass": True, "reason": "passes Income Dividends IPS gates"}


def _gate_innovation_fund(ticker, info):
    """Innovation Fund — Cathie Wood/ARK IPS gate checks (April 2026).

    G2: Revenue growth >= 15%
    G3: Dividend yield < 3% (anti-dividend — mature companies excluded)
    No P/E, PEG, ROE, or earnings gates — pre-profit tolerated.
    """
    # G2: Revenue growth >= 15%
    rg = info.get("revenueGrowth")
    if rg is not None and rg < 0.15:
        return {"pass": False, "reason": f"REJECT: revenue growth {rg:.0%} < 15%", "severity": "gate"}

    # G3: Dividend yield < 3%
    dy = info.get("dividendYield", 0) or 0
    if dy >= 0.03:
        return {"pass": False, "reason": f"REJECT: yield {dy:.1%} >= 3% (mature company)", "severity": "gate"}

    # Market cap
    mcap = info.get("marketCap", 0) or 0
    if mcap > 0 and mcap < 3e9:
        return {"pass": False, "reason": f"REJECT: mcap ${mcap/1e9:.1f}B < $3B", "severity": "gate"}

    return {"pass": True, "reason": "passes Innovation Fund (ARK) IPS gates"}


def _gate_momentum_growth(ticker, info):
    """Momentum Growth — CANSLIM IPS gate checks (April 2026).

    G1: Quarterly EPS growth >= 25%
    G3: ROE >= 17%
    G4: Near 52-week high (within 15%)
    G6: Market direction (SPY > SMA200) — checked at portfolio level
    G8: Positive earnings
    G9: Min price $15
    """
    # G8: Positive earnings
    eps = info.get("trailingEps")
    if eps is not None and eps <= 0:
        return {"pass": False, "reason": f"REJECT: EPS ${eps:.2f} <= 0", "severity": "gate"}

    # G1: Quarterly EPS growth >= 25%
    qeg = info.get("earningsQuarterlyGrowth")
    if qeg is not None and qeg < 0.25:
        return {"pass": False, "reason": f"REJECT: QtrEPS {qeg:.0%} < 25%", "severity": "gate"}

    # G3: ROE >= 17%
    roe = info.get("returnOnEquity")
    if roe is not None and roe < 0.17:
        return {"pass": False, "reason": f"REJECT: ROE {roe:.0%} < 17%", "severity": "gate"}

    # G4: Near 52-week high (within 15%)
    high52 = info.get("fiftyTwoWeekHigh", 0) or 0
    price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
    if high52 > 0 and price > 0:
        pct_below = (high52 - price) / high52
        if pct_below > 0.15:
            return {"pass": False, "reason": f"REJECT: {pct_below:.0%} below 52w high", "severity": "gate"}

    # G9: Min price
    if price and price < 15:
        return {"pass": False, "reason": f"REJECT: price ${price:.0f} < $15", "severity": "gate"}

    # Market cap
    mcap = info.get("marketCap", 0) or 0
    if mcap > 0 and mcap < 3e9:
        return {"pass": False, "reason": f"REJECT: mcap ${mcap/1e9:.1f}B < $3B", "severity": "gate"}

    return {"pass": True, "reason": "passes Momentum Growth (CANSLIM) IPS gates"}


def _gate_nuclear_renaissance(ticker, info):
    """Nuclear Renaissance — IPS gate checks (April 2026).

    G1: Must be on nuclear whitelist
    G2: Market cap >= $3B
    G3: Positive FCF for Core holdings (speculative/utility exempt)
    G4: Positive revenue (speculative exempt)
    G5: No-chase (>5% daily gain) — checked elsewhere
    G6: Data sufficiency
    """
    reasons = []

    # G1: Whitelist
    if ticker not in NUCLEAR_TICKERS:
        return {"pass": False, "reason": f"REJECT: {ticker} not on nuclear whitelist", "severity": "reject"}

    # Skip remaining gates for ETF benchmarks
    if ticker in ("URA", "URNM", "NLR"):
        return {"pass": False, "reason": f"{ticker} is ETF benchmark, not for purchase", "severity": "info"}

    # G2: Market cap >= $3B
    mcap = info.get("marketCap", 0) or 0
    if mcap > 0 and mcap < 3e9:
        return {"pass": False, "reason": f"REJECT: marketCap ${mcap/1e9:.1f}B < $3B minimum", "severity": "gate"}

    # G3: Positive FCF for Core (speculative and utilities exempt)
    if ticker not in NUCLEAR_SPECULATIVE and ticker not in NUCLEAR_UTILITIES:
        fcf = info.get("freeCashflow")
        if fcf is not None and fcf <= 0:
            reasons.append(f"FCF ${fcf/1e6:.0f}M <= 0 (Core holding)")

    # G4: Positive revenue (speculative exempt)
    if ticker not in NUCLEAR_SPECULATIVE:
        rev = info.get("totalRevenue", 0) or 0
        if rev <= 0:
            reasons.append("no revenue")

    if reasons:
        return {"pass": False, "reason": f"REJECT: {'; '.join(reasons)}", "severity": "gate"}

    return {"pass": True, "reason": f"{ticker} passes Nuclear Renaissance IPS gates"}


def _gate_defense(ticker, info):
    """AI Defense & Autonomous — IPS gate checks (April 2026).

    G1: Must be on defense whitelist
    G2: US domicile
    G3: Market cap >= $3B
    G5: Revenue > 0
    """
    # G1: Whitelist
    if ticker not in DEFENSE_TICKERS:
        return {"pass": False, "reason": f"REJECT: {ticker} not on defense whitelist", "severity": "reject"}

    # G2: US domicile
    country = info.get("country", "")
    if country and country != "United States":
        return {"pass": False, "reason": f"REJECT: country '{country}' not US", "severity": "gate"}

    # G3: Market cap >= $3B
    mcap = info.get("marketCap", 0) or 0
    if mcap > 0 and mcap < 3e9:
        return {"pass": False, "reason": f"REJECT: mcap ${mcap/1e9:.1f}B < $3B", "severity": "gate"}

    # G5: Revenue > 0
    rev = info.get("totalRevenue", 0) or 0
    if rev <= 0:
        return {"pass": False, "reason": "REJECT: no revenue", "severity": "gate"}

    return {"pass": True, "reason": f"{ticker} passes AI Defense IPS gates"}



# ─── Main API ────────────────────────────────────────────────────────────────

GATE_FUNCTIONS = {
    "Value Picks": _gate_value_picks,
    "Growth Value": _gate_growth_value,
    "Income Dividends": _gate_income_dividends,
    "Innovation Fund": _gate_innovation_fund,
    "Momentum Growth": _gate_momentum_growth,
    "Nuclear Renaissance": _gate_nuclear_renaissance,
    "AI Defense & Autonomous": _gate_defense,
}


def passes_style_gate(ticker, portfolio_name, info=None, context="pre_buy"):
    """Check if a ticker passes the style gate for a specific portfolio.

    The IPS criteria from the 4-LLM thesis debate (April 1) are authoritative.
    A failure is a failure; the 20-dim scoring engine handles dynamic re-entry.

    Args:
        ticker: Stock ticker symbol
        portfolio_name: Name of the portfolio to check against
        info: yfinance .info dict (if None, will be fetched)
        context: Label for logging only — pre_buy, holding_audit, candidate_screen

    Returns:
        dict with keys: pass (bool), reason (str), severity (str or None)
    """
    if info is None:
        try:
            import yfinance as yf
            from fundamentals_cache import get_info; info = get_info(ticker)
        except Exception as e:
            log.warning(f"Could not fetch info for {ticker}: {e}")
            # Fail open — if we can't get data, let the score decide
            return {"pass": True, "reason": f"data unavailable, deferring to score", "severity": None}

    gate_fn = GATE_FUNCTIONS.get(portfolio_name)
    if gate_fn is None:
        log.warning(f"No gate function for portfolio '{portfolio_name}'")
        return {"pass": True, "reason": "no gate defined", "severity": None}

    try:
        result = gate_fn(ticker, info)
    except Exception as e:
        log.error(f"Gate check error for {ticker}/{portfolio_name}: {e}")
        return {"pass": True, "reason": f"gate check error: {e}", "severity": None}

    # IPS criteria are authoritative — no AI override layer.
    # If a stock fails any gate, it fails. The 20-dim scoring engine handles
    # dynamic re-evaluation; if a stock's metrics improve later, it passes the
    # gate next screen and gets re-evaluated for entry.
    return result


def check_all_gates(ticker, info=None):
    """Check a ticker against ALL portfolio gates. Returns dict of portfolio -> result."""
    if info is None:
        try:
            import yfinance as yf
            from fundamentals_cache import get_info; info = get_info(ticker)
        except Exception:
            info = {}

    results = {}
    for pname in GATE_FUNCTIONS:
        results[pname] = passes_style_gate(ticker, pname, info)
    return results


# ─── CLI for testing ─────────────────────────────────────────────────────────

def main():
    """CLI: python3 style_gates.py TICKER [PORTFOLIO]"""
    import argparse
    parser = argparse.ArgumentParser(description="BigClaw Style Gate Checker")
    parser.add_argument("ticker", help="Stock ticker to check")
    parser.add_argument("portfolio", nargs="?", help="Specific portfolio (default: check all)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    import yfinance as yf
    ticker = args.ticker.upper()
    from fundamentals_cache import get_info; info = get_info(ticker)

    if args.portfolio:
        result = passes_style_gate(ticker, args.portfolio, info)
        if args.json:
            print(json.dumps({"ticker": ticker, "portfolio": args.portfolio, **result}, indent=2))
        else:
            icon = "✅" if result["pass"] else "🚫"
            print(f"{icon} {ticker} → {args.portfolio}: {result['reason']}")
    else:
        results = check_all_gates(ticker, info)
        sector = info.get("sector", "?")
        industry = info.get("industry", "?")
        print(f"\n{ticker} — {sector} / {industry}\n")

        if args.json:
            print(json.dumps({"ticker": ticker, "sector": sector, "industry": industry, "gates": {k: v for k, v in results.items()}}, indent=2, default=str))
        else:
            for pname, result in sorted(results.items()):
                icon = "✅" if result["pass"] else "🚫"
                print(f"  {icon} {pname:.<30s} {result['reason']}")
        print()


if __name__ == "__main__":
    main()
