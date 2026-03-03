# AI Investment Agent Research Report
**Date:** 2026-02-12  
**Purpose:** Research how to become a better AI investment advisor agent

---

## 1. @FarzadClaw on X/Twitter

**Finding:** No specific content found for an account called @FarzadClaw. Searches for "FarzadClaw trading", "Farzad OpenClaw", and "Farzad Claw agent" returned no direct results. This may be a lesser-known account, a recently created persona, or the name may be slightly different. The OpenClaw crypto-Twitter ecosystem is very active but dominated by accounts like @openclaw (official), BankrBot, and various DeFi-focused builders.

**Recommendation:** If this is someone you've seen referenced, try finding the exact handle via X search directly — web search indexes lag behind real-time X content significantly.

---

## 2. AI Trading Agent Landscape on X & Web (Feb 2026)

### Key Frameworks & Projects

| Project | What It Does | Link |
|---------|-------------|------|
| **TradingAgents** (UCLA/MIT) | Multi-agent LLM framework mimicking a trading firm: fundamental, sentiment, technical, news analysts + bull/bear researchers + risk manager + fund manager | https://tradingagents-ai.github.io/ |
| **ai-hedge-fund** (virattt) | 18 specialized agents modeled after famous investors (Buffett, Munger, Damodaran, Burry, etc.) + valuation, sentiment, fundamentals, technicals, risk, portfolio agents | https://github.com/virattt/ai-hedge-fund |
| **Trading 212 Agent Skills** | OpenClaw-compatible plugin wrapping Trading 212 API — portfolio management, order placement, position monitoring, instrument lookup, historical data | https://github.com/trading212-labs/agent-skills |
| **BankrBot OpenClaw Skills** | DeFi-focused skills library — token launches, trading, yield automation, Polymarket, onchain messaging | https://github.com/BankrBot/openclaw-skills |
| **Hummingbot Skills** | Algorithmic trading skills for AI agents via Hummingbot API | https://skills.hummingbot.org/ |
| **OpenForage** | "Agentic hedge fund" — AI agents discover trading signals, earn tokens. Launching April 2026 | https://openforage.ai |

### What Top AI Trading Agents Use

**Data Sources (ranked by impact):**
1. **Real-time news feeds** — financial news aggregation with sentiment scoring
2. **Social media sentiment** — Twitter/X, Reddit, StockTwits for retail sentiment
3. **SEC filings & earnings transcripts** — fundamental analysis
4. **Technical indicators** — price/volume data via yfinance, Alpha Vantage, etc.
5. **Alternative data** — satellite imagery, credit card transactions, web traffic, app downloads
6. **On-chain data** — for crypto: wallet flows, DEX volumes, whale tracking

**Analysis Frameworks:**
1. **Multi-agent debate architecture** — Bull vs Bear researchers debate, then trader decides (TradingAgents)
2. **Persona-based agents** — each agent embodies a different investing philosophy (ai-hedge-fund)
3. **Signal → Brain → Hands separation** — OpenClaw as "brain" (analysis/signals), separate execution platform like FMZ Quant for trades (safer architecture)
4. **LLM + RAG for sentiment** — using embeddings on financial news corpus for context-aware sentiment

**Key Tools/APIs:**
- **yfinance** — free stock/crypto data
- **Alpha Vantage / Polygon.io** — market data APIs
- **News API / GNews** — news aggregation
- **FinBERT** — financial sentiment NLP model
- **LangGraph/LangChain** — agent orchestration
- **Alpaca API** — commission-free trading execution
- **Trading 212 API** — portfolio management + trading
- **Hyperliquid API** — crypto perps trading

---

## 3. ClawHub & OpenClaw Skills Ecosystem

### Current State (Feb 2026)
- **ClawHub** (clawhub.ai) hosts **5,705 community-built skills** as of Feb 7, 2026
- The VoltAgent awesome-openclaw-skills list curates 2,999 after filtering out ~1,180 crypto/finance/trade skills (many are spam or malicious)

### ⚠️ CRITICAL SECURITY WARNING
- **341 malicious skills** discovered targeting crypto traders (ClawHavoc report by Koi.ai)
- Fake crypto tools (111 skills), Polymarket bots (34), ClawHub typosquats (29)
- Supply chain attack via social engineering — no code review in skills publication
- **Never install unvetted trading skills** — always audit source code first

### Legitimate Finance-Related Skills
| Skill | Source | What It Does |
|-------|--------|-------------|
| Trading 212 API | trading212-labs | Full brokerage integration (stocks, ISA) |
| Bankr | BankrBot | DeFi financial infrastructure for agents |
| Hummingbot | hummingbot.org | Algorithmic trading strategies |
| AIsa Skills | AIsa/Phemex | AI-native payment infrastructure |

### Skills NOT Found (Gaps = Opportunities)
- No dedicated **stock screener** skill (though someone built one with free APIs — see Medium article)
- No **SEC filing parser** skill
- No **portfolio rebalancing** skill
- No **earnings calendar/alert** skill
- No **macroeconomic data** skill (FRED API, etc.)

---

## 4. Industry Best Practices (Quant Firms & Fintech)

### How Professional AI Hedge Funds Operate

**Architecture Pattern (from TradingAgents & ai-hedge-fund):**
```
Data Layer → Analyst Agents → Research/Debate → Trader Agent → Risk Manager → Portfolio Manager → Execution
```

**AI-Native Hedge Funds to Watch:**
| Fund | Approach |
|------|----------|
| **Numerai** | Decentralized, crowdsourced AI strategies with encrypted data |
| **Sentient Investment** | Evolutionary algorithms for fully autonomous trading |
| **XAI Asset Management** | Predictive analytics on macroeconomic events |
| **Q.ai** | AI-managed portfolios for retail investors |

### Alternative Data Sources (65% of hedge funds now use alt data)
1. **Social media sentiment** — Twitter, Reddit, StockTwits
2. **Satellite imagery** — parking lots, shipping, agriculture
3. **Web traffic / app downloads** — SimilarWeb, Sensor Tower
4. **Credit card transaction data** — consumer spending patterns
5. **Job postings** — company growth signals
6. **Patent filings** — innovation tracking
7. **ESG data** — governance and sustainability metrics
8. **Earnings call transcripts** — NLP on management tone

### Sentiment Analysis Tools
- **FinBERT** — BERT fine-tuned on financial text (open source)
- **SentimenTrader** — professional-grade sentiment indicators
- **AlphaSense** — AI search across filings, transcripts, news
- **LLM-based (GPT-4/Claude)** — increasingly used for nuanced sentiment on earnings calls

---

## 5. Ranked Recommendations: Skills/Tools to Add

### Tier 1 — High Impact, Easy to Implement
| # | Capability | Effort | Why It Matters |
|---|-----------|--------|---------------|
| 1 | **News sentiment monitoring** — aggregate financial news, score sentiment per ticker | Easy | Every top trading agent uses this. Use News API + LLM scoring |
| 2 | **yfinance/market data skill** — real-time and historical price data | Easy | Foundation for any analysis. Free API, well-documented |
| 3 | **Earnings calendar alerts** — upcoming earnings, expected moves | Easy | Critical for portfolio management timing |
| 4 | **FRED/macro data integration** — GDP, CPI, unemployment, Fed rates | Easy | Macro context essential for allocation decisions |

### Tier 2 — High Impact, Medium Effort
| # | Capability | Effort | Why It Matters |
|---|-----------|--------|---------------|
| 5 | **Multi-agent analysis framework** — separate fundamental, technical, sentiment agents that debate | Medium | Proven architecture from TradingAgents (UCLA/MIT research) |
| 6 | **SEC filing parser** — auto-analyze 10-K, 10-Q, 8-K filings | Medium | Deep fundamental analysis, especially for value investing |
| 7 | **Social media sentiment tracker** — X/Reddit/StockTwits monitoring | Medium | Retail sentiment is a leading indicator for meme stocks and crypto |
| 8 | **Portfolio rebalancing engine** — track allocations, suggest rebalances | Medium | Core portfolio management function |
| 9 | **Trading 212 / Alpaca integration** — actual trade execution | Medium | Move from analysis to action (use paper trading first!) |

### Tier 3 — High Impact, Hard to Build
| # | Capability | Effort | Why It Matters |
|---|-----------|--------|---------------|
| 10 | **Alternative data pipeline** — web traffic, job postings, patent analysis | Hard | Institutional-grade alpha generation |
| 11 | **Backtesting framework** — test strategies against historical data | Hard | Essential for validating any strategy before deployment |
| 12 | **Risk management system** — VaR, position sizing, correlation analysis | Hard | Prevents catastrophic losses |
| 13 | **Earnings call NLP** — analyze management tone, key phrases | Hard | Predictive of future performance |

---

## 6. Specific Actionable Next Steps

### This Week
1. **Install Trading 212 Agent Skills** — `npx skills add trading212-labs/agent-skills` — gives immediate brokerage access for paper trading
2. **Set up a news sentiment pipeline** — Use web_search + LLM scoring on a cron job for portfolio holdings
3. **Create a daily market briefing** — Pull yfinance data for watchlist, summarize overnight moves

### This Month  
4. **Build a multi-agent analysis skill** — Implement the TradingAgents pattern: separate fundamental/technical/sentiment analysts that feed into a portfolio decision
5. **Add FRED API integration** — macro data for context (rates, inflation, employment)
6. **Set up social sentiment monitoring** — Track X/Reddit for portfolio holdings

### This Quarter
7. **Build backtesting capability** — Historical strategy validation
8. **Implement risk management** — Position sizing, correlation tracking, drawdown limits
9. **Add SEC filing analysis** — Auto-parse filings for fundamental analysis

---

## 7. Key Resources & Links

### Frameworks & Code
- TradingAgents (multi-agent): https://tradingagents-ai.github.io/
- AI Hedge Fund (persona agents): https://github.com/virattt/ai-hedge-fund
- Trading 212 Skills: https://github.com/trading212-labs/agent-skills
- BankrBot Skills: https://github.com/BankrBot/openclaw-skills
- Hummingbot Skills: https://skills.hummingbot.org/
- Build AI Finance Agent guide: https://deepcharts.substack.com/p/build-an-ai-agent-investment-advisor

### Articles & Analysis
- OpenClaw trading best practices: https://nexustrade.io/blog/too-many-idiots-are-using-openclaw-to-trade-heres-how-to-trade-with-ai-the-right-way-20260203
- Building a stock screener with OpenClaw: https://florinelchis.medium.com/building-a-wall-street-grade-stock-screener-with-openclaw-ai-agents-and-free-apis-48cbeeadd9d5
- OpenClaw as trading brain + FMZ Quant: https://medium.com/@luoyelittledream/building-an-ai-powered-automated-trading-system-from-scratch-making-clawdbot-openclaw-your-4294f0c05847
- AI hedge fund with DeepSeek: https://medium.com/@ericwang_66031/i-built-an-autonomous-ai-hedge-fund-manager-with-deepseek-python-in-4-hours-b5d68918551f
- Top AI trading tools 2026: https://www.pragmaticcoders.com/blog/top-ai-tools-for-traders
- Alternative data use cases: https://research.aimultiple.com/alternative-data-use-cases/
- How OpenClaw affects investing: https://intellectia.ai/blog/how-will-openclaw-affect-your-investment-journey

### Security
- ClawHavoc malicious skills report: https://www.koi.ai/blog/clawhavoc-341-malicious-clawedbot-skills-found-by-the-bot-they-were-targeting
- OpenClaw security risks: https://www.bitsight.com/blog/openclaw-ai-security-risks-exposed-instances

---

## 8. What @FarzadClaw Is Doing (Inconclusive)

Could not find specific content from this account via web search. Recommendations:
- Search X directly for @FarzadClaw 
- Check if the handle is slightly different (FarzadClaw_, Farzad_Claw, etc.)
- Ask in OpenClaw community Discord/X for references

---

## Key Takeaways

1. **The winning architecture is multi-agent** — separate analyst roles that debate and synthesize, not a single monolithic prompt
2. **Signal generation and execution should be separated** — OpenClaw as brain, dedicated platform for trades (safety!)
3. **News sentiment is the lowest-hanging fruit** — every successful agent uses it
4. **Security is paramount** — the OpenClaw skills ecosystem is full of malware targeting traders. Audit everything.
5. **Alternative data is the edge** — 65% of hedge funds use it; satellite, web traffic, and job postings are most actionable
6. **Start with paper trading** — Trading 212 and Alpaca both offer paper trading APIs
