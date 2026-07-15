# -*- coding: utf-8 -*-
"""Overnight pre-market case builder. Runs ~6am CT: find the rising sector, pick a few leaders,
run Bull/Bear/Judge to MAKE THE CASE for each, post a brief to Slack for Curtis to review + question
before the 8:30 tape. Untethered from timers/rules; this is a case FOR review, not an auto-trade.
Usage: overnight_case.py [--test] [N]"""
import os, sys, datetime
import yfinance as yf
from anthropic import Anthropic

TEST = "--test" in sys.argv
N = next((int(a) for a in sys.argv[1:] if a.isdigit()), 3)
SLACK_CH = "D0ADHLUJ400"
c = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
def ask(model, sysp, user, mt=1400):
    return c.messages.create(model=model, max_tokens=mt, system=sysp, messages=[{"role": "user", "content": user}]).content[0].text.strip()

SECTORS = {
 "XLK":"Technology","XLF":"Financials","XLE":"Energy","XLV":"Health Care","XLI":"Industrials",
 "XLY":"Consumer Disc.","XLP":"Staples","XLU":"Utilities","XLB":"Materials","XLRE":"Real Estate","XLC":"Communications"}
STOCKS = {
 "XLK":["NVDA","MSFT","AVGO","AMD","ORCL","CRM","ADBE","AAPL","PLTR","ANET"],
 "XLF":["JPM","BAC","WFC","GS","MS","SCHW","BLK","AXP","C","KKR","RJF","VOYA"],
 "XLE":["XOM","CVX","COP","SLB","EOG","MPC","PSX","OXG","WMB","OKE"],
 "XLV":["LLY","UNH","JNJ","ABBV","MRK","TMO","ABT","ISRG","VRTX","AMGN"],
 "XLI":["CAT","GE","HON","UNP","DE","BA","LMT","RTX","ETN","PH"],
 "XLY":["AMZN","TSLA","HD","MCD","NKE","LOW","BKNG","SBUX","TJX"],
 "XLP":["PG","KO","PEP","COST","WMT","MDLZ","CL"],
 "XLU":["NEE","SO","DUK","CEG","VST","D","AEP","EXC"],
 "XLB":["LIN","SHW","FCX","NEM","APD","ECL"],
 "XLRE":["PLD","AMT","EQIX","WELL","SPG","O"],
 "XLC":["GOOGL","META","NFLX","DIS","TMUS","VZ","T"]}

# 1) rank sectors (blend 5d + 20d momentum)
etfs=list(SECTORS); d=yf.download(etfs,period="2mo",progress=False)["Close"]
def mom(t,n): s=d[t].dropna(); return (s.iloc[-1]/s.iloc[-n]-1)*100 if len(s)>n else 0
score={t: 0.5*mom(t,5)+0.5*mom(t,20) for t in etfs}
lead=max(score,key=score.get)
print("Leading sector: %s (%s)  5d %+.1f%% / 20d %+.1f%%" % (SECTORS[lead],lead,mom(lead,5),mom(lead,20)))

# 2) rank names in the leading sector by 5d momentum, take top N
names=STOCKS[lead]
pd=yf.download(names,period="1mo",progress=False)["Close"]
nm=[]
for t in names:
    try:
        s=pd[t].dropna(); nm.append((t,(s.iloc[-1]/s.iloc[-5]-1)*100))
    except Exception: pass
picks=[t for t,_ in sorted(nm,key=lambda x:-x[1])[:N]]
print("Picks:", picks)

# 3) make the case for each
BULL="You are a sharp buy-side analyst. In 2 tight paragraphs, make the STRONGEST data-cited BULL case for owning this stock now, within a leading sector. Be concrete."
BEAR="You are a sharp skeptic. In 1 tight paragraph, give the STRONGEST specific BEAR case / key risk that would prove the bull wrong."
JUDGE="You are a seasoned analyst briefing an investor before the open. Given the bull and bear, write: (a) THE CASE IN 2 SENTENCES (why this is worth his attention today), (b) THE CRUX (the one question it hinges on), (c) WATCH (2 concrete signals). Tight, honest, no buy/sell order."

blocks=[]
for t in picks:
    inf=yf.Ticker(t).info; g=lambda k,dd="n/a": inf.get(k,dd)
    news=[n.get("title") or n.get("content",{}).get("title","") for n in (yf.Ticker(t).news or [])[:6]]; news=[x for x in news if x]
    data=f"{t} — {g('longName')} | ${g('currentPrice')} | fwdPE {g('forwardPE')} | mean target ${g('targetMeanPrice')} ({g('recommendationKey')})\nBusiness: {(g('longBusinessSummary') or '')[:500]}\nHeadlines:\n"+"\n".join(f"  - {h}" for h in news)
    bull=ask("claude-sonnet-4-6",BULL,data)
    bear=ask("claude-sonnet-4-6",BEAR,data+"\nBULL:\n"+bull)
    judge=ask("claude-opus-4-8",JUDGE,data+"\nBULL:\n"+bull+"\nBEAR:\n"+bear,mt=800)
    blocks.append(f"*{t} — {g('longName')}*  (${g('currentPrice')}, target ${g('targetMeanPrice')})\n{judge}\n_Bull:_ {bull[:600]}\n_Bear:_ {bear[:400]}")
    print("  done:", t)

today=datetime.date.today().isoformat() if not TEST else "TEST"
brief=(f":sunrise: *BigClaw Pre-Market Brief — {today}*\n"
       f"Leading sector: *{SECTORS[lead]}* ({lead}, +{mom(lead,20):.1f}% 1mo). Candidates below — review & ask questions before the 8:30 tape.\n\n"
       + "\n\n———\n\n".join(blocks)
       + "\n\n_Cases for your review, not auto-trades. Reply with questions and I'll re-loop the analysis._")

if TEST:
    print("\n"+"="*70+"\n"+brief[:4000])
else:
    from slack_sdk import WebClient
    wc=WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    for i in range(0,len(brief),38000):
        wc.chat_postMessage(channel=SLACK_CH,text=brief[i:i+38000],mrkdwn=True)
    print("posted to Slack")
