#!/usr/bin/env python3
"""
BigClaw 4-sleeve cutover (market-closed safe steps).

KEEP: Innovation Fund, Momentum Growth, AI Defense & Autonomous, LLM-Commando
KILL (flatten at next open): Value Picks, Growth Value, Income Dividends,
     Nuclear Renaissance, LLM-ETF Focus

This script:
  1) Cleans/shrinks portfolio_universes.json (KEEP rule books only)
  2) Does NOT liquidate (market closed) — writes pending flatten list
  3) Does NOT set is_active=0 until flat (see flatten_kill_portfolios.py)

Usage:
  python3 four_sleeve_cutover_tonight.py
  python3 four_sleeve_cutover_tonight.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
UNIVERSES = HOME / ".openclaw/workspace/config/portfolio_universes.json"
# repo mirror (symlink target for scripts; config lives under openclaw)
REPO_UNIVERSES = HOME / "bigclaw-ai/config/portfolio_universes.json"
PENDING = HOME / "bigclaw-ai/data/pending_four_sleeve_flatten.json"
BACKUP_DIR = HOME / "bigclaw-ai/data/cutover_backups"

KEEP_RULE = {
    "Innovation Fund",
    "Momentum Growth",
    "AI Defense & Autonomous",
}
KILL = {
    "Value Picks",
    "Growth Value",
    "Income Dividends",
    "Nuclear Renaissance",
    "LLM-ETF Focus",
}

# Innovation thematic seed (plus live holdings) — keep universe small
INNOVATION_SEED = [
    "NVDA", "AMD", "AVGO", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU",
    "PLTR", "SNOW", "CRWD", "NET", "DDOG", "SHOP", "SQ", "COIN", "HOOD",
    "TSLA", "RIVN", "PATH", "AI", "SOUN", "IONQ", "RGTI",
    "ISRG", "VRTX", "REGN", "MRNA", "CRSP", "NTLA",
    "ARKK",  # will be held as candidate only if not ETF-blocked elsewhere; OK in universe file
]

MAX_CAND = {
    "Innovation Fund": 40,
    "Momentum Growth": 80,
    "AI Defense & Autonomous": 25,
}


def clean_ticker(t: str) -> str | None:
    if not t or not isinstance(t, str):
        return None
    t = t.strip().upper()
    if not t.isalpha() or not (1 <= len(t) <= 5):
        return None
    # Corruption pattern: doubled first letter on 5-char codes (AAAPL -> AAPL)
    if len(t) >= 5 and t[0] == t[1]:
        t2 = t[1:]
        if t2.isalpha() and 1 <= len(t2) <= 5:
            t = t2
    return t


def clean_list(tickers, extra=None):
    out = []
    seen = set()
    for t in list(tickers or []) + list(extra or []):
        c = clean_ticker(t)
        if not c or c in seen:
            continue
        # Drop pure sector ETFs from innovation seed noise
        if c in {"ARKK", "ARKW", "ARKQ", "SPY", "QQQ"}:
            continue
        seen.add(c)
        out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw = UNIVERSES.read_text()
    bak = BACKUP_DIR / f"portfolio_universes.{ts}.json"
    if not args.dry_run:
        bak.write_text(raw)
        print(f"Backed up universes -> {bak}")

    u = json.loads(raw)
    new_u = {}

    for name in KEEP_RULE:
        blob = u.get(name, {"holdings": [], "candidates": []})
        holdings = clean_list(blob.get("holdings") or [])
        cands = clean_list(blob.get("candidates") or [])
        if name == "Innovation Fund":
            cands = clean_list(holdings, INNOVATION_SEED + cands)
        else:
            # holdings first, then prior candidates cleaned
            cands = clean_list(holdings, cands)
        # candidates should not duplicate the need for holdings list structure
        # but DE expects both; keep holdings as held list, candidates = union minus none
        cap = MAX_CAND[name]
        # Prefer holdings, then seeds/prior
        ordered = []
        seen = set()
        for t in holdings + cands:
            if t not in seen:
                seen.add(t)
                ordered.append(t)
        candidates = [t for t in ordered if t not in set(holdings)][: max(0, cap - len(holdings))]
        # Actually store candidates as full eligible set including holdings for rescreen
        full = clean_list(holdings, candidates)
        full = full[:cap]
        new_u[name] = {
            "holdings": holdings,
            "candidates": full,
        }
        print(f"{name}: holdings={len(holdings)} candidates={len(full)} (was H={len(blob.get('holdings') or [])} C={len(blob.get('candidates') or [])})")

    # Drop kill rule books from universe file (rescreen won't see them)
    for name in sorted(u.keys()):
        if name not in KEEP_RULE:
            print(f"DROP universe key: {name} (was C={len((u[name] or {}).get('candidates') or [])})")

    total = set()
    for blob in new_u.values():
        total |= set(blob["candidates"]) | set(blob["holdings"])
    print(f"UNIQUE rule-book tickers after cut: {len(total)}")

    pending = {
        "created": ts,
        "kill_portfolios": sorted(KILL),
        "keep_rule": sorted(KEEP_RULE),
        "keep_llm": ["LLM-Commando"],
        "note": "Run flatten_kill_portfolios.py at next market open, then deactivate.",
    }

    if args.dry_run:
        print("DRY RUN — not writing")
        print(json.dumps({k: {"H": v["holdings"], "C_n": len(v["candidates"])} for k, v in new_u.items()}, indent=2))
        return

    UNIVERSES.write_text(json.dumps(new_u, indent=2) + "\n")
    print(f"Wrote {UNIVERSES}")
    # mirror if separate path exists and is a real file
    if REPO_UNIVERSES.parent.exists():
        try:
            if REPO_UNIVERSES.resolve() != UNIVERSES.resolve():
                REPO_UNIVERSES.write_text(json.dumps(new_u, indent=2) + "\n")
                print(f"Wrote {REPO_UNIVERSES}")
        except Exception as e:
            print(f"skip repo mirror: {e}")

    PENDING.parent.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(pending, indent=2) + "\n")
    print(f"Wrote {PENDING}")
    print("DONE config cutover. Flatten kills at next open.")


if __name__ == "__main__":
    main()
