#!/usr/bin/env python3
"""EOD: snapshots + performance chart + versioned publish for CDN cache-bust."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path.home() / "bigclaw-ai"
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))
os.chdir(REPO)

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
    tickers = {h["ticker"] for p in ports for h in p.get_holdings()}
    prices = get_current_prices(list(tickers)) if tickers else {}
    save_snapshots(prices)
    gen_chart()

    chart = REPO / "docs" / "data" / "performance_chart.png"
    h = hashlib.sha256(chart.read_bytes()).hexdigest()[:10]
    ver = f"performance_chart_{h}.png"
    shutil.copy2(chart, REPO / "docs" / "data" / ver)
    meta = {
        "file": ver,
        "sha": h,
        "updated": datetime.now(timezone.utc).isoformat(),
        "includes": ["Monkey Dart"],
    }
    (REPO / "docs" / "data" / "chart_version.json").write_text(
        json.dumps(meta, indent=2) + "\n"
    )

    files = [
        "docs/data/performance_chart.png",
        f"docs/data/{ver}",
        "docs/data/chart_version.json",
    ]
    push = REPO / "scripts" / "push_docs.sh"
    if push.exists():
        subprocess.call(
            ["bash", str(push), "EOD performance chart (+Monkey Dart)"] + files,
            cwd=str(REPO),
        )
    print("eod_snapshot_chart: OK", ver)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
