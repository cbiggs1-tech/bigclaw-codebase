#!/usr/bin/env python3
"""EOD: daily_snapshots for active books + regenerate performance chart + push."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path.home() / "bigclaw-ai"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))
os.chdir(REPO)

# Load secrets if present
env_file = Path.home() / ".env_secrets"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    from portfolio_report import save_snapshots, get_current_prices
    from portfolio import get_active_portfolios
    from generate_chart import main as gen_chart

    ports = get_active_portfolios()
    tickers = set()
    for p in ports:
        for h in p.get_holdings():
            tickers.add(h["ticker"])
    prices = get_current_prices(list(tickers)) if tickers else {}
    save_snapshots(prices)
    gen_chart()
    chart = "docs/data/performance_chart.png"
    push = REPO / "scripts" / "push_docs.sh"
    if push.exists():
        subprocess.call(
            ["bash", str(push), "EOD performance chart", chart],
            cwd=str(REPO),
        )
    print("eod_snapshot_chart: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
