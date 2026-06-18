#!/usr/bin/env python3
"""Decision-engine intent for the Morning Market Brief.

Replaces the retired Unusual Whales sections (GEX / market tide / smart money /
insider, cancelled 2026-05-31) with a feed we actually use: what the rule-based
decision engine plans to do today, its top-scored candidates, and what it has
already executed this week. Reads docs/data/signals.json (refreshed daily by the
engine). Prints a plain-text section for the morning data file.
"""
import json
from pathlib import Path

SIG = Path.home() / "bigclaw-ai" / "docs" / "data" / "signals.json"


def main():
    try:
        d = json.load(open(SIG))
    except Exception as e:
        print(f"signals.json unavailable: {e}")
        return

    planned = d.get("planned_actions") or []
    executed = d.get("executed_this_week") or []
    sigs = sorted(
        [s for s in d.get("signals", []) if s.get("score") is not None],
        key=lambda s: -s["score"],
    )

    print(f"As of: {d.get('date', 'unknown')}  ({len(sigs)} candidates scored)")

    print("\nPLANNED ACTIONS (what the engine intends at the next run):")
    if planned:
        for a in planned[:12]:
            print(f"  {a.get('action','?'):4s} {a.get('ticker','?'):6s} x{a.get('shares','?')} "
                  f"[{a.get('portfolio','?')}] score {a.get('score')} - {(a.get('reason') or '')[:55]}")
        if len(planned) > 12:
            print(f"  ... and {len(planned) - 12} more")
    else:
        print("  (none planned)")

    print("\nTOP-SCORED CANDIDATES (engine conviction):")
    for s in sigs[:10]:
        print(f"  {s.get('ticker','?'):6s} score {s.get('score'):>3}   ${s.get('price','?')}")

    print("\nEXECUTED THIS WEEK:")
    if executed:
        for t in executed[-10:]:
            print(f"  {t.get('action','?'):4s} {t.get('ticker','?'):6s} x{t.get('shares','?')} "
                  f"[{t.get('portfolio','?')}] - {(t.get('reason') or '')[:50]}")
    else:
        print("  (none)")


if __name__ == "__main__":
    main()
