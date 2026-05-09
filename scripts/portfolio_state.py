"""Portfolio state derived from transactions log.

The transactions table is the single source of truth. Holdings and cash
are computed views, not independently-mutated state. After every trade
recompute_from_transactions() rebuilds these views from the log so they
cannot drift from the transaction record.

Verification: derived state can be compared to Alpaca's authoritative
account state for the share-count axis. The cash axis is verified by the
double-entry invariant (starting - buys + sells = derived_cash).
"""
import sqlite3
from collections import defaultdict
from pathlib import Path

DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.row_factory = sqlite3.Row
    return c


def derive_state_from_transactions(portfolio_id: int):
    """Derive (cash, holdings_dict) for a portfolio from its transaction log.

    Pure function of the transactions log — cannot drift from what's recorded.
    Returns:
        cash: float — starting_cash - sum(buys.total_value) + sum(sells.total_value)
        holdings: dict[ticker -> shares] — net position from buys minus sells
    """
    conn = _conn()
    starting = conn.execute(
        "SELECT starting_cash FROM portfolios WHERE id = ?", (portfolio_id,)
    ).fetchone()["starting_cash"]

    txns = conn.execute(
        "SELECT ticker, action, shares, total_value FROM transactions "
        "WHERE portfolio_id = ? ORDER BY executed_at, id",
        (portfolio_id,),
    ).fetchall()
    conn.close()

    cash = float(starting)
    holdings = defaultdict(float)
    for t in txns:
        if t["action"] == "buy":
            cash -= t["total_value"]
            holdings[t["ticker"]] += t["shares"]
        elif t["action"] == "sell":
            cash += t["total_value"]
            holdings[t["ticker"]] -= t["shares"]

    holdings = {k: v for k, v in holdings.items() if abs(v) > 0.001}
    return cash, holdings


def reconcile_shadow_with_derived(portfolio_id: int):
    """Compare the shadow ledger (current_cash, holdings table) to the
    derived state from transactions log.

    Returns dict with cash_drift, holdings_drift, and the raw values.
    Zero drift = the shadow ledger is consistent with its own log.
    """
    derived_cash, derived_holdings = derive_state_from_transactions(portfolio_id)

    conn = _conn()
    shadow_cash = conn.execute(
        "SELECT current_cash FROM portfolios WHERE id = ?", (portfolio_id,)
    ).fetchone()["current_cash"]
    shadow_rows = conn.execute(
        "SELECT ticker, shares FROM holdings WHERE portfolio_id = ?", (portfolio_id,)
    ).fetchall()
    shadow_holdings = {r["ticker"]: float(r["shares"]) for r in shadow_rows}
    conn.close()

    cash_drift = shadow_cash - derived_cash

    holdings_drift = {}
    for t in set(derived_holdings) | set(shadow_holdings):
        sh = shadow_holdings.get(t, 0.0)
        de = derived_holdings.get(t, 0.0)
        if abs(sh - de) > 0.001:
            holdings_drift[t] = {"shadow": sh, "derived": de, "diff": sh - de}

    return {
        "cash_drift": cash_drift,
        "shadow_cash": shadow_cash,
        "derived_cash": derived_cash,
        "holdings_drift": holdings_drift,
        "shadow_holdings_count": len(shadow_holdings),
        "derived_holdings_count": len(derived_holdings),
    }


def rebuild_shadow_from_transactions(portfolio_id: int, dry_run=True):
    """Reset shadow ledger (holdings table + portfolios.current_cash) to
    match the derived state from transactions.

    Use only when transactions are known correct (e.g., after Monday's reset
    when both ledgers start clean, or after a forensic correction).
    """
    derived_cash, derived_holdings = derive_state_from_transactions(portfolio_id)

    if dry_run:
        return {"would_set_cash": derived_cash, "would_set_holdings": dict(derived_holdings)}

    conn = _conn()
    c = conn.cursor()
    c.execute("UPDATE portfolios SET current_cash = ? WHERE id = ?", (derived_cash, portfolio_id))
    c.execute("DELETE FROM holdings WHERE portfolio_id = ?", (portfolio_id,))
    for ticker, shares in derived_holdings.items():
        c.execute(
            "INSERT INTO holdings (portfolio_id, ticker, shares) VALUES (?, ?, ?)",
            (portfolio_id, ticker, shares),
        )
    conn.commit()
    conn.close()
    return {"set_cash": derived_cash, "set_holdings": dict(derived_holdings)}
