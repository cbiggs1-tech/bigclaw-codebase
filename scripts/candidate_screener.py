#!/usr/bin/env python3
"""BigClaw Candidate Screener — discovers new stocks that fit each portfolio's style.

Runs weekly (Saturday). For each portfolio:
1. Screens Finviz using portfolio-specific filters to find eligible tickers
2. Runs style gate checks on each — hard rejects are dropped
3. Borderline near-misses are escalated to Opus for AI reasoning
4. Survivors are added to portfolio_universes.json as candidates
5. The daily rescreen (decision_engine --rescreen) scores them against holdings
6. If a candidate outscores the weakest holding by SWAP_THRESHOLD, the swap fires

This is the "find better stocks" pipeline. The existing swap engine handles the rest.

Usage:
    python3 candidate_screener.py                  # Full screen, update universes
    python3 candidate_screener.py --dry-run        # Show candidates without updating
    python3 candidate_screener.py --portfolio "Value Picks"  # Screen one portfolio
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style_gates import passes_style_gate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("screener")

DB_PATH = os.path.expanduser("~/bigclaw-ai/src/portfolios.db")
UNIVERSES_PATH = os.path.expanduser("~/.openclaw/workspace/config/portfolio_universes.json")
# (Removed MAX_CANDIDATES_PER_PORTFOLIO cap May 2026 — gates are the screening
# method, not gates+alphabetic-truncation. Decision engine handles top-N.)
FINVIZ_DELAY = 1.0  # seconds between finviz requests to avoid rate limiting

# ─── Finviz Screen Definitions Per Portfolio ─────────────────────────────────
# Each portfolio gets a Finviz filter set tuned to its style gates.
# These cast a wide net — the style gates narrow it down.

PORTFOLIO_SCREENS = {
    "Value Picks": {
        "description": "Buffett/Graham — quality value with margin of safety",
        "filters": [
            # Core value: low P/E, profitable, large cap, pays dividend
            {
                "P/E": "Under 25",
                "Market Cap.": "+Large (over $10bln)",
                "Return on Equity": "Over +15%",
                "EPS growththis year": "Positive (>0%)",
                "Dividend Yield": "Positive (>0%)",
            },
            # Secondary: mid-cap value with strong ROE and margins
            {
                "P/E": "Under 20",
                "Market Cap.": "+Mid (over $2bln)",
                "Return on Equity": "Over +20%",
                "Gross Margin": "Over 30%",
            },
        ],
    },
    "Growth Value": {
        "description": "Peter Lynch — GARP, growth at a reasonable price",
        "filters": [
            # PEG-friendly: growing earnings, not insane P/E
            {
                "P/E": "Under 40",
                "EPS growththis year": "Over 15%",
                "EPS growthnext year": "Over 10%",
                "Market Cap.": "+Large (over $10bln)",
            },
            # Revenue accelerators with reasonable valuation
            {
                "P/E": "Under 50",
                "Sales growthpast 5 years": "Over 10%",
                "EPS growthnext year": "Over 15%",
                "Market Cap.": "+Mid (over $2bln)",
            },
        ],
    },
    "Income Dividends": {
        "description": "Dividend Aristocrats — reliable income",
        "filters": [
            # High yield, sustainable
            {
                "Dividend Yield": "Over 2%",
                "Market Cap.": "+Large (over $10bln)",
                "Payout Ratio": "Under 80%",
            },
            # Moderate yield with growth
            {
                "Dividend Yield": "Over 1.5%",
                "EPS growththis year": "Positive (>0%)",
                "Market Cap.": "+Mid (over $2bln)",
            },
        ],
    },
    "Innovation Fund": {
        "description": "Cathie Wood — disruptive innovation on 5 platforms",
        "filters": [
            # High revenue growth tech/healthcare
            {
                "Sales growthqtr over qtr": "Over 15%",
                "Sector": "Technology",
                "Market Cap.": "+Mid (over $2bln)",
            },
            {
                "Sales growthqtr over qtr": "Over 20%",
                "Sector": "Healthcare",
                "Market Cap.": "+Small (over $300mln)",
            },
            # Fintech / communication
            {
                "Sales growthqtr over qtr": "Over 15%",
                "Sector": "Communication Services",
                "Market Cap.": "+Mid (over $2bln)",
            },
        ],
    },
    "Momentum Growth": {
        "description": "William O'Neil — CANSLIM momentum + earnings",
        "filters": [
            # Near 52-week high with earnings acceleration
            {
                "EPS growththis year": "Over 20%",
                "EPS growthnext year": "Over 15%",
                "52-Week High/Low": "0-10% below High",
                "Market Cap.": "+Mid (over $2bln)",
                "InstitutionalOwnership": "Over 20%",
            },
            # Strong relative performance
            {
                "EPS growthqtr over qtr": "Over 20%",
                "Performance (Quarter)": "Over 10%",
                "Market Cap.": "+Mid (over $2bln)",
            },
        ],
    },
    "Nuclear Renaissance": {
        "description": "Nuclear power, uranium, nuclear services",
        "filters": [
            # Utilities + energy sector
            {
                "Sector": "Utilities",
                "Market Cap.": "+Small (over $300mln)",
            },
            {
                "Industry": "Uranium",
                "Market Cap.": "+Micro (over $50mln)",
            },
        ],
    },
    "AI Defense & Autonomous": {
        "description": "Pentagon AI, defense primes, autonomous systems",
        "filters": [
            {
                "Industry": "Aerospace & Defense",
                "Market Cap.": "+Mid (over $2bln)",
            },
            # Gov IT / defense software
            {
                "Sector": "Technology",
                "Sales growthqtr over qtr": "Over 10%",
                "Market Cap.": "+Mid (over $2bln)",
                "InstitutionalOwnership": "Over 30%",
            },
        ],
    },
}


def get_current_holdings():
    """Load current holdings per portfolio from DB."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    rows = conn.execute("""
        SELECT p.name, h.ticker FROM holdings h
        JOIN portfolios p ON h.portfolio_id = p.id
        WHERE p.is_active = 1 AND h.shares > 0
    """).fetchall()
    conn.close()

    holdings = {}
    for pname, ticker in rows:
        holdings.setdefault(pname, set()).add(ticker)
    return holdings


def load_current_universes():
    """Load existing portfolio_universes.json."""
    try:
        with open(UNIVERSES_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def run_finviz_screen(filters_dict):
    """Run a Finviz screen and return list of tickers."""
    try:
        from finvizfinance.screener.overview import Overview
        foverview = Overview()
        foverview.set_filter(filters_dict=filters_dict)
        df = foverview.screener_view()
        if df is not None and len(df) > 0:
            return list(df["Ticker"].values)
        return []
    except Exception as e:
        log.warning(f"Finviz screen failed: {e}")
        return []


def screen_portfolio(portfolio_name, current_holdings):
    """Screen for new candidates for a specific portfolio.

    Returns list of dicts: [{"ticker": str, "gate_result": dict}, ...]
    """
    screen_config = PORTFOLIO_SCREENS.get(portfolio_name)
    if not screen_config:
        log.warning(f"No screen config for {portfolio_name}")
        return []

    held_tickers = current_holdings.get(portfolio_name, set())
    # Also exclude tickers held in ANY portfolio to avoid concentration
    all_held = set()
    for tickers in current_holdings.values():
        all_held.update(tickers)

    # Run all filter sets for this portfolio
    raw_candidates = set()
    for i, filters in enumerate(screen_config["filters"]):
        log.info(f"  Screen {i+1}/{len(screen_config['filters'])} for {portfolio_name}...")
        tickers = run_finviz_screen(filters)
        raw_candidates.update(tickers)
        time.sleep(FINVIZ_DELAY)

    log.info(f"  {portfolio_name}: {len(raw_candidates)} raw candidates from Finviz")

    # Remove already-held tickers (in this portfolio — cross-portfolio holdings are OK for candidates)
    raw_candidates -= held_tickers

    # Fetch yfinance info for gate checks
    candidates = []
    gate_blocked = 0
    gate_ai_allowed = 0

    for ticker in sorted(raw_candidates):
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            continue

        # Run IPS style gate — criteria are authoritative, no AI override
        gate_result = passes_style_gate(
            ticker, portfolio_name, info,
            context="candidate_screen"
        )

        if gate_result["pass"]:
            candidates.append({
                "ticker": ticker,
                "gate_result": gate_result,
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
            })
            if gate_result.get("ai_decision") == "ALLOW":
                gate_ai_allowed += 1
                log.info(f"    AI ALLOWED: {ticker} — {gate_result.get('ai_reason', '')}")
        else:
            gate_blocked += 1

    log.info(f"  {portfolio_name}: {len(candidates)} pass gates ({gate_blocked} blocked, {gate_ai_allowed} AI-allowed)")

    # No cap: gates are the screening method. The decision engine scores all
    # candidates and selects top N for trading. Truncating here introduced an
    # alphabetic bias (sorted() + [:N] = alphabetically first N).

    return candidates


def update_universes(portfolio_name, new_candidates, current_holdings, universes):
    """Update portfolio_universes.json with new candidates while preserving holdings."""
    held_tickers = sorted(current_holdings.get(portfolio_name, set()))
    existing = universes.get(portfolio_name, {})
    old_candidates = set(existing.get("candidates", []))

    new_tickers = {c["ticker"] for c in new_candidates}

    # Merge: keep existing candidates that are still valid, add new ones
    merged = sorted(old_candidates | new_tickers)

    # Remove any that are now holdings (promoted from candidate)
    merged = [t for t in merged if t not in set(held_tickers)]

    # No cap on merged universe: union of old + new gate-passers, deduplicated.
    # Each Saturday's screen contributes whatever it finds; the decision engine
    # scores everything and picks the top 10 to actually hold per portfolio.

    universes[portfolio_name] = {
        "holdings": held_tickers,
        "candidates": merged,
    }

    added = new_tickers - old_candidates
    removed = old_candidates - set(merged)
    return added, removed


def main():
    parser = argparse.ArgumentParser(description="BigClaw Candidate Screener")
    parser.add_argument("--dry-run", action="store_true", help="Show candidates without updating universes")
    parser.add_argument("--portfolio", type=str, help="Screen a single portfolio")
    args = parser.parse_args()

    log.info("=== BigClaw Candidate Screener ===")
    log.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    current_holdings = get_current_holdings()
    universes = load_current_universes()

    portfolios = [args.portfolio] if args.portfolio else list(PORTFOLIO_SCREENS.keys())

    summary = []
    total_new = 0

    for pname in portfolios:
        log.info(f"\nScreening: {pname}")
        candidates = screen_portfolio(pname, current_holdings)

        if args.dry_run:
            log.info(f"  [DRY RUN] Would add {len(candidates)} candidates:")
            for c in candidates:
                log.info(f"    {c['ticker']:6s} — {c['sector']} / {c['industry']}")
        else:
            added, removed = update_universes(pname, candidates, current_holdings, universes)
            total_new += len(added)
            if added:
                log.info(f"  Added: {', '.join(sorted(added))}")
            if removed:
                log.info(f"  Removed (stale): {', '.join(sorted(removed))}")

        summary.append({
            "portfolio": pname,
            "screened": len(candidates),
        })

    if not args.dry_run:
        # Save updated universes
        with open(UNIVERSES_PATH, "w") as f:
            json.dump(universes, f, indent=2)
        log.info(f"\nUpdated {UNIVERSES_PATH}")
        log.info(f"Total: {total_new} new candidates across {len(portfolios)} portfolios")
    else:
        log.info(f"\n[DRY RUN] No changes made.")

    # Print summary table
    log.info("\n=== Screening Summary ===")
    for s in summary:
        log.info(f"  {s['portfolio']:28s} — {s['screened']:3d} candidates")

    return summary


if __name__ == "__main__":
    main()
