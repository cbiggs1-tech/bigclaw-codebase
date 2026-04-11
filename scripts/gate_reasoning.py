#!/usr/bin/env python3
"""BigClaw AI Gate Reasoning — Opus-powered judgment for borderline style gate calls.

When a style gate check returns a borderline failure (severity='gate', not 'reject'),
this module sends the context to Claude Opus for a BLOCK/ALLOW decision with reasoning.

Hard REJECTs (P/E > 60 in value fund, zero dividend in income, wrong sector) bypass
this entirely — no AI needed for clear-cut violations.

Wired into style_gates.passes_style_gate() automatically.

Cost: ~$0.02 per call, ~2-5 calls per trading day = ~$0.10/day max.
"""

import json
import logging
import os
import sys

log = logging.getLogger("gate_reasoning")

# Model selection — Opus for high-judgment, low-volume decisions
MODEL = "claude-opus-4-6"

# Cache to avoid re-calling for same ticker+portfolio in one session
_session_cache = {}

SYSTEM_PROMPT = """You are BigClaw's style gate reviewer. BigClaw is an autonomous trading system managing 7 portfolios, each with a distinct investment philosophy.

A style gate check has flagged a stock as borderline. This happens in three contexts:
1. PRE-BUY GATE: A candidate was blocked from purchase. Should we let it in?
2. HOLDING AUDIT: A current holding is drifting out of style. Is this real drift or temporary?
3. CANDIDATE SCREEN: A potential new candidate almost passes the gate. Is it good enough to compete?

Your job: determine if this is a REAL style violation or a DATA ARTIFACT / EDGE CASE.

Guidelines:
- BLOCK if the stock genuinely doesn't fit the portfolio's philosophy
- ALLOW if the numbers are misleading due to one-time items, trailing data lag, entity-type mismatch (REIT/MLP), or sector classification quirks
- Look at the TREND, not just the snapshot — one bad quarter doesn't define a company
- Consider forward estimates vs trailing actuals — trailing can be stale
- A stock that narrowly misses ONE criterion but excels on all others may deserve ALLOW
- For holding audits: distinguish between permanent deterioration vs temporary data noise
- Be concise: 1-3 sentences explaining your reasoning

Reply format (exactly):
DECISION: BLOCK or ALLOW
REASON: Your 1-3 sentence explanation"""


def _load_portfolio_style(portfolio_name):
    """Load the relevant portfolio style section from PORTFOLIO_STYLES.md."""
    style_path = os.path.expanduser("~/.openclaw/workspace/PORTFOLIO_STYLES.md")
    try:
        with open(style_path, "r") as f:
            content = f.read()
        # Extract just the relevant portfolio section
        # Look for the portfolio header and grab until the next portfolio header
        lines = content.split("\n")
        capturing = False
        section = []
        for line in lines:
            if portfolio_name.lower() in line.lower() and line.startswith("#"):
                capturing = True
            elif capturing and line.startswith("### ") and portfolio_name.lower() not in line.lower():
                break
            if capturing:
                section.append(line)
        return "\n".join(section) if section else f"Portfolio: {portfolio_name}"
    except FileNotFoundError:
        return f"Portfolio: {portfolio_name}"


def _get_earnings_context(ticker):
    """Run earnings_analyzer and return structured output."""
    try:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, scripts_dir)
        from earnings_analyzer import analyze_ticker
        data = analyze_ticker(ticker)
        # Compact the output — only the parts that matter for gate reasoning
        compact = {
            "ticker": ticker,
            "last_earnings": data.get("step1_numbers", {}),
            "guidance": data.get("step2_guidance", {}),
            "quarterly_trend": data.get("step3_segments", {}).get("quarters", []),
            "market_reaction": {
                k: v for k, v in data.get("step5_reaction", {}).items()
                if k in ("close_before_earnings", "close_after_earnings", "price_change_pct",
                         "analyst_target_price", "analyst_recommendation")
            },
        }
        return compact
    except Exception as e:
        log.warning(f"Could not run earnings_analyzer for {ticker}: {e}")
        return None


def _format_info_summary(info):
    """Extract key metrics from yfinance info for the prompt."""
    keys = [
        "trailingPE", "forwardPE", "trailingEps", "forwardEps",
        "earningsGrowth", "earningsQuarterlyGrowth", "revenueGrowth",
        "returnOnEquity", "freeCashflow", "grossMargins", "operatingMargins",
        "payoutRatio", "dividendYield", "debtToEquity", "marketCap",
        "sector", "industry", "shortPercentOfFloat",
        "heldPercentInstitutions", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    ]
    summary = {}
    for k in keys:
        v = info.get(k)
        if v is not None:
            # Format large numbers
            if k in ("freeCashflow", "marketCap") and isinstance(v, (int, float)):
                summary[k] = f"${v/1e9:.1f}B"
            elif k in ("returnOnEquity", "grossMargins", "operatingMargins",
                        "earningsGrowth", "earningsQuarterlyGrowth", "revenueGrowth",
                        "dividendYield", "payoutRatio") and isinstance(v, (int, float)):
                summary[k] = f"{v:.1%}"
            else:
                summary[k] = v
    return summary


def reason_borderline_gate(ticker, portfolio_name, gate_result, info, context="pre_buy"):
    """Call Opus to reason about a borderline gate failure.

    Args:
        ticker: Stock ticker
        portfolio_name: Which portfolio's gate failed
        gate_result: The gate check result dict (from style_gates)
        info: yfinance .info dict
        context: One of "pre_buy", "holding_audit", "candidate_screen"

    Returns:
        dict: {"decision": "ALLOW"|"BLOCK", "reason": str, "model": str}
        Returns None if API call fails (caller should default to BLOCK).
    """
    cache_key = f"{ticker}:{portfolio_name}:{context}"
    if cache_key in _session_cache:
        return _session_cache[cache_key]

    try:
        import anthropic
    except ImportError:
        log.error("anthropic SDK not installed — cannot reason about borderline gate")
        return None

    # Build the context
    style_section = _load_portfolio_style(portfolio_name)
    info_summary = _format_info_summary(info) if info else {}
    earnings_context = _get_earnings_context(ticker)

    context_labels = {
        "pre_buy": "PRE-BUY GATE — this stock was blocked from purchase",
        "holding_audit": "HOLDING AUDIT — this is a current holding that may be drifting out of style",
        "candidate_screen": "CANDIDATE SCREEN — this stock almost passed the gate and may deserve a spot as a candidate",
    }

    user_message = f"""## Gate Check Failure

**Context:** {context_labels.get(context, context)}
**Ticker:** {ticker}
**Portfolio:** {portfolio_name}
**Gate result:** {gate_result.get('reason', 'unknown')}
**Severity:** {gate_result.get('severity', 'gate')} (borderline — not a hard reject)

## Portfolio Style Rules
{style_section}

## Current Metrics (yfinance)
{json.dumps(info_summary, indent=2)}

## Earnings Analysis
{json.dumps(earnings_context, indent=2, default=str) if earnings_context else "Earnings data unavailable"}

Based on the above, is this gate failure a legitimate style violation, or a data artifact that should be overridden?"""

    try:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            # Try loading from .env_secrets
            secrets_path = os.path.expanduser("~/.env_secrets")
            if os.path.exists(secrets_path):
                with open(secrets_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("export ANTHROPIC_API_KEY=") or line.startswith("ANTHROPIC_API_KEY="):
                            api_key = line.split("=", 1)[1].strip().strip("'\"")
                            break

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        text = response.content[0].text.strip()

        # Parse the response
        decision = "BLOCK"  # default to safe
        reason = text

        for line in text.split("\n"):
            line = line.strip()
            if line.upper().startswith("DECISION:"):
                d = line.split(":", 1)[1].strip().upper()
                if "ALLOW" in d:
                    decision = "ALLOW"
                else:
                    decision = "BLOCK"
            elif line.upper().startswith("REASON:"):
                reason = line.split(":", 1)[1].strip()

        result = {
            "decision": decision,
            "reason": reason,
            "model": MODEL,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        log.info(f"Gate reasoning for {ticker}/{portfolio_name}: {decision} — {reason}")
        _session_cache[cache_key] = result
        return result

    except Exception as e:
        log.error(f"Gate reasoning API call failed for {ticker}/{portfolio_name}: {e}")
        return None


def clear_session_cache():
    """Clear the session cache (call at start of each trading day)."""
    _session_cache.clear()
