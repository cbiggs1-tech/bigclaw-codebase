#!/usr/bin/env python3
"""BigClaw Style Compliance Auditor — weekly fund thesis validation.

Checks that each portfolio's holdings align with its investment style.
Catches drift that went undetected for 2 months (Feb-Mar 2026).

Three checks per portfolio:
1. Holdings characteristics match style expectations
2. Same ticker scores differently across portfolio styles (weights working)
3. No style-contradicting positions (e.g., Graham fund holding 200x P/E stock)

Usage:
    python3 style_compliance.py           # Full report to stdout
    python3 style_compliance.py --json    # Machine-readable output
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

import yfinance as yf

from bigclaw_logging import get_logger
from bigclaw_retry import retry
from style_gates import passes_style_gate

log = get_logger("compliance")

DB_PATH = os.path.expanduser("~/bigclaw-ai/src/portfolios.db")

# Style expectations: what each portfolio SHOULD look like
# "require" = holdings should generally meet these criteria
# "reject" = holdings matching these are red flags
STYLE_RULES = {
    "Value Picks": {
        "label": "Quality Value (Buffett/Graham IPS April 2026)",
        "require": {
            "positive_eps": {"desc": "positive earnings", "check": lambda info: (info.get("trailingEps") or 0) > 0},
            "roe_floor": {"desc": "ROE >= 15%", "check": lambda info: (info.get("returnOnEquity") or 0) >= 0.15},
        },
        "reject": {
            "pe_extreme": {"desc": "P/E > 50", "check": lambda info: (info.get("trailingPE") or 0) > 50},
            "negative_eps": {"desc": "negative earnings", "check": lambda info: (info.get("trailingEps") or 0) < 0},
        },
        "audit": {
            "pe_drift": {"desc": "P/E > 30", "check": lambda info: (info.get("trailingPE") or 0) > 30},
            "roe_drop": {"desc": "ROE < 12%", "check": lambda info: (info.get("returnOnEquity") or 0) < 0.12},
        },
        "min_yield": None,
    },
    "Growth Value": {
        "label": "Peter Lynch GARP (IPS April 2026)",
        "require": {
            "positive_eps": {"desc": "positive earnings", "check": lambda info: (info.get("trailingEps") or 0) > 0},
            "has_growth": {"desc": "earnings growing", "check": lambda info: (info.get("earningsGrowth") or 0) > 0},
        },
        "reject": {
            "peg_extreme": {"desc": "PEG > 2.0", "check": lambda info: (info.get("pegRatio") or 0) > 2.0},
            "pe_extreme": {"desc": "P/E > 40", "check": lambda info: (info.get("trailingPE") or 0) > 40},
        },
        "audit": {
            "peg_drift": {"desc": "PEG > 1.5", "check": lambda info: (info.get("pegRatio") or 0) > 1.5},
        },
        "min_yield": None,
    },
    "Income Dividends": {
        "label": "Income / Dividend Growth (IPS April 2026)",
        "require": {
            "has_dividend": {"desc": "pays dividend", "check": lambda info: (info.get("dividendYield") or 0) > 0},
            "decent_yield": {"desc": "yield >= 1.5%", "check": lambda info: (info.get("dividendYield") or 0) >= 0.015},
        },
        "reject": {
            "no_dividend": {"desc": "dividend eliminated", "check": lambda info: (info.get("dividendYield") or 0) <= 0},
            "payout_extreme": {"desc": "payout > 100%", "check": lambda info: (info.get("payoutRatio") or 0) > 1.0},
        },
        "audit": {
            "payout_elevated": {"desc": "payout > 60%", "check": lambda info: (info.get("payoutRatio") or 0) > 0.60},
            "yield_spike": {"desc": "yield > 6%", "check": lambda info: (info.get("dividendYield") or 0) > 0.06},
        },
        "min_yield": 0.015,
    },
    "Momentum Growth": {
        "label": "CANSLIM Momentum (IPS April 2026)",
        "require": {
            "positive_eps": {"desc": "positive earnings", "check": lambda info: (info.get("trailingEps") or 0) > 0},
        },
        "reject": {
            "earnings_collapse": {"desc": "quarterly EPS decline > 20%", "check": lambda info: (info.get("earningsQuarterlyGrowth") or 0) < -0.20},
        },
        "min_yield": None,
    },
    "Nuclear Renaissance": {
        "label": "Domain Expertise — Nuclear/Energy (IPS April 2026)",
        "require": {
            "on_whitelist": {"desc": "on nuclear whitelist", "check": lambda info: True},  # Checked in style_gates
            "revenue_positive": {"desc": "revenue growing", "check": lambda info: (info.get("revenueGrowth") or 0) >= 0},
        },
        "reject": {
            "short_extreme": {"desc": "short interest > 35%", "check": lambda info: (info.get("shortPercentOfFloat") or 0) > 0.35},
        },
        "audit": {
            "short_elevated": {"desc": "short interest > 25%", "check": lambda info: (info.get("shortPercentOfFloat") or 0) > 0.25},
            "pe_extreme": {"desc": "P/E > 50 (Core)", "check": lambda info: (info.get("trailingPE") or 0) > 50},
            "revenue_declining": {"desc": "revenue declining", "check": lambda info: (info.get("revenueGrowth") or 0) < 0},
        },
        "min_yield": None,
    },
    "Innovation Fund": {
        "label": "Disruptive Innovation / Cathie Wood (IPS April 2026)",
        "require": {
            "revenue_growing": {"desc": "revenue growth >= 15%", "check": lambda info: (info.get("revenueGrowth") or 0) >= 0.15},
        },
        "reject": {
            "dividend_heavy": {"desc": "dividend yield > 3%", "check": lambda info: (info.get("dividendYield") or 0) > 0.03},
        },
        "audit": {
            "revenue_slowing": {"desc": "revenue growth < 20%", "check": lambda info: 0.15 <= (info.get("revenueGrowth") or 0) < 0.20},
            "high_debt": {"desc": "D/E > 2.0", "check": lambda info: (info.get("debtToEquity") or 0) > 200},
        },
        "min_yield": None,
    },
    "AI Defense & Autonomous": {
        "label": "Pentagon Thematic (IPS April 2026)",
        "require": {
            "on_whitelist": {"desc": "on defense whitelist", "check": lambda info: True},
            "revenue_positive": {"desc": "revenue growing", "check": lambda info: (info.get("revenueGrowth") or 0) >= 0},
        },
        "reject": {
            "short_extreme": {"desc": "short > 30%", "check": lambda info: (info.get("shortPercentOfFloat") or 0) > 0.30},
            "revenue_collapse": {"desc": "revenue decline > 20%", "check": lambda info: (info.get("revenueGrowth") or 0) < -0.20},
        },
        "audit": {
            "short_elevated": {"desc": "short > 20%", "check": lambda info: (info.get("shortPercentOfFloat") or 0) > 0.20},
            "pe_extreme": {"desc": "P/E > 100", "check": lambda info: (info.get("trailingPE") or 0) > 100},
            "negative_fcf": {"desc": "negative FCF", "check": lambda info: (info.get("freeCashflow") or 0) < 0},
        },
        "min_yield": None,
    },
}


def get_holdings():
    """Load current holdings per portfolio from DB."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    rows = conn.execute("""
        SELECT p.name, h.ticker, h.shares, h.avg_cost
        FROM portfolios p JOIN holdings h ON p.id = h.portfolio_id
        WHERE p.is_active = 1 AND h.shares > 0
        ORDER BY p.name, h.ticker
    """).fetchall()
    conn.close()

    portfolios = {}
    for pname, ticker, shares, avg_cost in rows:
        if pname not in portfolios:
            portfolios[pname] = []
        portfolios[pname].append({"ticker": ticker, "shares": shares, "avg_cost": avg_cost})
    return portfolios


def fetch_info_batch(tickers):
    """Fetch yfinance info for all tickers."""
    info_map = {}
    for ticker in tickers:
        try:
            data = retry(
                lambda t=ticker: yf.Ticker(t).info or {},
                attempts=2, delay=3, label=f"yf.info({ticker})"
            )
            info_map[ticker] = data
        except Exception as e:
            log.warning(f"Could not fetch info for {ticker}: {e}")
            info_map[ticker] = {}
    return info_map


def check_technical(ticker, check_type):
    """Check technical conditions for a ticker."""
    try:
        from ta.trend import SMAIndicator
        data = retry(
            lambda: yf.download(ticker, period="3mo", progress=False),
            attempts=2, delay=3, label=f"yf.download({ticker})"
        )
        close = data["Close"].dropna()
        if len(close) < 50:
            return None  # Insufficient data

        if check_type == "sma50":
            sma50 = SMAIndicator(close, window=50).sma_indicator().iloc[-1]
            current = close.iloc[-1]
            return float(current) > float(sma50)
    except Exception:
        return None


def check_style_divergence(info_map):
    """Verify that style weights produce different scores across portfolios.

    Two-level check:
    1. Weight vectors must be unique across all 7 portfolios
    2. A synthetic signal vector must produce different scores when weighted by each style
    This catches both the old naming mismatch bug AND asymmetric scoring issues.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from decision_engine import STYLE_WEIGHTS, DEFAULT_STYLE_WEIGHTS

    style_names = list(STYLE_WEIGHTS.keys())

    # Level 1: Weight vector uniqueness
    weight_vectors = {}
    for sname in style_names:
        w = STYLE_WEIGHTS[sname]
        sig = tuple(sorted(w.items()))
        weight_vectors[sname] = sig

    unique_sigs = set(weight_vectors.values())
    if len(unique_sigs) == 1:
        return {
            "status": "FAIL",
            "reason": "ALL portfolio styles have identical weights — scoring is NOT style-specific!",
            "severity": "CRITICAL",
        }

    dupes = {}
    for sname, sig in weight_vectors.items():
        dupes.setdefault(sig, []).append(sname)
    identical_groups = {k: v for k, v in dupes.items() if len(v) > 1}

    # Level 2: Synthetic scoring test
    # Create a signal vector where every category scores +1.
    # Each style should produce a different total because weights differ.
    all_cats = sorted(DEFAULT_STYLE_WEIGHTS.keys())
    synthetic_signals = [(cat, 1, f"test_{cat}") for cat in all_cats]

    style_scores = {}
    for sname in style_names:
        w = STYLE_WEIGHTS[sname]
        total = sum(1 * w.get(cat, 1.0) for cat, _, _ in synthetic_signals)
        style_scores[sname] = round(total, 2)

    unique_scores = set(style_scores.values())

    # Also check that no category in STYLE_WEIGHTS is missing from emitted signals
    missing_keys = []
    for sname in style_names:
        for key in STYLE_WEIGHTS[sname]:
            if key not in DEFAULT_STYLE_WEIGHTS:
                missing_keys.append(f"{sname}.{key}")

    issues = []
    if identical_groups:
        issues.append(f"Identical weight vectors: {[v for v in identical_groups.values()]}")
    if len(unique_scores) < len(style_names):
        score_dupes = {}
        for sname, sc in style_scores.items():
            score_dupes.setdefault(sc, []).append(sname)
        score_identical = {k: v for k, v in score_dupes.items() if len(v) > 1}
        issues.append(f"Identical synthetic scores: {[v for v in score_identical.values()]}")
    if missing_keys:
        issues.append(f"Keys in STYLE_WEIGHTS not in DEFAULT: {missing_keys}")

    if issues:
        return {
            "status": "WARN" if len(unique_sigs) > 1 else "FAIL",
            "reason": "; ".join(issues),
            "severity": "WARNING" if len(unique_sigs) > 1 else "CRITICAL",
            "style_scores": style_scores,
        }
    else:
        return {
            "status": "PASS",
            "reason": f"All {len(style_names)} styles have unique weights and produce distinct scores",
            "style_scores": style_scores,
        }


def run_audit():
    """Run the full compliance audit."""
    log.info("Starting style compliance audit")
    portfolios = get_holdings()

    # Collect all tickers
    all_tickers = set()
    for holdings in portfolios.values():
        for h in holdings:
            all_tickers.add(h["ticker"])

    log.info(f"Fetching data for {len(all_tickers)} tickers across {len(portfolios)} portfolios")
    info_map = fetch_info_batch(all_tickers)

    results = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "portfolios": {},
        "style_divergence": check_style_divergence(info_map),
        "summary": {"pass": 0, "warn": 0, "fail": 0},
    }

    for pname, holdings in portfolios.items():
        rules = STYLE_RULES.get(pname)
        if not rules:
            results["portfolios"][pname] = {"status": "skip", "reason": "no style rules defined"}
            continue

        port_result = {
            "label": rules["label"],
            "holdings_count": len(holdings),
            "violations": [],
            "warnings": [],
            "passes": [],
        }

        # Check each holding against style gates (with AI reasoning for borderline cases)
        for h in holdings:
            ticker = h["ticker"]
            info = info_map.get(ticker, {})

            # Use the unified gate check — same gates as pre-buy, applied to current holdings
            gate_result = passes_style_gate(
                ticker, pname, info,
                use_ai_reasoning=True,
                context="holding_audit"
            )

            if gate_result["pass"]:
                if gate_result.get("ai_decision") == "ALLOW":
                    # AI overrode a borderline failure — note it as a pass with context
                    port_result["passes"].append(
                        f"{ticker}: borderline but AI approved — {gate_result.get('ai_reason', '')}"
                    )
                else:
                    port_result["passes"].append(f"{ticker}: passes style gate")
            elif gate_result.get("severity") == "reject":
                # Hard violation
                port_result["violations"].append(
                    f"{ticker}: {gate_result['reason']}"
                )
            else:
                # Borderline failure — AI was consulted and agreed to block
                ai_note = ""
                if gate_result.get("ai_decision") == "BLOCK":
                    ai_note = f" (AI confirmed: {gate_result.get('ai_reason', '')})"
                port_result["warnings"].append(
                    f"{ticker}: {gate_result['reason']}{ai_note}"
                )

            # Also run the legacy require/reject checks for any rules not covered by gates
            for check_name, check_def in rules.get("require", {}).items():
                try:
                    passed = check_def["check"](info)
                    if not passed:
                        msg = f"{ticker}: fails '{check_def['desc']}' requirement"
                        if msg not in port_result["warnings"]:
                            port_result["warnings"].append(msg)
                except Exception:
                    pass

            for check_name, check_def in rules.get("reject", {}).items():
                try:
                    triggered = check_def["check"](info)
                    if triggered:
                        msg = f"{ticker}: {check_def['desc']} — contradicts {rules['label']} thesis"
                        if msg not in port_result["violations"]:
                            port_result["violations"].append(msg)
                except Exception:
                    pass

        # Technical checks (e.g., momentum must be above SMA)
        for check_name, check_def in rules.get("technical_checks", {}).items():
            for h in holdings:
                result = check_technical(h["ticker"], check_def["check"])
                if result is False:
                    port_result["warnings"].append(
                        f"{h['ticker']}: NOT {check_def['desc']} — weak for momentum style"
                    )
                elif result is True:
                    port_result["passes"].append(f"{h['ticker']}: {check_def['desc']}")

        # Portfolio-level yield check
        min_yield = rules.get("min_yield")
        if min_yield is not None:
            yields = []
            for h in holdings:
                info = info_map.get(h["ticker"], {})
                dy = info.get("dividendYield") or info.get("trailingAnnualDividendYield") or 0
                yields.append(dy)
            avg_yield = sum(yields) / len(yields) if yields else 0
            if avg_yield < min_yield:
                port_result["warnings"].append(
                    f"Portfolio avg yield {avg_yield:.1%} below {min_yield:.0%} target for {rules['label']}"
                )
            else:
                port_result["passes"].append(f"Avg yield {avg_yield:.1%} meets {min_yield:.0%} target")

        # Determine status
        if port_result["violations"]:
            port_result["status"] = "FAIL"
            results["summary"]["fail"] += 1
        elif port_result["warnings"]:
            port_result["status"] = "WARN"
            results["summary"]["warn"] += 1
        else:
            port_result["status"] = "PASS"
            results["summary"]["pass"] += 1

        results["portfolios"][pname] = port_result

    # Check style divergence result
    div = results["style_divergence"]
    if div.get("status") == "FAIL":
        results["summary"]["fail"] += 1
    elif div.get("status") == "WARN":
        results["summary"]["warn"] += 1
    else:
        results["summary"]["pass"] += 1

    log.info(f"Audit complete: {results['summary']}")
    return results


def format_report(results):
    """Format audit results for Slack/stdout."""
    lines = []
    s = results["summary"]
    total = s["pass"] + s["warn"] + s["fail"]

    if s["fail"] > 0:
        lines.append(f"🔴 **Style Compliance Audit** — {s['fail']} FAILURES")
    elif s["warn"] > 0:
        lines.append(f"🟡 **Style Compliance Audit** — {s['warn']} warnings")
    else:
        lines.append(f"✅ **Style Compliance Audit** — all {total} checks passed")
    lines.append(f"*{results['date']}*\n")

    # Style divergence check
    div = results["style_divergence"]
    if div["status"] == "FAIL":
        lines.append(f"🚨 **CRITICAL: {div['reason']}**\n")
    elif div["status"] == "WARN":
        lines.append(f"⚠️ Style divergence: {div['reason']}\n")
    else:
        lines.append(f"✅ Style weights: {div['reason']}\n")

    # Per-portfolio results
    for pname, pr in sorted(results["portfolios"].items()):
        if pr.get("status") == "skip":
            continue

        icon = {"PASS": "✅", "WARN": "🟡", "FAIL": "🔴"}.get(pr["status"], "❓")
        lines.append(f"{icon} **{pname}** ({pr['label']}) — {pr['holdings_count']} holdings")

        for v in pr.get("violations", []):
            lines.append(f"  🔴 {v}")
        for w in pr.get("warnings", []):
            lines.append(f"  ⚠️ {w}")

        if not pr.get("violations") and not pr.get("warnings"):
            lines.append(f"  All holdings align with thesis")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="BigClaw Style Compliance Auditor")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = run_audit()

    if args.json:
        # Strip lambda functions before serializing
        clean = json.loads(json.dumps(results, default=str))
        print(json.dumps(clean, indent=2))
    else:
        print(format_report(results))

    # Save for cron to post
    report_file = "/tmp/bigclaw_compliance_report.txt"
    with open(report_file, "w") as f:
        f.write(format_report(results))

    # Exit code reflects status
    if results["summary"]["fail"] > 0:
        sys.exit(2)
    elif results["summary"]["warn"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
