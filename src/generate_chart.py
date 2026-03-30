"""Generate portfolio performance chart from daily_snapshots table."""

import os
import sqlite3
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

REPO_ROOT = os.path.expanduser("~/bigclaw-ai")
DB_PATH = os.path.join(REPO_ROOT, 'src', 'portfolios.db')
CHART_PATH = os.path.join(REPO_ROOT, 'docs', 'data', 'performance_chart.png')


def main():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    c = conn.cursor()

    # Get portfolio names
    c.execute("SELECT id, name, starting_cash FROM portfolios WHERE is_active = 1 ORDER BY id")
    portfolios = {row[0]: {"name": row[1], "starting": row[2]} for row in c.fetchall()}

    # Get all snapshots
    c.execute("""
        SELECT portfolio_id, snapshot_date, total_value
        FROM daily_snapshots
        ORDER BY snapshot_date
    """)
    snapshots = c.fetchall()
    conn.close()

    # Organize by portfolio
    data = {pid: {"dates": [], "returns": []} for pid in portfolios}
    for pid, date_str, total_value in snapshots:
        if pid not in portfolios or not total_value:
            continue
        starting = portfolios[pid]["starting"]
        ret_pct = ((total_value - starting) / starting) * 100
        data[pid]["dates"].append(datetime.strptime(date_str[:10], "%Y-%m-%d"))
        data[pid]["returns"].append(ret_pct)

    # Check we have data
    has_data = any(len(d["dates"]) > 0 for d in data.values())
    if not has_data:
        print("No snapshot data to chart")
        return False

    for pid in portfolios:
        print(f"  {portfolios[pid]['name']}: {len(data[pid]['dates'])} data points, "
              f"latest return: {data[pid]['returns'][-1]:+.2f}%" if data[pid]['returns'] else "no data")

    # Generate chart
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')

    colors = {
        'Value Picks': '#4ade80',
        'Innovation Fund': '#f87171',
        'Growth Value': '#60a5fa',
        'Nuclear Renaissance': '#facc15',
        'Income Dividends': '#c084fc',
        'Momentum Growth': '#fb923c',
        'AI Defense & Autonomous': '#22d3ee',
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

    ax.set_xlabel('Date', fontsize=11, color='#e5e5e5')
    ax.set_ylabel('Return (%)', fontsize=11, color='#e5e5e5')

    # Dynamic date range in title
    all_dates = []
    for d in data.values():
        all_dates.extend(d["dates"])
    if all_dates:
        start = min(all_dates).strftime('%b %d')
        end = max(all_dates).strftime('%b %d, %Y')
        ax.set_title(f'Portfolio Performance ({start} - {end})',
                     fontsize=14, fontweight='bold', color='white', pad=15)

    ax.axhline(y=0, color='#4a4a6a', linestyle='--', linewidth=1, alpha=0.7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    plt.xticks(rotation=45, ha='right')
    ax.grid(True, alpha=0.2, color='#4a4a6a')
    ax.legend(loc='best', framealpha=0.9, facecolor='#1a1a2e', edgecolor='#4a4a6a')

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
