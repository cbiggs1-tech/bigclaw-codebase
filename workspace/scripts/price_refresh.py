#!/usr/bin/env python3
"""Lightweight price refresh for BigClaw website.

Fetches current prices for all portfolio holdings via yfinance,
updates portfolios.json and market.json, commits and pushes to GitHub.
No AI analysis — just fresh numbers.
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timezone

import yfinance as yf

REPO_ROOT = os.path.expanduser("~/bigclaw-ai")
DOCS_DATA = os.path.join(REPO_ROOT, "docs", "data")
DB_PATH = os.path.join(REPO_ROOT, "src", "portfolios.db")

sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
from portfolio import list_portfolios, Portfolio


def fetch_prices(tickers):
    """Batch fetch current prices via yfinance."""
    if not tickers:
        return {}
    prices = {}
    try:
        data = yf.download(list(tickers), period="1d", progress=False, threads=True)
        if 'Close' in data.columns or len(tickers) == 1:
            close = data['Close'] if len(tickers) > 1 else data[['Close']]
            if hasattr(close, 'iloc'):
                row = close.iloc[-1]
                for t in tickers:
                    col = t if t in row.index else None
                    if col and not (row[col] != row[col]):  # not NaN
                        prices[t] = float(row[col])
    except Exception as e:
        print(f"Batch fetch failed: {e}, trying individual...")

    # Fallback for missing tickers
    for t in tickers:
        if t not in prices:
            try:
                info = yf.Ticker(t).fast_info
                p = getattr(info, 'last_price', None) or getattr(info, 'previous_close', None)
                if p:
                    prices[t] = float(p)
            except:
                pass
    return prices


def fetch_prev_closes(tickers):
    """Fetch previous closing prices for daily change calculation."""
    if not tickers:
        return {}
    prev = {}
    try:
        data = yf.download(list(tickers), period="5d", progress=False, threads=True)
        if 'Close' in data.columns or len(tickers) == 1:
            close = data['Close'] if len(tickers) > 1 else data[['Close']]
            if hasattr(close, 'iloc') and len(close) >= 2:
                row = close.iloc[-2]  # previous day's close
                for t in tickers:
                    col = t if t in row.index else None
                    if col and not (row[col] != row[col]):
                        prev[t] = float(row[col])
    except Exception as e:
        print(f"Previous close fetch failed: {e}")

    # Fallback
    for t in tickers:
        if t not in prev:
            try:
                info = yf.Ticker(t).fast_info
                pc = getattr(info, 'previous_close', None)
                if pc:
                    prev[t] = float(pc)
            except:
                pass
    return prev


def refresh_portfolios():
    """Refresh portfolios.json with current prices."""
    all_tickers = set()
    portfolio_data = []

    for p_info in list_portfolios():
        if not p_info.get('is_active'):
            continue
        portfolio = Portfolio(p_info['id'])
        holdings = portfolio.get_holdings()
        for h in holdings:
            all_tickers.add(h['ticker'])
        portfolio_data.append({
            'id': p_info['id'],
            'name': portfolio.name,
            'style': portfolio.investment_style,
            'starting_cash': portfolio.starting_cash,
            'current_cash': portfolio.current_cash,
            'created_at': portfolio.created_at,
            'purchase_status': p_info.get('purchase_status', 'active'),
            'holdings_raw': holdings,
        })

    prices = fetch_prices(all_tickers)
    prev_closes = fetch_prev_closes(all_tickers)
    print(f"Fetched prices for {len(prices)}/{len(all_tickers)} tickers")

    # Auto-detect pending→active: if cash < 10% of starting, portfolio is deployed
    auto_activated = []
    for p in portfolio_data:
        if p['purchase_status'] == 'pending' and len(p['holdings_raw']) > 0:
            cash_pct = (p['current_cash'] / p['starting_cash'] * 100) if p['starting_cash'] > 0 else 100
            if cash_pct < 10:
                import sqlite3
                conn = sqlite3.connect(DB_PATH)
                conn.execute("UPDATE portfolios SET purchase_status='active' WHERE id=?", (p['id'],))
                conn.commit()
                conn.close()
                p['purchase_status'] = 'active'
                auto_activated.append(f"{p['name']} ({cash_pct:.1f}% cash)")
    if auto_activated:
        print(f"Auto-activated: {', '.join(auto_activated)}")

    output = []
    for p in portfolio_data:
        holdings = []
        holdings_value = 0
        prev_holdings_value = 0
        for h in p['holdings_raw']:
            t = h['ticker']
            cp = prices.get(t, h['avg_cost'])
            pc = prev_closes.get(t, cp)
            val = h['shares'] * cp
            prev_val = h['shares'] * pc
            holdings_value += val
            prev_holdings_value += prev_val
            pa = h.get('first_bought_at', '')
            if pa:
                try:
                    dt = datetime.fromisoformat(pa.replace('Z', '+00:00'))
                    pa = dt.strftime('%b %d, %Y')
                except:
                    pa = pa[:10] if len(pa) >= 10 else pa
            holdings.append({
                'ticker': t,
                'shares': round(h['shares'], 2),
                'avgCost': round(h['avg_cost'], 2),
                'currentPrice': round(cp, 2),
                'purchasedAt': pa,
            })
        total_value = p['current_cash'] + holdings_value
        prev_total_value = p['current_cash'] + prev_holdings_value
        total_return = ((total_value - p['starting_cash']) / p['starting_cash']) * 100
        daily_return = ((total_value - prev_total_value) / prev_total_value * 100) if prev_total_value > 0 else 0
        output.append({
            'name': p['name'],
            'style': p['style'],
            'totalValue': round(total_value, 2),
            'prevTotalValue': round(prev_total_value, 2),
            'startingCash': round(p['starting_cash'], 2),
            'totalReturn': round(total_return, 2),
            'dailyReturn': round(daily_return, 2),
            'createdAt': p['created_at'],
            'purchaseStatus': p.get('purchase_status', 'active'),
            'holdings': holdings,
        })

    result = {
        'lastUpdate': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'portfolios': output,
    }
    with open(os.path.join(DOCS_DATA, 'portfolios.json'), 'w') as f:
        json.dump(result, f, indent=2)
    return prices


def refresh_market(prices):
    """Refresh market.json with index data."""
    indices = {'^GSPC': 'S&P 500', '^DJI': 'Dow Jones', '^IXIC': 'NASDAQ', '^VIX': 'VIX'}
    idx_prices = fetch_prices(set(indices.keys()))

    market = {'lastUpdate': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), 'indices': []}
    for sym, name in indices.items():
        p = idx_prices.get(sym)
        if p:
            # Get previous close for change calc
            try:
                info = yf.Ticker(sym).fast_info
                prev = getattr(info, 'previous_close', p)
                chg = ((p - prev) / prev) * 100 if prev else 0
            except:
                chg = 0
            market['indices'].append({
                'name': name, 'value': round(p, 2), 'change': round(chg, 2),
            })

    with open(os.path.join(DOCS_DATA, 'market.json'), 'w') as f:
        json.dump(market, f, indent=2)


def refresh_signals(prices):
    """Inject fresh prices into signals.json so watchlist shows current data."""
    signals_path = os.path.join(DOCS_DATA, 'signals.json')
    if not os.path.exists(signals_path):
        print("signals.json not found, skipping")
        return

    with open(signals_path, 'r') as f:
        data = json.load(f)

    signals = data.get('signals', [])
    if not signals:
        return

    # Collect any signal tickers not already fetched (watchlist candidates)
    all_sig_tickers = {s['ticker'] for s in signals}
    missing = all_sig_tickers - set(prices.keys())
    if missing:
        extra = fetch_prices(missing)
        prices = {**prices, **extra}

    updated = 0
    for s in signals:
        t = s['ticker']
        if t in prices:
            s['price'] = round(prices[t], 2)
            updated += 1

    data['signals'] = signals
    # Add a priceRefreshedAt timestamp so we can track freshness
    data['priceRefreshedAt'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    with open(signals_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"Updated prices for {updated}/{len(signals)} signals in signals.json")


def git_push():
    """Commit and push data changes."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    os.chdir(REPO_ROOT)
    subprocess.run(['git', 'add',
                    'docs/data/portfolios.json',
                    'docs/data/market.json',
                    'docs/data/signals.json'], check=True)
    result = subprocess.run(['git', 'diff', '--cached', '--quiet'])
    if result.returncode == 0:
        print("No changes to push")
        return
    subprocess.run(['git', 'commit', '-m', f'Price refresh {now}'], check=True)
    subprocess.run(['git', 'push'], check=True)
    print(f"Pushed price update at {now}")


if __name__ == '__main__':
    prices = refresh_portfolios()
    refresh_market(prices)
    refresh_signals(prices)
    git_push()
