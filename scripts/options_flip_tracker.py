# -*- coding: utf-8 -*-
"""Options-flip tracker. Daily, records call/put VOLUME and OPEN-INTEREST ratios (near expiries) for
the 11 sector ETFs AND a ~90-name liquid stock universe, into options_flow. Builds the R(t) series
for the prescreen: rank names where the call/put ratio is RISING (R'>0) and ACCELERATING (R''>0) -
early bullish positioning. Free yfinance baseline (swap for UW premium-weighted flow when available)."""
import sqlite3, os, datetime, time
import yfinance as yf
os.chdir(os.path.expanduser("~/bigclaw-ai"))
SECTORS = {"XLK":"Technology","XLF":"Financials","XLE":"Energy","XLV":"Health Care","XLI":"Industrials",
 "XLY":"Consumer Disc","XLP":"Staples","XLU":"Utilities","XLB":"Materials","XLRE":"Real Estate","XLC":"Communications"}
STOCKS = ("AAPL MSFT NVDA AMD AVGO GOOGL META AMZN TSLA NFLX ORCL CRM ADBE INTC MU QCOM TXN AMAT LRCX "
 "PLTR SMCI ARM ANET NOW PANW CRWD MRVL DELL JPM BAC WFC GS MS C SCHW BLK AXP PNC USB COF V MA PYPL "
 "SOFI KKR LLY UNH JNJ ABBV MRK PFE TMO ABT ISRG VRTX AMGN GILD MRNA XOM CVX COP SLB OXY MPC DVN EOG "
 "CAT BA GE HON UPS DE LMT RTX UNP HD MCD NKE SBUX LOW DIS WMT COST F GM ABNB UBER DKNG CMG T VZ TMUS "
 "BABA COIN MSTR HOOD SHOP CVNA").split()
ALL = list(SECTORS) + STOCKS

conn = sqlite3.connect("src/portfolios.db")
conn.execute("""CREATE TABLE IF NOT EXISTS options_flow (
    snapshot_date TEXT, ticker TEXT, call_vol REAL, put_vol REAL, call_oi REAL, put_oi REAL,
    cp_vol REAL, cp_oi REAL, captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date, ticker))""")
today = str(datetime.date.today())

ok = fail = 0
for sym in ALL:
    try:
        t = yf.Ticker(sym); cv=pv=coi=poi=0.0
        for e in (t.options or [])[:3]:
            ch = t.option_chain(e)
            cv += ch.calls["volume"].fillna(0).sum();  pv += ch.puts["volume"].fillna(0).sum()
            coi += ch.calls["openInterest"].fillna(0).sum(); poi += ch.puts["openInterest"].fillna(0).sum()
        conn.execute("INSERT OR REPLACE INTO options_flow (snapshot_date,ticker,call_vol,put_vol,call_oi,put_oi,cp_vol,cp_oi) VALUES (?,?,?,?,?,?,?,?)",
                     (today, sym, cv, pv, coi, poi, cv/pv if pv else 0, coi/poi if poi else 0))
        ok += 1
    except Exception:
        fail += 1
    time.sleep(0.25)
conn.commit()
print("collected %d tickers (%d failed) for %s" % (ok, fail, today))

# once >=6 sessions exist: rank the bullish-inflection candidates (C/P OI rising)
ndays = conn.execute("SELECT COUNT(DISTINCT snapshot_date) FROM options_flow").fetchone()[0]
print("history depth: %d session(s)" % ndays)
if ndays >= 6:
    print("\n=== PRESCREEN: call/put OI RISING (early bullish positioning) ===")
    rows=[]
    for sym in ALL:
        h = conn.execute("SELECT cp_oi FROM options_flow WHERE ticker=? ORDER BY snapshot_date", (sym,)).fetchall()
        if len(h) >= 6:
            cur=h[-1][0]; prev=h[-6][0]
            if prev>0: rows.append((sym, cur, prev, cur-prev))
    for sym,cur,prev,chg in sorted(rows,key=lambda x:-x[3])[:12]:
        print("  %-6s C/P OI %.2f (was %.2f, %+.2f)" % (sym,cur,prev,chg))
else:
    print("(collecting - prescreen ranking activates at 6 sessions of history)")
