"""Single canonical entry point for recording a trade to the BigClaw DB.

Every code path that records a buy or sell MUST go through `record_trade()`.
This guarantees:

  RULE 1: shares written = filled_qty from Alpaca (caller's responsibility to pass)
  RULE 2: price written = filled_avg_price from Alpaca (caller's responsibility)
  RULE 3: total_value written = filled_qty * filled_avg_price (caller's responsibility)
  RULE 4: cash is RECOMPUTED from the transactions log, never additively updated
  RULE 5: holdings DELETE only on full close, otherwise decrement
  RULE 6: order_id stored alongside the transaction for direct broker cross-check

Cash recomputation formula (Rule 4):
    current_cash = starting_cash - sum(buys.total_value)
                                 + sum(sells.total_value)
                                 + sum(dividends.total_value)

This formula is bulletproof — even if the holdings table or current_cash
get corrupted, recomputing from the transaction log restores truth as long
as the transactions themselves are correct (which they are, because they
come from Alpaca's filled order via wait_for_fill).
"""
import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("bigclaw.trade_recorder")

DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def record_trade(pid, pname, ticker, action, shares, price, total_value,
                 rationale, order_id=None, sell_all=False, max_retries=10,
                 target_price=None, target_source=None):
    """Record one trade to the DB (transactions log + holdings + recomputed cash).

    Args:
        pid: portfolio_id
        pname: portfolio_name (for logging)
        ticker: stock ticker (BigClaw internal format, e.g., "BRK-B" not "BRK.B")
        action: "buy" or "sell"
        shares: filled_qty from wait_for_fill (Alpaca's truth)
        price: filled_avg_price from wait_for_fill (Alpaca's truth)
        total_value: shares * price (caller computes; we don't recompute to allow
                     for slight rounding differences from Alpaca's own arithmetic)
        rationale: human-readable reason for the trade
        order_id: Alpaca order_id string (optional but strongly recommended)
        sell_all: DEPRECATED. Ignored as of May 21 2026 — record_trade always
                  decrements shares and auto-deletes when remaining <= 0.001.
                  The old (filled_qty >= requested_qty) pattern was wrong for
                  partial trims; computing remaining from DB is the only
                  reliable source of truth.

    Returns:
        True on success, False if all retries exhausted.
    """
    if shares <= 0:
        logger.warning(f"record_trade: skipping {action} {ticker} for {pname} "
                       f"with zero shares (no transaction recorded)")
        return True

    for attempt in range(max_retries):
        try:
            conn = _conn()
            c = conn.cursor()

            # 1. Insert transaction row (source of truth)
            c.execute(
                "INSERT INTO transactions "
                "(portfolio_id, ticker, action, shares, price, total_value, rationale, order_id) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (pid, ticker, action, shares, price, total_value, rationale, order_id),
            )

            # 2. Update holdings to match
            if action == "buy":
                c.execute(
                    "SELECT shares, avg_cost FROM holdings "
                    "WHERE portfolio_id = ? AND ticker = ?",
                    (pid, ticker),
                )
                existing = c.fetchone()
                if existing is not None:
                    old_shares = existing[0] or 0
                    old_avg = existing[1] or price
                    if old_shares > 0:
                        new_shares = old_shares + shares
                        new_avg = ((old_shares * old_avg) + (shares * price)) / new_shares
                    else:
                        new_shares = shares
                        new_avg = price
                    c.execute(
                        "UPDATE holdings SET shares = ?, avg_cost = ?, "
                        "last_bought_at = CURRENT_TIMESTAMP "
                        "WHERE portfolio_id = ? AND ticker = ?",
                        (new_shares, round(new_avg, 4), pid, ticker),
                    )
                else:
                    # First buy of this position — capture target_price.
                    # Targets set here persist for life of position (not updated on adds).
                    c.execute(
                        "INSERT INTO holdings "
                        "(portfolio_id, ticker, shares, avg_cost, rationale, "
                        " target_price, target_set_at, target_source) "
                        "VALUES (?,?,?,?,?,?,"
                        " CASE WHEN ? IS NOT NULL THEN CURRENT_TIMESTAMP ELSE NULL END,"
                        " ?)",
                        (pid, ticker, shares, price, rationale,
                         target_price, target_price, target_source),
                    )
            elif action == "sell":
                # Always decrement-and-cleanup. The sell_all parameter is
                # intentionally ignored: callers historically computed it as
                # (filled_qty >= requested_sell_qty), which is True for
                # partial trims and caused full holdings rows to be deleted
                # (SHOP incident May 21 2026). Computing remaining shares
                # from the DB itself is the only safe source of truth.
                c.execute(
                    "UPDATE holdings SET shares = shares - ? "
                    "WHERE portfolio_id = ? AND ticker = ?",
                    (shares, pid, ticker),
                )
                c.execute(
                    "DELETE FROM holdings WHERE portfolio_id = ? AND ticker = ? "
                    "AND shares <= 0.001",
                    (pid, ticker),
                )
                # Clean up trailing stop if position fully closed
                c.execute(
                    "DELETE FROM trailing_stops "
                    "WHERE portfolio_id = ? AND ticker = ? "
                    "AND NOT EXISTS ("
                    "  SELECT 1 FROM holdings "
                    "  WHERE portfolio_id = ? AND ticker = ? AND shares > 0.001"
                    ")",
                    (pid, ticker, pid, ticker),
                )

            # 3. Recompute cash from the entire transaction log (RULE 4)
            c.execute(
                "SELECT COALESCE(SUM(CASE WHEN action='buy' THEN total_value END), 0), "
                "       COALESCE(SUM(CASE WHEN action='sell' THEN total_value END), 0), "
                "       COALESCE(SUM(CASE WHEN action='dividend' THEN total_value END), 0) "
                "FROM transactions WHERE portfolio_id = ?",
                (pid,),
            )
            buys, sells, dividends = c.fetchone()
            c.execute("SELECT starting_cash FROM portfolios WHERE id = ?", (pid,))
            starting = c.fetchone()[0]
            correct_cash = starting - buys + sells + dividends
            c.execute(
                "UPDATE portfolios SET current_cash = ? WHERE id = ?",
                (round(correct_cash, 2), pid),
            )

            conn.commit()
            conn.close()
            logger.info(
                f"DB recorded: {action.upper()} {shares} {ticker} for {pname} "
                f"(attempt {attempt + 1}, order_id={order_id})"
            )
            return True

        except Exception as e:
            err_str = str(e)
            retryable = "database is locked" in err_str or "UNIQUE constraint" in err_str
            if retryable and attempt < max_retries - 1:
                wait = 3 * (attempt + 1)
                logger.warning(
                    f"DB error recording {action} {ticker} for {pname}: {err_str}. "
                    f"Retry {attempt + 1}/{max_retries} in {wait}s..."
                )
                time.sleep(wait)
                continue
            logger.error(
                f"DB recording FAILED after {attempt + 1} attempts for "
                f"{action} {ticker} {pname}: {err_str}"
            )
            return False

    return False
