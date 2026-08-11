"""Generate portfolio performance chart from daily_snapshots, rebased to the
April 16 2026 refactor baseline, with an S&P 500 (SPY) overlay for comparison."""

import os
import sqlite3
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import yfinance as yf

REPO_ROOT = os.path.expanduser("~/bigclaw-ai")
DB_PATH = os.path.join(REPO_ROOT, 'src', 'portfolios.db')
CHART_PATH = os.path.join(REPO_ROOT, 'docs', 'data', 'performance_chart.png')

# Refactor baseline: portfolios were reset / IPS rules went live week of April 16
BASELINE_DATE = '2026-04-16'


def fetch_spy_returns(start_date: str, end_date: str):
    """Pull SPY closes from yfinance and rebase to 0% at start_date.

    Returns (dates_list, return_pct_list). On failure returns ([], []) so the
    chart still renders without the benchmark line.
    """
    try:
        # yfinance end is exclusive; pad a day to ensure we get end_date close
        from datetime import timedelta as _td
        end_inclusive = (datetime.strptime(end_date, '%Y-%m-%d') + _td(days=1)).strftime('%Y-%m-%d')
        df = yf.download('SPY', start=start_date, end=end_inclusive,
                         progress=False, auto_adjust=True)
        if df.empty:
            return [], []
        closes = df['Close'].squeeze()  # collapse single-ticker MultiIndex if present
        baseline = float(closes.iloc[0])
        dates = [d.to_pydatetime() for d in closes.index]
        returns = [((float(c) - baseline) / baseline) * 100 for c in closes.values]
        return dates, returns
    except Exception as e:
        print(f"SPY fetch failed: {e}")
        return [], []


def main():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    c = conn.cursor()

    c.execute("SELECT id, name FROM portfolios WHERE is_active = 1 ORDER BY id")
    portfolios = {row[0]: {"name": row[1]} for row in c.fetchall()}

    c.execute("""
        SELECT portfolio_id, snapshot_date, total_value
        FROM daily_snapshots
        WHERE snapshot_date >= ?
        ORDER BY snapshot_date
    """, (BASELINE_DATE,))
    rows = c.fetchall()
    conn.close()

    # Per-portfolio: take the earliest snapshot on/after BASELINE_DATE as the
    # baseline value, then compute % return relative to that.
    by_pid = {pid: [] for pid in portfolios}
    for pid, date_str, total_value in rows:
        if pid not in portfolios or not total_value:
            continue
        by_pid[pid].append((datetime.strptime(date_str[:10], "%Y-%m-%d"), float(total_value)))

    data = {}
    for pid, series in by_pid.items():
        if not series:
            data[pid] = {"dates": [], "returns": []}
            continue
        baseline = series[0][1]
        data[pid] = {
            "dates": [d for d, _ in series],
            "returns": [((v - baseline) / baseline) * 100 for _, v in series],
        }

    has_data = any(len(d["dates"]) > 0 for d in data.values())
    if not has_data:
        print("No snapshot data to chart")
        return False

    for pid in portfolios:
        if data[pid]['returns']:
            print(f"  {portfolios[pid]['name']}: {len(data[pid]['dates'])} pts, "
                  f"latest: {data[pid]['returns'][-1]:+.2f}%")

    # SPY benchmark: align to portfolio date range
    all_dates = [d for s in data.values() for d in s["dates"]]
    spy_start = BASELINE_DATE
    spy_end = max(all_dates).strftime('%Y-%m-%d')
    spy_dates, spy_returns = fetch_spy_returns(spy_start, spy_end)
    if spy_returns:
        print(f"  S&P 500 (SPY): {len(spy_dates)} pts, latest: {spy_returns[-1]:+.2f}%")

    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')

    # Colors for live sleeves (is_active=1 only; killed books not plotted)
    colors = {
        'Innovation Fund': '#f87171',
        'Momentum Growth': '#fb923c',
        'AI Defense & Autonomous': '#22d3ee',
        'LLM-Commando': '#a78bfa',
        'Monkey Dart': '#f472b6',  # pink — QQQ random tide sleeve
        'LLM-Inverse-Commando': '#94a3b8',
        # retired (kept for color stability if re-activated):
        'Value Picks': '#4ade80',
        'Growth Value': '#60a5fa',
        'Nuclear Renaissance': '#facc15',
        'Income Dividends': '#c084fc',
        'LLM-ETF Focus': '#94a3b8',
    }

    for pid, portfolio in portfolios.items():
        d = data[pid]
        if not d["dates"]:
            continue
        name = portfolio["name"]
        color = colors.get(name, '#ffffff')
        last_ret = d["returns"][-1]
        ax.plot(d["dates"], d["returns"],
                label=f"{name} ({last_ret:+.1f}%)",
                linewidth=2.5, color=color, marker='o', markersize=5)

    if spy_returns:
        ax.plot(spy_dates, spy_returns,
                label=f"S&P 500 ({spy_returns[-1]:+.1f}%)",
                linewidth=2.5, color='#ffffff', linestyle='--',
                marker='s', markersize=4, alpha=0.85)

    ax.set_xlabel('Date', fontsize=11, color='#e5e5e5')
    ax.set_ylabel('Return since Apr 16 (%)', fontsize=11, color='#e5e5e5')

    if all_dates:
        start = min(all_dates).strftime('%b %d')
        end = max(all_dates).strftime('%b %d, %Y')
        ax.set_title(f'Portfolio Performance vs S&P 500 ({start} - {end}) · Monkey Dart live',
                     fontsize=14, fontweight='bold', color='white', pad=15)

    ax.axhline(y=0, color='#4a4a6a', linestyle='--', linewidth=1, alpha=0.7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    plt.xticks(rotation=45, ha='right')
    ax.grid(True, alpha=0.2, color='#4a4a6a')
    ax.legend(loc='best', framealpha=0.9, facecolor='#1a1a2e',
              edgecolor='#4a4a6a', ncol=2, fontsize=9)

    for spine in ax.spines.values():
        spine.set_color('#4a4a6a')
    ax.tick_params(colors='#e5e5e5')

    plt.tight_layout()
    plt.savefig(CHART_PATH, dpi=150, facecolor='#1a1a2e', edgecolor='none')
    plt.close()

    size = os.path.getsize(CHART_PATH)
    print(f"Chart saved to {CHART_PATH} ({size/1024:.0f} KB)")
    return True


if __name__ == '__main__':
    main()
