# -*- coding: utf-8 -*-
"""Screen 11 sectors for a DOWN-BUT-TURNING inflection: beaten down over 1-3 months, but the
rate-of-change has flipped from negative to positive (2nd-derivative turning up), price reclaiming
its 20d MA with the MA slope turning up. The opposite of chasing a mature leader."""
import yfinance as yf, numpy as np
SEC={"XLK":"Technology","XLF":"Financials","XLE":"Energy","XLV":"Health Care","XLI":"Industrials",
 "XLY":"Consumer Disc","XLP":"Staples","XLU":"Utilities","XLB":"Materials","XLRE":"Real Estate","XLC":"Communications"}
etfs=list(SEC)
d=yf.download(etfs,period="5mo",progress=False,auto_adjust=True)["Close"].dropna()

rows=[]
for t in etfs:
    s=d[t].dropna()
    r63=(s.iloc[-1]/s.iloc[-63]-1)*100      # 3mo (down check)
    r21=(s.iloc[-1]/s.iloc[-21]-1)*100      # 1mo
    r10=(s.iloc[-1]/s.iloc[-10]-1)*100      # 10d (turning)
    r5=(s.iloc[-1]/s.iloc[-5]-1)*100        # 5d
    # rate-of-change acceleration: recent daily pace vs the month's pace (2nd derivative sign)
    accel=(r5/5)-(r21/21)
    ma20=s.rolling(20).mean()
    ma20_slope=(ma20.iloc[-1]/ma20.iloc[-6]-1)*100   # is the 20d MA turning up
    above20 = s.iloc[-1] > ma20.iloc[-1]
    # inflection flag: beaten down (3mo or 1mo negative) AND turning (5d>0, accel>0)
    turning = (r63 < 2 or r21 < 0) and r5 > 0 and accel > 0
    rows.append((t,SEC[t],r63,r21,r10,r5,accel,ma20_slope,above20,turning))

print("%-14s %6s %6s %6s %6s %7s %8s %6s  %s" % ("sector","3mo%","1mo%","10d%","5d%","accel","MAslope",">20MA","TURN?"))
for r in sorted(rows, key=lambda x:(-int(x[9]), -x[6])):
    print("%-14s %+6.1f %+6.1f %+6.1f %+6.1f %+7.2f %+7.1f %6s  %s" % (
        r[1],r[2],r[3],r[4],r[5],r[6],r[7], "yes" if r[8] else "no", ">>> INFLECTING" if r[9] else ""))

print("\nMost beaten-down 3mo (mean-reversion candidates):",
      [SEC[t] for t,_,r63,*_ in sorted([(x[0],)+x[1:] for x in rows], key=lambda z:z[2])[:3]])
inflecting=[r for r in rows if r[9]]
print("Down-but-turning (inflection) sectors:", [r[1] for r in inflecting] or "none clean today")
