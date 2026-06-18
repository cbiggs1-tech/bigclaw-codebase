"""Research dossier generator — Phase A of the dossier-funnel architecture.

For each candidate ticker, pulls all available BigClaw + public data and
uses Claude API to synthesize into a structured Markdown document for
human review. The human (Curtis) does the qualitative analysis the
engine cannot.

Phase A scope: just generate the dossiers. Does NOT change any execution
logic. Trader continues to act on score/discipline rules. Dossiers are
purely informational outputs for review.

Inputs per ticker:
  - Current score breakdown (from signals.json)
  - target_price + analyst targets (from holdings + yfinance)
  - Forward EPS revision trend (from yfinance.eps_trend)
  - Recent insider transactions (from finviz)
  - News headlines (from existing news pipeline)
  - Options flow / max pain / dark pool (from options_flow.json)
  - Earnings dates (from existing earnings pipeline)

Output: docs/dossiers/{ticker}_{YYYYMMDD}.md

Usage:
  python3 research_dossier.py --ticker AMD
  python3 research_dossier.py --top10                  # All current top-10 candidates
  python3 research_dossier.py --portfolio "Innovation Fund"
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

BIGCLAW_HOME = Path.home() / "bigclaw-ai"
sys.path.insert(0, str(BIGCLAW_HOME / "scripts"))

DOSSIER_DIR = BIGCLAW_HOME / "docs" / "dossiers"
DOSSIER_DIR.mkdir(parents=True, exist_ok=True)


def load_secrets():
    secrets_file = Path.home() / ".env_secrets"
    secrets = {}
    if not secrets_file.exists():
        return secrets
    import re
    for line in secrets_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^export\s+", "", line)
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        secrets[k.strip()] = v.strip().strip('"').strip("'")
    return secrets


def gather_data(ticker):
    """Pull every available signal/data point for a ticker. Returns a dict."""
    import yfinance as yf
    data = {"ticker": ticker, "generated": datetime.now().isoformat()}

    # yfinance info
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        data["company_name"] = info.get("longName") or info.get("shortName") or ticker
        data["sector"] = info.get("sector", "")
        data["industry"] = info.get("industry", "")
        data["mcap"] = info.get("marketCap", 0)
        data["current_price"] = info.get("currentPrice") or info.get("regularMarketPrice")
        data["forward_pe"] = info.get("forwardPE")
        data["trailing_pe"] = info.get("trailingPE")
        data["revenue_growth"] = info.get("revenueGrowth")
        data["earnings_growth"] = info.get("earningsGrowth")
        data["target_mean"] = info.get("targetMeanPrice")
        data["target_high"] = info.get("targetHighPrice")
        data["target_low"] = info.get("targetLowPrice")
        data["n_analysts"] = info.get("numberOfAnalystOpinions")
        data["short_pct"] = info.get("shortPercentOfFloat")
        data["52w_high"] = info.get("fiftyTwoWeekHigh")
        data["52w_low"] = info.get("fiftyTwoWeekLow")

        # eps_trend
        trend = tk.eps_trend
        if trend is not None and not trend.empty:
            row = trend.loc["+1y"] if "+1y" in trend.index else None
            if row is not None:
                eps_now = row.get("current")
                eps_90d = row.get("90daysAgo")
                if eps_now is not None and eps_90d is not None and float(eps_90d) != 0:
                    data["forward_eps_revision_90d_pct"] = round(
                        (float(eps_now) - float(eps_90d)) / abs(float(eps_90d)) * 100, 1
                    )

        # eps_revisions
        revs = tk.eps_revisions
        if revs is not None and not revs.empty:
            for idx in ["+1y", "0y"]:
                if idx in revs.index:
                    r = revs.loc[idx]
                    data["analyst_up_30d"] = int(r.get("upLast30days", 0) or 0)
                    data["analyst_down_30d"] = int(r.get("downLast30days", 0) or 0)
                    break
    except Exception as e:
        data["yfinance_error"] = str(e)

    # BigClaw signals.json
    try:
        signals_path = BIGCLAW_HOME / "docs" / "data" / "signals.json"
        signals = json.loads(signals_path.read_text())
        for pname, sigs in signals.get("portfolio_signals", {}).items():
            if ticker in sigs:
                data.setdefault("bigclaw_scores", {})[pname] = sigs[ticker]
    except Exception:
        pass

    # Current BigClaw position (if held)
    try:
        import sqlite3
        conn = sqlite3.connect(BIGCLAW_HOME / "src" / "portfolios.db", timeout=10)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT p.name AS pname, h.shares, h.avg_cost, h.target_price, h.first_bought_at "
            "FROM holdings h JOIN portfolios p ON h.portfolio_id = p.id "
            "WHERE h.ticker = ? AND h.shares > 0",
            (ticker,),
        ).fetchone()
        if row:
            data["bigclaw_position"] = dict(row)
        conn.close()
    except Exception:
        pass

    return data


def synthesize_dossier(data, anthropic_api_key):
    """Call Claude to write a structured Markdown dossier from the data."""
    try:
        from anthropic import Anthropic
    except ImportError:
        return None, "anthropic package not installed"

    client = Anthropic(api_key=anthropic_api_key)
    ticker = data["ticker"]
    company = data.get("company_name", ticker)
    sector = data.get("sector", "")
    industry = data.get("industry", "")

    # Build a concise prompt with all the data
    prompt = f"""Generate a one-page research dossier for {ticker} ({company}, {sector} / {industry}).

This dossier is for a sophisticated investor to decide whether to add this position
to a model portfolio. Be specific, cite numbers, and call out what is uncertain.

# DATA AVAILABLE
{json.dumps(data, indent=2, default=str)}

# OUTPUT FORMAT (strict Markdown, no preamble):

## {ticker} — {company}
**Sector**: {sector} / {industry}  |  **Market cap**: $XB  |  **Generated**: <today>

### Signal Snapshot
- BigClaw score: <by portfolio if available>
- Analyst consensus: $X target ({{N}} analysts), {{X%}} upside from ${{current}}
- Forward EPS revisions: {{X%}} over 90 days ({{up/down/flat}})
- Forward P/E: {{X.X}} vs trailing {{Y.Y}}
- Revenue growth: {{X%}} YoY
- Short interest: {{X%}} of float

### Bull Case (3-4 specific points)
- Concrete catalysts, growth drivers, competitive moats
- Reference data points from above where possible

### Bear Case (3-4 specific points)
- Specific risks: market share loss, regulatory, sector headwinds
- Reference negative data (short interest, analyst downgrades, etc.)

### Key Unknowns (questions the data cant answer)
- 3-5 specific questions a domain expert should be asking
- Things that would change the thesis materially

### Recommendation
One sentence: Strong buy / Buy / Hold / Wait / Avoid — and why in 15 words or less.

Keep total length ~500-700 words. No fluff. Direct, data-cited prose."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text, None
    except Exception as e:
        return None, f"API error: {e}"


def write_dossier(ticker, content):
    today = datetime.now().strftime("%Y%m%d")
    path = DOSSIER_DIR / f"{ticker}_{today}.md"
    path.write_text(content)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker")
    parser.add_argument("--portfolio", help="All top-10 holdings of a portfolio")
    parser.add_argument("--top10", action="store_true",
                        help="All current top-10 picks across all portfolios")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show data only, dont call Claude")
    args = parser.parse_args()

    secrets = load_secrets()
    api_key = secrets.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set in ~/.env_secrets")
        sys.exit(1)

    tickers = []
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.portfolio:
        signals = json.loads((BIGCLAW_HOME / "docs" / "data" / "signals.json").read_text())
        pf_sigs = signals.get("portfolio_signals", {}).get(args.portfolio, {})
        ranked = sorted(pf_sigs.items(), key=lambda kv: -kv[1].get("score", 0))[:10]
        tickers = [t for t, _ in ranked]
    elif args.top10:
        signals = json.loads((BIGCLAW_HOME / "docs" / "data" / "signals.json").read_text())
        seen = set()
        for pname, pf_sigs in signals.get("portfolio_signals", {}).items():
            ranked = sorted(pf_sigs.items(), key=lambda kv: -kv[1].get("score", 0))[:10]
            for t, _ in ranked:
                if t not in seen:
                    tickers.append(t)
                    seen.add(t)
    else:
        parser.print_help()
        sys.exit(1)

    print(f"Generating dossiers for {len(tickers)} tickers...")
    for ticker in tickers:
        print(f"  {ticker}...", end=" ", flush=True)
        data = gather_data(ticker)
        if args.dry_run:
            print("dry-run, data only")
            print(json.dumps(data, indent=2, default=str))
            continue
        content, err = synthesize_dossier(data, api_key)
        if err:
            print(f"FAIL ({err})")
            continue
        path = write_dossier(ticker, content)
        print(f"-> {path.name}")
    print(f"\nDone. Dossiers written to {DOSSIER_DIR}/")


if __name__ == "__main__":
    main()
