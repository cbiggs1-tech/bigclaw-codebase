#!/usr/bin/env python3
"""Export signals and macro data to JSON for the BigClaw website."""

import json
import os
import subprocess
import sys
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.expanduser("~/bigclaw-ai/src/portfolios.db")

def enrich_signals_with_holdings(signals_path):
    """Annotate each signal with portfolio holding context from the DB."""
    import sqlite3
    try:
        with open(signals_path, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    signals = data.get("signals", [])
    if not signals:
        return

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    c = conn.cursor()

    # Get all active holdings with portfolio info
    c.execute("""
        SELECT h.ticker, p.name, h.shares, h.avg_cost,
               p.current_cash,
               (SELECT SUM(h2.shares * h2.avg_cost) FROM holdings h2
                WHERE h2.portfolio_id = p.id AND h2.shares > 0) as portfolio_cost,
               (SELECT COUNT(*) FROM holdings h2
                WHERE h2.portfolio_id = p.id AND h2.shares > 0) as num_holdings
        FROM holdings h
        JOIN portfolios p ON h.portfolio_id = p.id
        WHERE p.is_active = 1 AND h.shares > 0
    """)

    # Build lookup: ticker -> list of {portfolio, shares, pct, at_max_holdings}
    holdings_map = {}
    for row in c.fetchall():
        ticker, pname, shares, avg_cost, cash, portfolio_cost, num_holdings = row
        position_value = shares * avg_cost
        total_value = (portfolio_cost or 0) + (cash or 0)
        pct = (position_value / total_value * 100) if total_value > 0 else 0

        if ticker not in holdings_map:
            holdings_map[ticker] = []
        holdings_map[ticker].append({
            "portfolio": pname,
            "shares": shares,
            "position_pct": round(pct, 1),
            "at_max_position": pct >= 19.5,  # ~20% cap
            "at_max_holdings": num_holdings >= 10,
        })

    conn.close()

    # Annotate each signal
    for s in signals:
        t = s.get("ticker", "")
        if t in holdings_map:
            s["held_in"] = holdings_map[t]
        else:
            s["held_in"] = []

    # Enrich with swap recommendations from portfolio_optimization
    opt = data.get("portfolio_optimization", {})
    swap_map = {}  # ticker -> list of swap info
    for pname, pdata in opt.items():
        for swap in pdata.get("swap_recommendations", []):
            sell_t = swap.get("sell", "")
            buy_t = swap.get("buy", "")
            swap_info = {
                "portfolio": pname,
                "sell": sell_t,
                "sell_score": swap.get("sell_score", 0),
                "buy": buy_t,
                "buy_score": swap.get("buy_score", 0),
                "score_diff": swap.get("score_diff", 0),
            }
            # Tag the sell ticker
            if sell_t not in swap_map:
                swap_map[sell_t] = []
            swap_map[sell_t].append({"action": "SWAP OUT", **swap_info})
            # Tag the buy ticker
            if buy_t not in swap_map:
                swap_map[buy_t] = []
            swap_map[buy_t].append({"action": "SWAP IN", **swap_info})

    for s in signals:
        t = s.get("ticker", "")
        s["pending_swaps"] = swap_map.get(t, [])

    _tmp = f"{signals_path}.tmp.{os.getpid()}"
    with open(_tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    os.replace(_tmp, signals_path)
    enriched = len([s for s in signals if s.get("held_in")])
    swapped = len([s for s in signals if s.get("pending_swaps")])
    print(f"  ✅ Enriched {enriched} signals with holdings, {swapped} with swap context", file=sys.stderr)


DATA_DIR = os.path.expanduser("~/bigclaw-ai/docs/data")

def run_script(cmd, output_file, label):
    """Run a script, capture JSON stdout, save to file."""
    print(f"[export_signals] Running {label}...", file=sys.stderr)
    try:
        result = subprocess.run(
            # 1800s = 30 min. Decision engine subprocess can run 15-25 min
            # after the May 8 bias fix lifted the candidate cap.
            cmd, capture_output=True, text=True, timeout=1800,
            cwd=SCRIPTS_DIR,
            env={**os.environ}
        )
        if result.returncode != 0:
            print(f"  ⚠ {label} failed (exit {result.returncode})", file=sys.stderr)
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}", file=sys.stderr)
            return False

        stdout = result.stdout.strip()
        if not stdout:
            print(f"  ⚠ {label} produced no output", file=sys.stderr)
            return False

        # Validate JSON
        data = json.loads(stdout)
        _tmp = f"{output_file}.tmp.{os.getpid()}"
        with open(_tmp, "w") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(_tmp, output_file)
        print(f"  ✅ {label} → {output_file}", file=sys.stderr)
        return True

    except json.JSONDecodeError as e:
        print(f"  ⚠ {label} output is not valid JSON: {e}", file=sys.stderr)
        # Save raw output for debugging
        with open(output_file + ".raw", "w") as f:
            f.write(stdout)
        return False
    except subprocess.TimeoutExpired:
        print(f"  ⚠ {label} timed out (600s)", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  ⚠ {label} error: {e}", file=sys.stderr)
        return False


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    results = {}

    # Decision Engine → signals.json
    results["signals"] = run_script(
        [sys.executable, "decision_engine.py", "--json", "--rescreen"],
        os.path.join(DATA_DIR, "signals.json"),
        "Decision Engine"
    )

    # Enrich signals with portfolio holding context
    if results["signals"]:
        enrich_signals_with_holdings(os.path.join(DATA_DIR, "signals.json"))

    # Build cash-aware planned actions for dashboard
    if results['signals']:
        try:
            from build_planned_actions import inject_planned_actions
            inject_planned_actions()
        except Exception as e:
            print(f'  Planned actions failed (non-fatal): {e}', file=sys.stderr)

    # Build executed trades list for dashboard
    if results["signals"]:
        try:
            from fix_executed_tracking import inject_executed_trades
            inject_executed_trades()
        except Exception as e:
            print(f"  Executed trades failed (non-fatal): {e}", file=sys.stderr)

    # Macro Scanner → macro.json
    results["macro"] = run_script(
        [sys.executable, "macro_scanner.py", "--json"],
        os.path.join(DATA_DIR, "macro.json"),
        "Macro Scanner"
    )

    # Update metadata
    metadata_path = os.path.join(DATA_DIR, "metadata.json")
    try:
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        metadata = {}

    metadata["signals_updated"] = datetime.now().isoformat()
    metadata["signals_export_results"] = results

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  ✅ metadata → {metadata_path}", file=sys.stderr)

    success = all(results.values())
    print(f"\n[export_signals] Done. {'All succeeded ✅' if success else 'Some failed ⚠'}", file=sys.stderr)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
