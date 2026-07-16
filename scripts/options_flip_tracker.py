# -*- coding: utf-8 -*-
"""Options-flip tracker (free baseline). Daily, for each sector ETF, record call/put VOLUME and
OPEN-INTEREST ratios (near expiries) into options_flow. Detects the puts->calls cycle: OI ratio
trend + a flip above 1.0. Read by the pre-market brief so each 'down-but-turning' sector shows
whether options are confirming. (If UW is re-subscribed, swap the collector for premium-weighted flow.)"""
import sqlite3, os, datetime
import yfinance as yf
os.chdir(os.path.expanduser("~/bigclaw-ai"))
SECTORS = {"XLK":"Technology","XLF":"Financials","XLE":"Energy","XLV":"Health Care","XLI":"Industrials",
 "XLY":"Consumer Disc","XLP":"Staples","XLU":"Utilities","XLB":"Materials","XLRE":"Real Estate","XLC":"Communications"}
conn = sqlite3.connect("src/portfolios.db")
conn.execute("""CREATE TABLE IF NOT EXISTS options_flow (
    snapshot_date TEXT, ticker TEXT, call_vol REAL, put_vol REAL, call_oi REAL, put_oi REAL,
    cp_vol REAL, cp_oi REAL, captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(snapshot_date, ticker))""")
today = str(datetime.date.today())

def collect(sym):
    t = yf.Ticker(sym); cv=pv=coi=poi=0.0
    for e in (t.options or [])[:3]:
        ch = t.option_chain(e)
        cv += ch.calls["volume"].fillna(0).sum();  pv += ch.puts["volume"].fillna(0).sum()
        coi += ch.calls["openInterest"].fillna(0).sum(); poi += ch.puts["openInterest"].fillna(0).sum()
    return cv, pv, coi, poi

for sym in SECTORS:
    try:
        cv, pv, coi, poi = collect(sym)
        conn.execute("INSERT OR REPLACE INTO options_flow (snapshot_date,ticker,call_vol,put_vol,call_oi,put_oi,cp_vol,cp_oi) VALUES (?,?,?,?,?,?,?,?)",
                     (today, sym, cv, pv, coi, poi, cv/pv if pv else 0, coi/poi if poi else 0))
    except Exception as e:
        print("collect fail", sym, e)
conn.commit()

# report: current ratios + trend vs ~5 sessions ago + flip flag
print("%-14s %8s %8s %9s  %s" % ("sector","cp_vol","cp_oi","oi_5d_ago","signal"))
for sym, name in SECTORS.items():
    hist = conn.execute("SELECT snapshot_date, cp_vol, cp_oi FROM options_flow WHERE ticker=? ORDER BY snapshot_date", (sym,)).fetchall()
    cur = hist[-1]; prior = hist[-6] if len(hist) >= 6 else (hist[0] if hist else None)
    cpv, cpoi = cur[1], cur[2]
    prev_oi = prior[2] if prior else None
    sig = ""
    if prev_oi is not None:
        if cpoi > 1.0 and prev_oi <= 1.0: sig = ">>> FLIPPED puts->calls"
        elif cpoi > prev_oi: sig = "calls rising"
        elif cpoi < prev_oi: sig = "puts rising"
    else:
        sig = "(building history)"
    print("%-14s %8.2f %8.2f %9s  %s" % (name, cpv, cpoi, ("%.2f"%prev_oi) if prev_oi is not None else "n/a", sig))
print("\ncp_vol/cp_oi > 1 = calls favored (bullish positioning). Rising OI ratio = puts cycling to calls.")
