#!/usr/bin/env python3
"""IV skew/spread signal for the Morning Market Brief.

This is the forward options read that REPLACED Unusual Whales (UW cancelled
2026-05-31; IV skew + call-put spread was the one options signal with a
documented forward-equity-return edge for our horizon -- BULLISH-IV names ran
~+1% excess vs SPY, BEARISH ~-2% in the diagnostic). Reads iv_history (populated
daily by iv_tracker.py). Prints a plain-text section for the morning data file.
"""
import sqlite3
from pathlib import Path

DB = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"


def main():
    c = sqlite3.connect(DB)
    mx = c.execute("SELECT max(snapshot_date) FROM iv_history").fetchone()[0]
    if not mx:
        print("IV data unavailable (iv_history empty)")
        return
    held = {r[0] for r in c.execute("SELECT DISTINCT ticker FROM holdings WHERE shares>0")}
    rows = c.execute(
        "SELECT ticker, classification, round(skew,3), round(spread,3) "
        "FROM iv_history WHERE snapshot_date=? AND target_days=30", (mx,)
    ).fetchall()
    if not rows:
        print(f"IV data unavailable for {mx}")
        return

    by = {}
    for t, cls, sk, sp in rows:
        by.setdefault(cls, []).append((t, sp))

    print(f"As of {mx} | {len(rows)} names | forward options read (30d skew/spread). "
          "BULLISH-IV names historically outperform; BEARISH underperform.")
    print(f"  Tally: BULLISH {len(by.get('BULLISH', []))}  "
          f"MIXED {len(by.get('MIXED', []))}  BEARISH {len(by.get('BEARISH', []))}")

    held_rows = [(t, cls) for t, cls, sk, sp in rows if t in held]
    if held_rows:
        order = {"BULLISH": 0, "MIXED": 1, "BEARISH": 2}
        print("  HOLDINGS forward IV read:")
        for t, cls in sorted(held_rows, key=lambda x: order.get(x[1], 9)):
            print(f"    {t:6s} {cls}")

    bull = ", ".join(t for t, sp in sorted(by.get("BULLISH", []), key=lambda x: -x[1])[:6])
    bear = ", ".join(t for t, sp in sorted(by.get("BEARISH", []), key=lambda x: x[1])[:6])
    print(f"  Strongest BULLISH-IV (non-held watch): {bull or 'none'}")
    print(f"  Strongest BEARISH-IV (avoid/caution):  {bear or 'none'}")


if __name__ == "__main__":
    main()
