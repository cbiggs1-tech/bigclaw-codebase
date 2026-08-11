#!/usr/bin/env python3
"""Post-flatten website/export straighten for 4-sleeve BigClaw.

Run AFTER kill books are flat + is_active=0.
- Refreshes portfolios.json via price_refresh (is_active filter)
- Stales out LLM-ETF panel JSON with a retired notice
- Sanity-checks only KEEP names appear in portfolios.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
DOCS = HOME / "bigclaw-ai" / "docs"
DATA = DOCS / "data"
KEEP = {
    "Innovation Fund",
    "Momentum Growth",
    "AI Defense & Autonomous",
    "LLM-Commando",
    "Monkey Dart",
}
KILL = {
    "Value Picks",
    "Growth Value",
    "Income Dividends",
    "Nuclear Renaissance",
    "LLM-ETF Focus",
}


def main():
    # 1) price refresh / export
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    # source secrets into env for child
    for line in (HOME / ".env_secrets").read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

    print("Running price_refresh.py ...")
    r = subprocess.run(
        [sys.executable, str(HOME / "bigclaw-ai/scripts/price_refresh.py")],
        cwd=str(HOME / "bigclaw-ai"),
        env=env,
        capture_output=True,
        text=True,
    )
    print(r.stdout[-2000:] if r.stdout else "")
    if r.returncode != 0:
        print("price_refresh stderr:", (r.stderr or "")[-1500:])
        print("WARN: price_refresh rc", r.returncode)

    # 2) verify portfolios.json
    pf_path = DATA / "portfolios.json"
    data = json.loads(pf_path.read_text())
    names = [p.get("name") for p in data.get("portfolios") or []]
    print("portfolios.json names:", names)
    bad = [n for n in names if n in KILL]
    missing = [n for n in KEEP if n not in names]
    if bad:
        print("ERROR still showing kill books:", bad)
    if missing:
        print("WARN missing keep books:", missing)
    if not bad and not missing:
        print("OK: portfolios.json is 4-sleeve clean")

    # 3) retire ETF Focus panel file (dashboard may still fetch it)
    etf = DATA / "llm_portfolio.json"
    retired = {
        "status": "retired",
        "name": "LLM-ETF Focus",
        "retired_at": datetime.now(timezone.utc).isoformat(),
        "note": "Deactivated in 4-sleeve cutover 2026-07-22. Active LLM book is LLM-Commando only.",
        "portfolio": None,
        "holdings": [],
        "cash": 0,
    }
    if etf.exists():
        bak = DATA / f"llm_portfolio.json.bak-pre-retire-{datetime.now().strftime('%Y%m%d')}"
        if not bak.exists():
            bak.write_text(etf.read_text())
        etf.write_text(json.dumps(retired, indent=2) + "\n")
        print("Wrote retired llm_portfolio.json (ETF Focus panel)")

    # 4) optional git push of docs data — leave to push_docs / user
    print("Done. If site is GitHub Pages, run push_docs or commit docs/data.")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
