"""Daily accounting audit — three invariants that must always hold.

Run as a cron at 06:15 CT daily (before daily_export at 06:30).

INVARIANT 1 (Cash double-entry, per portfolio):
    starting_cash - Σ(buys.total_value) + Σ(sells.total_value) = current_cash
    Tolerance: $0 exact. Failure = the shadow ledger has drifted from its
    own transaction log (a write went wrong somewhere).

INVARIANT 2 (Shares match Alpaca, per ticker):
    Σ(holdings.shares for ticker) = Alpaca position.qty
    Tolerance: 0 shares. Failure = a buy or sell didn't record the right
    qty (partial-fill bug, lost write, double-write).

INVARIANT 3 (Aggregate cash matches Alpaca account):
    Σ(per-portfolio current_cash) ≈ Alpaca.account.cash
    Tolerance: $5 (rounding noise). Failure = real cash exists at the
    broker that no portfolio claims.

If any invariant fails, write logs/ALPACA_MISMATCH.flag and post to Slack.
"""
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
import urllib.request

sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "scripts"))
from alpaca_symbols import from_alpaca
from portfolio_state import derive_state_from_transactions, reconcile_shadow_with_derived
from autonomous_trader import get_trading_client

DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
LOG_DIR = Path.home() / "bigclaw-ai" / "logs"
SLACK_CHANNEL = "D0ADHLUJ400"
TOLERANCE_INVARIANT_1 = 0.01  # one cent
TOLERANCE_INVARIANT_3 = 5.00  # $5 noise


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def audit_invariant_1():
    """Per-portfolio cash double-entry."""
    conn = _conn(); conn.row_factory = sqlite3.Row
    portfolios = conn.execute(
        "SELECT id, name, starting_cash, current_cash FROM portfolios WHERE is_active = 1"
    ).fetchall()
    results = []
    for p in portfolios:
        derived_cash, _ = derive_state_from_transactions(p["id"])
        diff = p["current_cash"] - derived_cash
        results.append({
            "portfolio": p["name"],
            "starting": p["starting_cash"],
            "shadow_cash": p["current_cash"],
            "derived_cash": derived_cash,
            "diff": diff,
            "ok": abs(diff) <= TOLERANCE_INVARIANT_1,
        })
    conn.close()
    return results


def audit_invariant_2(alpaca_client):
    """Aggregate share count per ticker, DB vs Alpaca."""
    positions = alpaca_client.get_all_positions()
    alpaca = {from_alpaca(p.symbol): float(p.qty) for p in positions}

    conn = _conn(); conn.row_factory = sqlite3.Row
    db_rows = conn.execute(
        "SELECT ticker, SUM(shares) AS total FROM holdings GROUP BY ticker"
    ).fetchall()
    conn.close()
    db = {r["ticker"]: float(r["total"]) for r in db_rows}

    drifts = []
    for ticker in set(db) | set(alpaca):
        d = db.get(ticker, 0.0); a = alpaca.get(ticker, 0.0)
        if abs(d - a) > 0.001:
            drifts.append({"ticker": ticker, "db": d, "alpaca": a, "diff": d - a})
    return drifts


def audit_invariant_3(alpaca_client):
    """Aggregate cash sum vs Alpaca account cash."""
    conn = _conn(); conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT SUM(current_cash) AS total FROM portfolios WHERE is_active = 1"
    ).fetchone()
    conn.close()
    db_total_cash = float(rows["total"] or 0)

    account = alpaca_client.get_account()
    alpaca_cash = float(account.cash)

    diff = db_total_cash - alpaca_cash
    return {
        "db_total_cash": db_total_cash,
        "alpaca_cash": alpaca_cash,
        "diff": diff,
        "ok": abs(diff) <= TOLERANCE_INVARIANT_3,
    }


def post_slack(message):
    secrets = {}
    secrets_path = Path.home() / ".env_secrets"
    if secrets_path.exists():
        import re
        for line in secrets_path.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                line = re.sub(r"^export\s+", "", line)
                k, v = line.split("=", 1)
                secrets[k.strip()] = v.strip().strip("'\"")
    token = secrets.get("SLACK_BOT_TOKEN", "")
    if not token: return
    payload = json.dumps({"channel": SLACK_CHANNEL, "text": message}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def run_audit(post_to_slack=True):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    client = get_trading_client()

    inv1 = audit_invariant_1()
    inv2 = audit_invariant_2(client)
    inv3 = audit_invariant_3(client)

    inv1_ok = all(r["ok"] for r in inv1)
    inv2_ok = len(inv2) == 0
    inv3_ok = inv3["ok"]
    overall = inv1_ok and inv2_ok and inv3_ok

    audit_record = {
        "timestamp": datetime.now().isoformat(),
        "overall_pass": overall,
        "invariant_1": inv1,
        "invariant_2": inv2,
        "invariant_3": inv3,
    }
    audit_log = LOG_DIR / "accounting_audit.jsonl"
    with audit_log.open("a") as f:
        f.write(json.dumps(audit_record) + "\n")

    # Print human-readable report
    lines = [f"BigClaw Accounting Audit — {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}"]
    lines.append(f"Overall: {'PASS' if overall else 'FAIL'}")
    lines.append("")
    lines.append("Invariant 1 — Per-portfolio cash double-entry:")
    for r in inv1:
        marker = "  OK " if r["ok"] else "  X  "
        lines.append(f"{marker}{r['portfolio']:<28s} shadow=${r['shadow_cash']:>11,.2f}  derived=${r['derived_cash']:>11,.2f}  diff=${r['diff']:>+10,.2f}")
    lines.append("")
    lines.append("Invariant 2 — DB shares match Alpaca shares:")
    if inv2_ok:
        lines.append("  OK  no share mismatches")
    else:
        for d in inv2:
            lines.append(f"  X   {d['ticker']:<8s} db={d['db']:>6.0f}  alpaca={d['alpaca']:>6.0f}  diff={d['diff']:>+6.0f}")
    lines.append("")
    lines.append("Invariant 3 — Aggregate cash matches Alpaca account:")
    marker = "  OK " if inv3["ok"] else "  X  "
    lines.append(f"{marker}DB sum=${inv3['db_total_cash']:>11,.2f}  Alpaca=${inv3['alpaca_cash']:>11,.2f}  diff=${inv3['diff']:>+10,.2f}")

    report = "\n".join(lines)
    print(report)

    if not overall:
        flag = LOG_DIR / "ALPACA_MISMATCH.flag"
        flag.write_text(json.dumps(audit_record, indent=2, default=str))
        if post_to_slack:
            post_slack(":rotating_light: *BigClaw Accounting Audit FAILED*\n```\n" + report + "\n```")
    elif post_to_slack:
        # Only post on success once a day to avoid noise
        post_slack(":white_check_mark: *BigClaw Accounting Audit: PASS*  (all 3 invariants clean)")

    return audit_record


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-slack", action="store_true")
    args = parser.parse_args()
    record = run_audit(post_to_slack=not args.no_slack)
    sys.exit(0 if record["overall_pass"] else 1)
