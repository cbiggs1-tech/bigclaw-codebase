#!/usr/bin/env python3
"""Generate portfolio reports and export to website.

Usage:
  python3 portfolio_report.py [--report] [--export] [--snapshot]
  
  --report    Print portfolio summary (for agent consumption)
  --export    Export dashboard JSON + git push to GitHub Pages
  --snapshot  Save daily snapshots for performance tracking
"""

import sys
import os
import json
import logging

# Add bigclaw src to path
sys.path.insert(0, os.path.expanduser("~/bigclaw-ai/src"))

from portfolio import get_active_portfolios, list_portfolios
from alpaca_data import get_extended_hours_prices, get_market_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_current_prices(tickers):
    """Get current prices via Alpaca, fallback to yfinance."""
    prices = {}
    
    # Try Alpaca first
    try:
        alpaca = get_extended_hours_prices(tickers)
        for t, data in alpaca.items():
            if data.get('price'):
                prices[t] = data['price']
    except Exception as e:
        logger.warning(f"Alpaca failed: {e}")
    
    # Fallback for missing tickers
    missing = [t for t in tickers if t not in prices]
    if missing:
        try:
            import yfinance as yf
            data = yf.download(missing, period="1d", progress=False)
            if len(missing) == 1:
                prices[missing[0]] = float(data["Close"].iloc[-1])
            else:
                for t in missing:
                    try:
                        prices[t] = float(data["Close"][t].iloc[-1])
                    except:
                        pass
        except Exception as e:
            logger.warning(f"yfinance fallback failed: {e}")
    
    return prices


def generate_report():
    """Generate a text report of all portfolios."""
    from datetime import datetime
    
    portfolios = get_active_portfolios()
    if not portfolios:
        print("No active portfolios.")
        return
    
    # Collect all tickers
    all_tickers = set()
    for p in portfolios:
        for h in p.get_holdings():
            all_tickers.add(h['ticker'])
    
    prices = get_current_prices(list(all_tickers))
    
    market = get_market_status()
    print(f"Market: {'OPEN' if market.get('is_open') else 'CLOSED'}")
    print(f"Report time: {datetime.now().strftime('%Y-%m-%d %H:%M CST')}")
    print("=" * 60)
    
    for p in portfolios:
        val = p.calculate_total_value(prices)
        emoji = "📈" if val['total_return'] >= 0 else "📉"
        
        print(f"\n**{p.name}** ({p.investment_style})")
        print(f"Total: ${val['total_value']:,.2f} | Cash: ${val['cash']:,.2f}")
        print(f"{emoji} Return: {val['total_return_pct']:+.2f}% (${val['total_return']:+,.2f})")
        
        for pos in sorted(val['positions'], key=lambda x: x['value'], reverse=True):
            g = "🟢" if pos['gain'] >= 0 else "🔴"
            since_str = ''
            if pos.get('first_bought_at'):
                try:
                    from datetime import datetime
                    bought = pos['first_bought_at']
                    if isinstance(bought, str):
                        bought = datetime.fromisoformat(bought.replace(' ', 'T'))
                    since_str = f" since {bought.strftime('%b %-d')}"
                except Exception:
                    pass
            print(f"  {g} {pos['ticker']}: {pos['shares']:.1f} sh @ ${pos['current_price']:.2f} = ${pos['value']:,.0f} ({pos['gain_pct']:+.1f}%{since_str})")
    
    print("\n" + "=" * 60)
    return prices


def save_snapshots(prices=None):
    """Save daily snapshots for all portfolios."""
    portfolios = get_active_portfolios()
    if not portfolios:
        return
    
    if not prices:
        all_tickers = set()
        for p in portfolios:
            for h in p.get_holdings():
                all_tickers.add(h['ticker'])
        prices = get_current_prices(list(all_tickers))
    
    for p in portfolios:
        val = p.calculate_total_value(prices)
        p.save_daily_snapshot(val['total_value'], val['holdings_value'])
        print(f"Snapshot saved: {p.name} = ${val['total_value']:,.2f}")


def export_dashboard():
    """Export data to GitHub Pages and push."""
    # Use the existing export module
    sys.path.insert(0, os.path.expanduser("~/bigclaw-ai/src"))
    from export_dashboard import export_dashboard as _export
    _export()
    print("Dashboard exported and pushed to GitHub.")


if __name__ == "__main__":
    args = sys.argv[1:]
    
    if not args:
        args = ["--report"]
    
    prices = None
    
    if "--report" in args:
        prices = generate_report()
    
    if "--snapshot" in args:
        save_snapshots(prices)
    
    if "--export" in args:
        export_dashboard()
