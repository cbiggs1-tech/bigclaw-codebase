"""Stop-sell cooldown gate.

When a trailing stop fires, the position is removed but the IPS scoring
engine often still flags the same ticker as "top 10" minutes later, leading
to a rebuy at near-identical price. The May 1 2026 AI Defense round-trip
(LMT/NOC/RTX sold and re-bought within 73 minutes for $4.8K of crystallized
loss) exposed this.

Rule: after a stop fires, that (portfolio, ticker) pair is blocked from
re-entry until BOTH conditions are met:
  1. At least 10 trading days have elapsed since the stop trigger.
  2. The current score is at least 2 points above the score at trigger.

If score never recovers, the position stays blocked indefinitely — which
is the right behavior for a genuinely deteriorated name.
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = os.path.expanduser("~/bigclaw-ai/src/portfolios.db")
SIGNALS_PATH = os.path.expanduser("~/bigclaw-ai/docs/data/signals.json")

COOLDOWN_DAYS = 10
SCORE_BUMP_REQUIRED = 2


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=30000")
    return c


def ensure_schema():
    """Idempotent table creation. Safe to call from any module load."""
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stop_cooldowns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            triggered_at TIMESTAMP NOT NULL,
            trigger_score REAL,
            note TEXT,
            UNIQUE(portfolio_id, ticker)
        )
    """)
    conn.commit()
    conn.close()


def _score_for(pname: str, ticker: str):
    """Look up the current score for a (portfolio_name, ticker) from
    signals.json. Returns float or None if not found."""
    try:
        with open(SIGNALS_PATH) as f:
            data = json.load(f)
        sig = data.get("portfolio_signals", {}).get(pname, {}).get(ticker)
        if sig and "score" in sig:
            return float(sig["score"])
    except Exception:
        pass
    return None


def record_stop_trigger(portfolio_id: int, portfolio_name: str, ticker: str, note: str = ""):
    """Called from trailing_stop_manager when a stop fires. Records the
    trigger time and the score-at-trigger from the latest signals.json."""
    ensure_schema()
    score = _score_for(portfolio_name, ticker)
    conn = _conn()
    conn.execute("""
        INSERT INTO stop_cooldowns (portfolio_id, ticker, triggered_at, trigger_score, note)
        VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
        ON CONFLICT(portfolio_id, ticker) DO UPDATE SET
            triggered_at = CURRENT_TIMESTAMP,
            trigger_score = excluded.trigger_score,
            note = excluded.note
    """, (portfolio_id, ticker, score, note))
    conn.commit()
    conn.close()


def is_blocked(portfolio_id: int, portfolio_name: str, ticker: str, current_score=None):
    """Return (blocked: bool, reason: str). If unblocked, the cooldown row
    (if any) is auto-cleared so the gate is single-firing."""
    ensure_schema()
    conn = _conn()
    row = conn.execute("""
        SELECT triggered_at, trigger_score
        FROM stop_cooldowns WHERE portfolio_id = ? AND ticker = ?
    """, (portfolio_id, ticker)).fetchone()
    if row is None:
        conn.close()
        return False, ""

    triggered_at_str, trigger_score = row
    try:
        triggered_at = datetime.strptime(triggered_at_str[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        triggered_at = datetime.now() - timedelta(days=COOLDOWN_DAYS + 1)
    days_since = (datetime.now() - triggered_at).days

    if current_score is None:
        current_score = _score_for(portfolio_name, ticker)

    time_ok = days_since >= COOLDOWN_DAYS
    score_ok = (
        trigger_score is None
        or current_score is None
        or current_score >= (trigger_score + SCORE_BUMP_REQUIRED)
    )
    # Special case: if trigger_score is known but current_score is unknown,
    # we can't validate the bump — keep blocked to be safe.
    if trigger_score is not None and current_score is None:
        score_ok = False

    if time_ok and score_ok:
        conn.execute("DELETE FROM stop_cooldowns WHERE portfolio_id = ? AND ticker = ?",
                     (portfolio_id, ticker))
        conn.commit()
        conn.close()
        return False, f"cooldown released: {days_since}d elapsed, score {current_score} >= trigger {trigger_score}+{SCORE_BUMP_REQUIRED}"

    conn.close()
    parts = []
    if not time_ok:
        parts.append(f"{days_since}/{COOLDOWN_DAYS}d elapsed")
    if not score_ok:
        ts = "?" if trigger_score is None else f"{trigger_score}"
        cs = "?" if current_score is None else f"{current_score}"
        parts.append(f"score {cs} < {ts}+{SCORE_BUMP_REQUIRED}")
    return True, "STOP-COOLDOWN | " + " | ".join(parts)


def list_active():
    """Return list of (portfolio_id, ticker, triggered_at, trigger_score, days_remaining)."""
    ensure_schema()
    conn = _conn()
    rows = conn.execute("""
        SELECT portfolio_id, ticker, triggered_at, trigger_score
        FROM stop_cooldowns ORDER BY triggered_at DESC
    """).fetchall()
    conn.close()
    out = []
    now = datetime.now()
    for pid, ticker, trig_str, score in rows:
        try:
            t = datetime.strptime(trig_str[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            t = now
        days_since = (now - t).days
        days_remaining = max(0, COOLDOWN_DAYS - days_since)
        out.append({
            "portfolio_id": pid, "ticker": ticker,
            "triggered_at": trig_str, "trigger_score": score,
            "days_remaining": days_remaining,
        })
    return out


if __name__ == "__main__":
    import sys
    ensure_schema()
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for c in list_active():
            print(c)
    else:
        print("stop_cooldown module — call ensure_schema(), record_stop_trigger(), is_blocked(), list_active()")
