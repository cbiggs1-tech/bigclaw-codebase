# BigClaw Skills & Capabilities Assessment
**Date:** 2026-04-01 12:31
**Models:** Claude Opus 4.6, Grok 4.20 Beta, Gemini 3.1 Pro, GPT-5.4

---

## Round 1: Independent Assessment

### Claude Opus 4.6



# BigClaw Investment Bot — Architecture Assessment & Upgrade Roadmap

---

## 1. STRENGTHS

BigClaw is remarkably advanced for a Raspberry Pi–based autonomous system. Credit where due:

| Strength | Why It Matters |
|---|---|
| **7 IPS from multi-model debate** | This is institutional-grade. Most retail bots have zero formal policy. The gate/reject/audit/signal-weight structure creates a defensible, auditable decision framework. This alone puts BigClaw in the top 1% of retail bot architectures. |
| **20-dimension scoring engine with style gates** | Prevents style drift — the #1 silent killer of systematic strategies. Each portfolio has a defined identity. |
| **Paper portfolios before live capital** | Proper walk-forward validation. Most builders skip this and lose money learning. |
| **15-min trailing stop refresh** | Meaningful downside protection. Most retail systems check stops daily at best, missing intraday crashes. |
| **Multi-channel signal fusion** (fundamentals + sentiment + dark pool + insider + institutional flow) | No single signal source dominates. This diversification of alpha sources reduces correlation to any one data failure. |
| **Saturday candidate screener** | Weekend batch processing when markets are closed = no resource contention with real-time systems. Smart scheduling. |
| **Weekly compliance audit** | Self-policing loop. Catches drift, rule violations, and data staleness before they compound. |
| **Skill-vetting + self-improve skills** | Meta-cognitive layer — the bot can evaluate and upgrade its own capabilities. This is the foundation for compounding improvement. |
| **Full observability stack** (Uptime Kuma, log-analyzer, Slack/Discord, GitHub Pages) | You can't fix what you can't see. Most retail systems are black boxes to their own creators. |
| **Unusual Whales dark pool integration** | Access to non-exchange order flow data that most retail investors never see. Genuine informational edge. |

---

## 2. CRITICAL GAPS (Direct Impact on Returns & Risk)

### GAP 2.1 — No Live Execution Engine
- **Current State:** 7 paper portfolios on Alpaca, autonomous daily trading — but no evidence of live capital deployment with position sizing, slippage modeling, or execution quality measurement.
- **Why It Matters:** Paper trading has zero slippage, zero market impact, zero emotional/liquidity risk. Academic research (Harvey et al., 2016) shows strategies lose 40-70% of backtested alpha when moving to live execution. Every day in paper-only mode is a day where the IPS validation is incomplete.
- **Return/Risk Impact:** Without live execution, you cannot measure true Sharpe, true max drawdown, or true win rate. You are optimizing a simulation, not a portfolio.
- **Implementation:** Deploy 1 portfolio live on Alpaca with minimum position sizes ($100-500/position). Implement execution quality measurement (compare fill price vs. decision price). Add slippage tracking as a new metric in the scoring engine.
- **Priority:** **CRITICAL** | **Effort:** 1-2 Weeks
- **Milestone:** First live trade with full audit trail within 14 days.

### GAP 2.2 — No Correlation-Aware Portfolio Construction
- **Current State:** 20-dimension scoring ranks individual stocks. No evidence of cross-holding correlation analysis, sector concentration limits enforced at the portfolio level, or covariance-based position sizing.
- **Why It Matters:** You can pick 7 "perfect" stocks that are all 0.92 correlated to each other. In a drawdown, they all fall together. Diversification is the only free lunch in investing (Markowitz, 1952). The IPS gate rules likely catch some of this via sector limits, but without a correlation matrix, concentrated factor exposure will slip through.
- **Return/Risk Impact:** A portfolio of 10 uncorrelated 15%-return assets has ~4.7% volatility. The same assets at 0.8 correlation have ~13.4% volatility. That's a Sharpe ratio difference of ~2x for the same gross return.
- **Implementation:** Add a `portfolio-correlation-engine` skill. Pull 90-day rolling correlation matrix from yfinance daily closes. Before any new position is added, compute marginal portfolio correlation impact. Reject if portfolio average pairwise correlation exceeds IPS threshold (suggest 0.55). Use `afrexai-portfolio-risk` as the foundation — it likely already has some of this data.
- **Priority:** **CRITICAL** | **Effort:** 1 Week

### GAP 2.3 — No Regime Detection Driving Allocation
- **Current State:** `market-environment-analysis` and `us-market-bubble-detector` exist, but there's no evidence they dynamically adjust position sizing, cash allocation, or strategy selection.
- **Why It Matters:** A momentum strategy that returns +25% in bull markets returns -40% in bear markets. If your regime detector says "bear" but your portfolios stay fully invested in momentum names, the detector is decoration. 70-80% of stock returns are explained by market regime (Fama & French).
- **Return/Risk Impact:** Simple regime-based cash allocation (e.g., 100% invested in bull, 50% in neutral, 20% in bear) historically reduces max drawdown by 30-50% while sacrificing only 10-15% of upside.
- **Implementation:** Create a `regime-allocation-controller` that sits between the scoring engine and the execution layer. Map `market-environment-analysis` output to discrete regimes {BULL, NEUTRAL, BEAR, CRISIS}. Each IPS defines allocation % per regime. The controller scales position sizes accordingly before orders are generated.
- **Priority:** **CRITICAL** | **Effort:** 1-2 Weeks

### GAP 2.4 — No Drawdown Circuit Breaker
- **Current State:** 15-min trailing stops protect individual positions. No evidence of portfolio-level drawdown limits, daily loss limits, or automatic de-risking when multiple stops trigger simultaneously.
- **Why It Matters:** In a correlated selloff (2020 COVID, 2022 rate shock), 5 trailing stops can trigger in the same hour. Each individual stop works correctly, but the portfolio just lost 15% in a day. Without a portfolio-level circuit breaker, cascading individual stop-losses create realized losses that compound.
- **Return/Risk Impact:** A 10% portfolio drawdown requires 11.1% to recover. A 30% drawdown requires 42.9%. A 50% drawdown requires 100%. Circuit breakers at -5% daily / -12% weekly / -20% monthly prevent catastrophic compounding.
- **Implementation:** Add a `circuit-breaker` module that monitors aggregate portfolio P&L intraday. If daily loss exceeds IPS-defined threshold, liquidate to cash and halt new entries for 24-48 hours. Log the event, trigger Slack/Discord alert, and require manual override to resume.
- **Priority:** **CRITICAL** | **Effort:** 3-5 Days

### GAP 2.5 — No Options Greeks Management
- **Current State:** `options-strategy-advisor` exists. TSLA watchdog monitors options flow. But no evidence of real-time Greeks tracking (delta, gamma, theta, vega) for any options positions, or portfolio-level Greeks aggregation.
- **Why It Matters:** An options position without Greeks monitoring is a leveraged bet without a speedometer. Theta decay alone can destroy 30-50% of an at-the-money option's value in the final 2 weeks. Gamma risk near expiration can cause P&L swings of 5-10x the underlying move.
- **Return/Risk Impact:** Systematic theta harvesting strategies (e.g., selling 30-45 DTE puts on high-scoring names) generate 15-25% annual returns with proper Greeks management. Without it, options positions are speculative rather than systematic.
- **Implementation:** Add a `greeks-engine` skill using `py_vollib` or `QuantLib`. Track portfolio-level delta, gamma, theta, vega. Set IPS-level limits (e.g., portfolio delta < 0.7, portfolio theta > -$X/day). Alert when Greeks breach thresholds.
- **Priority:** **HIGH** | **Effort:** 1-2 Weeks

### GAP 2.6 — No Transaction Cost Model
- **Current State:** No evidence of commission, spread, slippage, or market impact modeling in the scoring engine or backtester.
- **Why It Matters:** A strategy that trades 3x/week with $0.02 average slippage per share on 100-share lots loses $312/year per position to friction. If the strategy's edge is 2% annually on a $5,000 position ($100), friction alone makes it negative EV. This is the #1 reason backtested strategies fail live.
- **Return/Risk Impact:** Proper cost modeling eliminates 30-50% of false-positive trade signals, dramatically improving live Sharpe ratio.
- **Implementation:** Add a `transaction-cost-model` to the scoring engine. For each candidate trade, estimate: spread cost (use bid-ask from yfinance), market impact (function of position size vs. average daily volume), and opportunity cost of limit vs. market orders. Subtract total estimated cost from expected return. Reject trades where cost > 20% of expected edge.
- **Priority:** **HIGH** | **Effort:** 3-5 Days

---

## 3. SKILL REDUNDANCIES

| Redundancy Cluster | Skills Involved | Recommendation |
|---|---|---|
| **Stock Evaluation Overlap** | `fundamental-stock-analysis`, `stock-evaluator`, `intellectia-stock-forecast`, `sector-analyst` | These likely overlap significantly. `fundamental-stock-analysis` and `stock-evaluator` probably pull the same yfinance fields. **Merge** into a single `equity-scoring-engine` with sub-modules for value, growth, quality, and momentum factors. Keep `intellectia-stock-forecast` only if it provides a genuinely different ML-based signal. Keep `sector-analyst` as a top-down overlay. **Impact:** Reduces maintenance burden by ~40%, eliminates conflicting signals, simplifies audit trail. **Effort:** 1 Week. |
| **Backtesting Overlap** | `backtest-expert`, `stock-strategy-backtester` | Two backtesting skills is one too many unless they serve fundamentally different purposes (e.g., one for single-stock signals, one for portfolio-level). **Merge** into a single `backtesting-engine` with modes: {single-asset, portfolio, walk-forward, Monte Carlo}. **Impact:** Single source of truth for historical validation. **Effort:** 3-5 Days. |
| **Portfolio/Risk Overlap** | `portfolio-manager`, `afrexai-portfolio-risk` | If `portfolio-manager` handles allocation and `afrexai-portfolio-risk` handles risk metrics, they should be tightly coupled or merged. Risk-unaware portfolio management is dangerous; portfolio-unaware risk analysis is useless. **Merge** into `portfolio-risk-manager` with unified state. **Impact:** Prevents allocation decisions that ignore risk constraints. **Effort:** 3-5 Days. |
| **Sentiment Overlap** | `realtime-x-sentiment-tracker` + X sentiment tracking (listed as capability) | These appear to be the same thing listed twice. Confirm and deduplicate. **Effort:** Hours. |

**Net effect of deduplication:** Reduce from 27 skills to ~22, lower cognitive overhead, fewer integration points to maintain, clearer audit trails.

---

## 4. NEW CAPABILITIES NEEDED

### 4.1 — Earnings Event Risk Manager
- **Gap:** No pre-earnings position management. Earnings announcements cause 5-15% overnight gaps that trailing stops cannot protect against.
- **Return/Risk Impact:** Avoiding or hedging 2-3 adverse earnings surprises per year saves 3-8% portfolio drawdown annually.
- **Implementation:** Skill `earnings-event-manager`. Pull earnings calendar (yfinance or Earnings Whispers). 3 days before earnings: flag positions, reduce size by 50% or buy protective puts per IPS rules. Post-earnings: re-evaluate and resize.
- **Priority:** **HIGH** | **Effort:** 3-5 Days

### 4.2 — Macro Factor Monitor
- **Gap:** No tracking of interest rates, yield curve, DXY, VIX term structure, credit spreads, or Fed funds futures. These drive 60-70% of equity market direction.
- **Return/Risk Impact:** Yield curve inversion has predicted every recession since 1970 with 12-18 month lead time. Credit spread widening >100bps signals risk-off. Ignoring these is flying blind on the macro environment.
- **Implementation:** Skill `macro-factor-monitor`. Pull from FRED API (free): 10Y-2Y spread, HY OAS, Fed funds rate, CPI. Pull from yfinance: ^VIX, DX-Y.NYB, ^TNX. Compute composite macro score. Feed into regime-allocation-controller (Gap 2.3).
- **Priority:** **HIGH** | **Effort:** 1 Week

### 4.3 — Alpha Decay Tracker
- **Gap:** No measurement of whether each signal source's predictive power is degrading over time. All alpha sources decay — typically 20-40% per year as markets adapt.
- **Return/Risk Impact:** Continuing to weight a decayed signal equally costs 2-5% annual return through false signals. Detecting decay early and downweighting saves this.
- **Implementation:** Skill `alpha-decay-tracker`. For each of the 20 scoring dimensions, track rolling 90-day hit rate (did the signal predict the correct direction?). If hit rate drops below 52% (barely above random), flag for review and auto-downweight by 50%. Weekly report.
- **Priority:** **HIGH** | **Effort:** 1 Week

### 4.4 — Liquidity Screener
- **Gap:** No evidence of liquidity filtering. Low-liquidity stocks have wider spreads, higher slippage, and can trap positions during selloffs.
- **Return/Risk Impact:** A position in a stock trading $500K/day average volume with a $5,000 position represents 1% of daily volume — acceptable. A $5,000 position in a $50K/day stock represents 10% — you ARE the market. Exit slippage alone can cost 2-5%.
- **Implementation:** Add liquidity gate to scoring engine: minimum average daily dollar volume > 20x maximum position size. Minimum bid-ask spread < 0.3%. Reject all candidates that fail. Use yfinance `averageVolume` and `bid`/`ask` fields already mapped in IPS.
- **Priority:** **HIGH** | **Effort:** 1 Day

### 4.5 — Tax-Loss Harvesting Automation
- **Gap:** `afrexai-tax-planning` exists but no evidence of automated tax-loss harvesting — the single highest-impact tax strategy for taxable accounts.
- **Return/Risk Impact:** Systematic TLH adds 0.5-1.5% annually after-tax (Betterment research, Wealthfront research). On a $100K portfolio, that's $500-$1,500/year of free alpha.
- **Implementation:** Enhance `afrexai-tax-planning` to: scan positions daily for unrealized losses > $100, check 30-day wash sale window, identify correlated replacement securities, execute swap, log tax lot. Requires tracking cost basis per lot.
- **Priority:** **MEDIUM** | **Effort:** 1-2 Weeks

### 4.6 — Benchmark Tracking & Attribution
- **Gap:** No evidence of performance attribution vs. benchmarks. Without this, you cannot answer: "Is BigClaw adding alpha, or is the market just going up?"
- **Return/Risk Impact:** If BigClaw returns 15% but SPY returned 18%, BigClaw destroyed 3% of value. Without attribution, you'd celebrate the 15%. This is the most dangerous blind spot in investing.
- **Implementation:** Skill `performance-attribution`. Track daily NAV per portfolio. Compare vs. appropriate benchmark (SPY for large-cap, IWM for small-cap, QQQ for tech). Decompose returns into: market beta, sector allocation, stock selection, timing. Weekly Slack report. Add to GitHub Pages dashboard.
- **Priority:** **HIGH** | **Effort:** 1 Week

### 4.7 — Order Execution Optimizer
- **Gap:** No evidence of smart order routing, TWAP/VWAP execution, or limit order management.
- **Return/Risk Impact:** Market orders on Alpaca route through payment-for-order-flow, costing 0.5-2 cents/share in price improvement loss. On 1,000 trades/year at 100 shares average, that's $500-$2,000 in hidden costs.
- **Implementation:** Implement limit order strategy: place limit at mid-price, wait 30 seconds, if unfilled widen by 1 tick, repeat up to 3x, then market order. For positions > 5% of ADV, implement TWAP over 30 minutes.
- **Priority:** **MEDIUM** | **Effort:** 3-5 Days

---

## 5. DATA SOURCE GAPS

| Missing Data Source | What It Provides | Return/Risk Impact | Implementation | Priority | Effort |
|---|---|---|---|---|---|
| **FRED API** | Interest rates, yield curve, credit spreads, CPI, unemployment, GDP | Macro regime detection. Missing this means ignoring the single largest driver of equity returns. | Free API key. Python `fredapi` library. Feed into macro-factor-monitor. | **CRITICAL** | Hours |
| **Options Chain Greeks (live)** | Real-time delta, gamma, theta, vega, IV rank, IV percentile | Without this, options positions are unmanaged leveraged bets. IV rank alone determines whether options are cheap or expensive. | CBOE data via Unusual Whales (already integrated) or Tradier API (free tier). | **HIGH** | Days |
| **Earnings Calendar + Estimates** | Earnings dates, consensus EPS, revenue estimates, whisper numbers | Pre-earnings risk management (Gap 4.1). Earnings surprises drive 60% of single-stock vol. | Earnings Whispers API, or yfinance `.earnings_dates`. | **HIGH** | Hours |
| **Fund Flow Data** | ETF inflows/outflows, mutual fund flows | Identifies sector rotation before price moves. $1B flowing into XLK over 2 weeks signals institutional tech conviction. | ETF.com (scrape), or ICI weekly data (free). | **MEDIUM** | Days |
| **Short Interest Data** | Shares short, days to cover, short % of float | Short squeezes (GME) and crowded shorts are both alpha signals and risk factors. | FINRA (bi-monthly, free), or Ortex (paid, real-time). | **MEDIUM** | Days |
| **Insider Transaction Enrichment** | Cluster buys, 10b5-1 plan vs. discretionary, insider track record | `openinsider` provides raw data. Enrichment separates signal from noise. Cluster buys by 3+ insiders within 2 weeks have 70%+ hit rate at 12 months (Lakonishok & Lee, 2001). | Enrich `openinsider` output with clustering logic and historical insider accuracy scoring. | **MEDIUM** | 1 Week |
| **Alternative Data: Satellite/Web Traffic** | Store foot traffic, app downloads, web visits | Leading indicators for revenue surprises. 2-4 week lead time on earnings. | SimilarWeb (free tier for web traffic), Apptopia (paid). Start with SimilarWeb only. | **LOW** | 1-2 Weeks |
| **Bond/Credit Market Data** | Corporate bond spreads, CDS spreads for individual names | Credit markets price distress 3-6 months before equity markets. If a company's CDS spread doubles, equity risk is elevated regardless of what the stock chart shows. | FRED (HY OAS index), or ICE BofA indices. Individual CDS requires Bloomberg or paid source. | **MEDIUM** | Days |

---

## 6. AUTOMATION GAPS

### 6.1 — No Automated IPS Compliance Enforcement
- **Current State:** Weekly compliance audit exists, but it's periodic, not real-time. A rule violation on Monday isn't caught until Saturday.
- **Impact:** 5 trading days of drift before correction. In a volatile week, this can mean 3-5% of avoidable loss.
- **Fix:** Pre-trade compliance check. Before every order is submitted, validate against IPS gates: sector concentration, position size limits, correlation threshold, regime allocation, liquidity minimum. Reject non-compliant orders with logged reason. Post-trade check within 1 hour of execution.
- **Priority:** **CRITICAL** | **Effort:** 3-5 Days

### 6.2 — No Automated Rebalancing
- **Current State:** Daily trading exists, but no evidence of systematic rebalancing to target weights.
- **Impact:** Without rebalancing, winning positions grow to dominate the portfolio (concentration risk) and losing positions shrink to irrelevance (dead weight). A 5% position that doubles to 10% now represents 2x the intended risk.
- **Fix:** Daily post-market check: if any position deviates >2% from target weight (or >25% relative deviation), generate rebalance order for next open. Respect IPS tax rules (don't rebalance if it triggers short-term capital gains above threshold).
- **Priority:** **HIGH** | **Effort:** 3-5 Days

### 6.3 — No Automated Data Quality Validation
- **Current State:** 5x daily price refresh, but no evidence of data quality checks. Yahoo Finance is free and occasionally returns stale, null, or incorrect data.
- **Impact:** A single bad price feed (e.g., yfinance returns $0 for a stock) could trigger a trailing stop, generating a false sell signal. Or a null fundamental field could cause a scoring error that promotes a bad candidate.
- **Fix:** Add data validation layer: check for nulls, check for >20% price change vs. previous close (flag for manual review), check for stale timestamps, cross-reference critical prices against a second source (e.g., Alpaca's own market data). Log all anomalies.
- **Priority:** **HIGH** | **Effort:** 2-3 Days

### 6.4 — No Automated Failover / Disaster Recovery
- **Current State:** Running on a single Raspberry Pi 4. If the SD card corrupts, the power supply fails, or the Pi overheats, BigClaw goes dark.
- **Impact:** If BigClaw goes down during a market crash, trailing stops don't execute, circuit breakers don't fire, and positions are unmanaged during the highest-risk period.
- **Fix:** (a) Nightly backup of all state, configs, and IPS to cloud (GitHub private repo or S3). (b) Set Alpaca server-side stop-loss orders as a dead-man's switch — these execute even if BigClaw is offline. (c) Uptime Kuma already monitors — add auto-restart script and escalation to phone call (Twilio) if down >5 minutes during market hours.
- **Priority:** **HIGH** | **Effort:** 3-5 Days

### 6.5 — No Automated Signal Weighting Optimization
- **Current State:** IPS defines signal weights, presumably set manually during the multi-model debate.
- **Impact:** Static weights degrade as market regimes change. A weight that was optimal in 2024 may be suboptimal in 2025.
- **Fix:** Monthly automated walk-forward optimization: using the last 6 months of signal scores and actual returns, run ridge regression to find optimal weights. Compare to current weights. If improvement > 0.5% annualized Sharpe, propose new weights for human approval (don't auto-deploy — keep human in the loop for weight changes).
- **Priority:** **MEDIUM** | **Effort:** 1-2 Weeks

### 6.6 — No Weekend Infrastructure Maintenance Window
- **Current State:** Saturday screener runs, but no evidence of automated system maintenance.
- **Fix:** Sunday 2-6 AM: automated database vacuum, log rotation, dependency updates (`pip` security patches), SD card health check, memory/CPU trending analysis. Generate Monday morning "system health" report alongside market report.
- **Priority:** **MEDIUM** | **Effort:** 1 Day

---

## 7. IMPLEMENTATION ROADMAP

Ordered by **Impact/Effort ratio** (highest first). Each phase builds on the previous.

---

### PHASE 1: "STOP THE BLEEDING" (Weeks 1-2)
*Focus: Prevent catastrophic losses before pursuing alpha*

| # | Item | Gap Ref | Effort | Impact |
|---|---|---|---|---|
| 1 | **FRED API integration** | 5.1 | 4 hours | Unlocks macro regime detection — foundation for everything |
| 2 | **Liquidity screener gate** | 4.4 | 1 day | Eliminates illiquid traps immediately |
| 3 | **Data quality validation layer** | 6.3 | 2-3 days | Prevents false signals from bad data |
| 4 | **Portfolio-level circuit breaker** | 2.4 | 3-5 days | Prevents catastrophic drawdowns |
| 5 | **Pre-trade IPS compliance enforcement** | 6.1 | 3-5 days | Real-time rule enforcement vs. weekly audit |
| 6 | **Disaster recovery + server-side stops** | 6.4 | 3-5 days | BigClaw survives hardware failure |

**Phase 1 Outcome:** BigClaw cannot blow up. Estimated risk reduction: **40-60% reduction in tail risk.**

---

### PHASE 2: "KNOW YOUR EDGE" (Weeks 3-4)
*Focus: Measure performance accurately, understand what's working*

| # | Item | Gap Ref | Effort | Impact |
|---|---|---|---|---|
| 7 | **Performance attribution vs. benchmarks** | 4.6 | 1 week | Answer: "Is BigClaw actually adding alpha?" |
| 8 | **Transaction cost model** | 2.6 | 3-5 days | Eliminate negative-EV trades |
| 9 | **Alpha decay tracker** | 4.3 | 1 week | Detect dying signals before they cost money |
| 10 | **Skill deduplication** (merge redundant skills) | §3 | 1 week | Reduce maintenance, clarify signal flow |
| 11 | **Earnings calendar integration** | 5.3 | 4 hours | Foundation for earnings risk management |

**Phase 2 Outcome:** BigClaw knows exactly what's working, what's not, and what it costs. Estimated improvement: **2-4% annual return from eliminating false signals and hidden costs.**

---

### PHASE 3: "PORTFOLIO INTELLIGENCE" (Weeks 5-7)
*Focus: Move from stock-picking to portfolio construction*

| # | Item | Gap Ref | Effort | Impact |
|---|---|---|---|---|
| 12 | **Correlation-aware portfolio construction** | 2.2 | 1 week | Diversification = free Sharpe improvement |
| 13 | **Regime-driven allocation controller** | 2.3 | 1-2 weeks | Dynamic cash allocation based on macro |
| 14 | **Macro factor monitor** (uses FRED from Phase 1) | 4.2 | 1 week | Feed regime controller with real data |
| 15 | **Automated rebalancing** | 6.2 | 3-5 days | Maintain target risk profile |
| 16 | **Earnings event risk manager** | 4.1 | 3-5 days | Pre-earnings position management |

**Phase 3 Outcome:** BigClaw thinks in portfolios, not stocks. Estimated improvement: **30-50% reduction in portfolio volatility at similar return levels (Sharpe improvement of 0.3-0.5).**

---

### PHASE 4: "GO LIVE" (Weeks 8-10)
*Focus: Deploy real capital with full safeguards*

| # | Item | Gap Ref | Effort | Impact |
|---|---|---|---|---|
| 17 | **Live execution engine** (1 portfolio, minimum size) | 2.1 | 1-2 weeks | Real P&L, real validation |
| 18 | **Order execution optimizer** (limit orders, TWAP) | 4.7 | 3-5 days | Reduce execution costs 30-50% |
| 19 | **Slippage tracking & reporting** | 2.1 | 3 days | Measure paper-to-live degradation |

**Phase 4 Outcome:** BigClaw manages real money with full audit trail. Estimated impact: **Validates entire system with real capital. Execution optimization saves 0.3-0.8% annually.**

---

### PHASE 5: "ADVANCED ALPHA" (Weeks 11-16)
*Focus: New alpha sources and optimization*

| # | Item | Gap Ref | Effort | Impact |
|---|---|---|---|---|
| 20 | **Options Greeks engine** | 2.5 | 1-2 weeks | Systematic options management |
| 21 | **Tax-loss harvesting automation** | 4.5 | 1-2 weeks | 0.5-1.5% annual after-tax alpha |
| 22 | **Automated signal weight optimization** | 6.5 | 1-2 weeks | Adaptive scoring improvement |
| 23 | **Short interest data integration** | 5.5 | 3 days | New signal source |
| 24 | **Fund flow data integration** | 5.4 | 3 days | Sector rotation signal |
| 25 | **Insider transaction enrichment** | 5.6 | 1 week | Higher-quality insider signal |
| 26 | **Sunday maintenance automation** | 6.6 | 1 day | System longevity |

**Phase 5 Outcome:** BigClaw has institutional-grade capabilities on retail hardware. Estimated cumulative improvement: **3-6% additional annual return, 50%+ risk reduction vs. current state.**

---

## SUMMARY SCORECARD

| Metric | Current State | After Full Roadmap | Delta |
|---|---|---|---|
| **Tail Risk Protection** | Individual trailing stops only | Circuit breakers + regime allocation + correlation limits + earnings management | **~60% reduction in max drawdown** |
| **Alpha Measurement** | None (no benchmark comparison) | Full attribution, decay tracking, cost modeling | **Know true alpha for first time** |
| **Execution Quality** | Paper only, no cost model | Live with slippage tracking, limit orders, TWAP | **0.5-2% annual cost savings** |
| **Signal Quality** | 20 dimensions, static weights | Decay-tracked, auto-optimized, deduplicated | **2-4% annual improvement** |
| **Tax Efficiency** | Planning skill exists, no automation | Automated TLH | **0.5-1.5% annual after-tax** |
| **System Resilience** | Single Pi, no failover | Cloud backup, server-side stops, auto-restart | **99.5% → 99.95% uptime** |
| **Skills Count** | 27 (with redundancy) | ~24 (deduplicated) + 8 new = ~32 focused skills | **Net: fewer, better skills** |

---

**Bottom line:** BigClaw's architecture is genuinely impressive — the IPS framework, multi-signal fusion, and self-improvement loop are institutional concepts running on a $75 computer. The critical path is: **protect against catastrophic loss first (Phase 1), measure accurately second (Phase 2), then build portfolio intelligence (Phase 3) before deploying real capital (Phase 4).** Do not skip to Phase 4. The graveyard of algorithmic trading is full of systems that went live before they could measure their own edge.

---

### Grok 4.20 Beta

**1) STRENGTHS**

BigClaw is already one of the most sophisticated open-source autonomous investment agents in existence. Key strengths:

- 27 specialized OpenClaw skills giving broad coverage across fundamental, technical, sentiment, on-chain, regulatory, and portfolio domains.
- Production-grade automation: autonomous daily trading on 7 Alpaca paper portfolios, 15-minute trailing stops, 5x daily price refresh, Saturday screener, morning/afternoon reports.
- Strong compliance foundation: 7 multi-model Investment Policy Statements with explicit gate rules, reject rules, audit rules, signal weights, and yfinance mappings.
- Real-time edge: TSLA watchdog + options flow, Unusual Whales dark pool, X sentiment tracker, ARK ITK tracking.
- Self-improvement loop (self-improve + skill-vetting) and infrastructure maturity (Raspberry Pi 4, GitHub Pages, Slack+Discord, network security).
- 20-dimension scoring engine + style gates providing structured decision making.

**2) CRITICAL GAPS (impact on returns/risk)**

| Gap | Why It Matters (Return/Risk Impact) | Priority | Effort |
|-----|-------------------------------------|----------|--------|
| **No live execution with position sizing & real risk limits** | Currently only paper trading. Missing Kelly/fractional Kelly, volatility targeting, and dynamic leverage control. **Directly caps returns at 0% real P&L and creates false confidence.** | Critical | Weeks |
| **Missing macroeconomic regime filter & tactical asset allocation** | No integration of yield curve, inflation breakevens, DXY, credit spreads, or global risk appetite. Major driver of 70-80% of portfolio variance in drawdowns. | Critical | Days |
| **No formal drawdown control or portfolio heat management** | 20-dim scoring lacks explicit portfolio-level risk overlay (max drawdown, sector concentration, factor crowding). **Primary cause of catastrophic loss in live trading.** | Critical | Days |
| **No options Greeks / volatility surface awareness** | Options-strategy-advisor exists but lacks real-time implied vol rank, skew, term structure, and vanna/charm. Critical for options returns and hedging. | Critical | Weeks |
| **No trade execution journaling + post-trade analytics** | Cannot measure edge decay, slippage, or rule violations. Prevents systematic alpha improvement. | Critical | Days |

**3) SKILL REDUNDANCIES**

- `fundamental-stock-analysis` + `stock-evaluator` + `intellectia-stock-forecast` → heavy overlap. Consolidate into single `multi-factor-equity-analyst`.
- `backtest-expert` + `stock-strategy-backtester` → merge.
- `afrexai-portfolio-risk` + `portfolio-manager` + `afrexai-esg-reporting` + `afrexai-tax-planning` → should be sub-skills under unified `portfolio-orchestrator`.
- `yahoo-finance` + `time-series-analysis` + `python-dataviz` → largely redundant with modern data stack.

**4) NEW CAPABILITIES NEEDED (as new OpenClaw skills)**

1. **macro-regime-detector** – yield curve, inflation, liquidity, risk-on/risk-off signals.
2. **portfolio-heat-manager** – dynamic position sizing, Kelly, volatility targeting, concentration limits.
3. **options-greeks-vol-surface** – real-time vol analytics and options flow interpretation.
4. **trade-journal-post-mortem** – automated trade review, edge tracking, rule violation detection.
5. **factor-crowding-detector** – identify when value/momentum/quality becomes crowded.
6. **cross-asset-correlation-monitor** – real-time correlation breakdown detection.
7. **tax-loss-harvester** – automated tax optimization engine.
8. **execution-algorithm** – smart order routing, VWAP/TWAP, dark pool access simulation.

**5) DATA SOURCE GAPS**

- Missing high-quality options chain + Greeks (need CBOE, OptionMetrics, or Polygon.io full options).
- No reliable institutional order flow / 13F flow beyond Unusual Whales (need Quandl, Bloomberg, or Estimize).
- No Treasury yield curve, inflation swaps, or breakeven data (need FRED + Quandl).
- No short interest flow or borrow rate data.
- No high-frequency sentiment beyond X (need NewsAPI + RavenPack or proprietary NLP).
- No earnings transcript sentiment or guidance quantification.

**6) AUTOMATION GAPS**

- No nightly Monte Carlo / stress testing of entire portfolio.
- No automated rebalancing engine with transaction cost awareness.
- No circuit breakers on runaway strategies or model disagreement.
- No versioned strategy code with git-triggered backtests on new signals.
- No formal A/B testing framework for new alphas.
- No automated quarterly IPS compliance certification with human escalation.

**7) IMPLEMENTATION ROADMAP** (Highest impact / lowest effort first)

**Phase 0 – Critical Foundations (2–3 weeks total)**

1. **portfolio-heat-manager** (Priority: Critical, Effort: 5 Days)  
   Impact: Prevents blow-ups, enables proper risk-adjusted returns.  
   Implement dynamic Kelly, volatility targeting, max sector/factor exposure, and portfolio-level drawdown gates. Integrate with existing 7 IPS.

2. **macro-regime-detector** (Priority: Critical, Effort: 4 Days)  
   Impact: Avoids 2008/2022-style drawdowns. Can improve Sharpe by 0.4–0.8.  
   Pull FRED + yield curve data, classify 6 regimes, create regime overlay that vetoes or tilts existing signals.

3. **trade-journal-post-mortem + execution logging** (Priority: Critical, Effort: 3 Days)  
   Impact: Turns paper trading into genuine learning system. Required before going live.

**Phase 1 – Risk & Options Mastery (3–4 weeks)**

4. **options-greeks-vol-surface** (Priority: Critical, Effort: 8 Days)  
   Impact: Unlocks superior options income and hedging strategies.

5. **Live execution bridge with real risk limits** (Priority: Critical, Effort: 10 Days)  
   Move at least one portfolio from paper to small live with strict heat limits.

**Phase 2 – Alpha & Efficiency (4–6 weeks)**

6. Consolidate redundant skills into `multi-factor-equity-analyst` and `portfolio-orchestrator`.
7. Add `factor-crowding-detector` and `cross-asset-correlation-monitor`.
8. Build nightly Monte Carlo + stress test automation.
9. Implement tax-loss-harvester.

**Phase 3 – Institutional Grade (Ongoing)**

- Add premium data sources (Polygon, OptionMetrics, RavenPack).
- Build formal A/B testing and strategy versioning.
- Quarterly automated IPS compliance report with multi-model audit.

**Immediate Recommendation (Next 7 days):**

Focus exclusively on building **portfolio-heat-manager** and **macro-regime-detector**. These two capabilities will have the highest return/risk impact of anything on the roadmap and will make all existing 27 skills significantly more effective and safer.

Once these are complete, BigClaw will transition from "very impressive research bot" to "institutional-grade autonomous investment system."

---

### Gemini 3.1 Pro

As a Senior Investment Technology Architect, I have reviewed BigClaw’s architecture, skill stack, and recent IPS milestone. 

BigClaw has evolved from a basic script into a sophisticated quantamental orchestration engine. However, running a 27-skill, 7-portfolio autonomous system on a Raspberry Pi 4 with mismatched data frequencies and redundant LLM skills introduces severe execution and operational risks.

Here is the architectural assessment and upgrade plan to elevate BigClaw to a Master Investor Bot.

---

### 1. STRENGTHS (The Foundation)
*   **Institutional-Grade Framework:** The recent multi-model IPS debate with strict gate/reject/audit rules is a massive differentiator. Most retail bots lack a formalized Investment Policy Statement.
*   **Alpha Diversity:** Combining Unusual Whales (dark pools/options flow), OpenInsider, and SEC filings provides a robust, multi-factor alpha generation engine.
*   **Autonomous Lifecycle:** End-to-end automation from Saturday screening to daily trading and AM/PM reporting shows excellent orchestration.
*   **Risk Awareness:** Implementing 15-minute trailing stops, weekly compliance audits, and a dedicated TSLA watchdog demonstrates a strong defensive posture.

---

### 2. CRITICAL GAPS (Architectural & Logic Flaws)

**Gap 2.1: The Data Frequency vs. Execution Mismatch**
*   **The Gap:** You have 15-minute trailing stops, but only a 5x daily price refresh. The bot is blind between those 5 refreshes.
*   **Why it matters:** A flash crash or sudden intraday reversal will blow past your stop-loss because the bot won't see the price drop until hours later.
*   **Return/Risk Impact:** **Catastrophic Risk.** Unmanaged downside exposure could result in max drawdowns exceeding 20% in volatile regimes.
*   **How to implement:** Implement a lightweight WebSocket connection to Alpaca’s real-time data stream specifically for the trailing stop logic, bypassing the heavy 5x daily full-portfolio refresh.
*   **Priority:** Critical | **Effort:** Days

**Gap 2.2: Compute Bottleneck (Raspberry Pi 4)**
*   **The Gap:** A Pi 4 (max 8GB RAM, weak ARM CPU) cannot efficiently handle 20-dimension scoring across hundreds of candidates, backtesting, and concurrent API calls without thermal throttling or memory faults.
*   **Why it matters:** Memory crashes during trading hours leave positions unmanaged. High latency in signal processing causes execution slippage.
*   **Return/Risk Impact:** **-1.5% to -3.0% Return Drag annually** due to missed execution windows and system downtime risk.
*   **How to implement:** Keep the Pi 4 as the *Orchestrator* (cron jobs, API routing, Slack alerts), but offload heavy Pandas/NumPy data crunching and backtesting to AWS Lambda or a cheap DigitalOcean droplet via API.
*   **Priority:** High | **Effort:** Weeks

**Gap 2.3: Pre-Trade Compliance vs. Post-Trade Audit**
*   **The Gap:** Compliance audit is weekly, but trading is daily. 
*   **Why it matters:** If the bot hallucinates or a signal misfires on Monday, it trades outside the IPS until the Sunday audit catches it.
*   **Return/Risk Impact:** **High Risk.** Style drift or over-concentration can violate portfolio volatility targets, increasing tail risk.
*   **How to implement:** Convert the IPS gate/reject rules into hardcoded Python logic (not LLM prompts) that runs *milliseconds before* the Alpaca order execution API call.
*   **Priority:** Critical | **Effort:** Days

---

### 3. SKILL REDUNDANCIES (Consolidation for Speed & Cost)

LLM skill bloat increases token costs, latency, and the probability of agent hallucination. 

*   **Consolidate Backtesting:** `backtest-expert`, `stock-strategy-backtester`, and `time-series-analysis` should be merged into one **`quant-engine`** skill. *Impact: Faster execution, lower API costs.*
*   **Consolidate Fundamentals:** `fundamental-stock-analysis`, `stock-evaluator`, and `sector-analyst` overlap heavily. Merge into **`fundamental-scorer`** mapped directly to your 20-dimension engine. *Impact: Eliminates conflicting LLM outputs.*
*   **Consolidate Portfolio Management:** `portfolio-manager`, `afrexai-portfolio-risk`, `financial-planning`, and `afrexai-tax-planning`. Drop financial/tax planning (irrelevant for paper/Alpaca trading) and merge the rest into **`risk-manager`**. *Impact: Streamlines position sizing.*

---

### 4. NEW CAPABILITIES NEEDED

**Capability 4.1: Volatility-Adjusted Position Sizing (Target Vol)**
*   **The Gap:** Currently relying on static weights or basic portfolio management.
*   **Why it matters:** Equal weighting a low-vol utility stock and a high-vol tech stock creates massive risk imbalances.
*   **How to implement:** Use ATR (Average True Range) or 30-day historical volatility to size positions. (e.g., Risk exactly 1% of portfolio equity per trade based on the distance to the trailing stop).
*   **Return/Risk Impact:** **+2% to +4% Return / -15% Drawdown.** Maximizes compounding by preventing single-stock blowups.
*   **Priority:** High | **Effort:** Days

**Capability 4.2: Smart Execution Algorithms (TWAP/VWAP)**
*   **The Gap:** Autonomous daily trading likely uses basic Market or Limit orders.
*   **Why it matters:** Crossing the spread or executing large orders at the open/close results in poor fill prices.
*   **How to implement:** Build an execution module that slices orders into smaller chunks and executes them over a 2-hour window using Time-Weighted Average Price (TWAP).
*   **Return/Risk Impact:** **+0.5% to +1.0% Return annually** by capturing the spread and reducing slippage.
*   **Priority:** Medium | **Effort:** Weeks

**Capability 4.3: Regime Switching**
*   **The Gap:** The bot trades its strategies regardless of the macro environment.
*   **Why it matters:** Trend-following fails in choppy markets; mean-reversion fails in strong trends.
*   **How to implement:** Add a `macro-regime` skill that checks SPY moving averages (e.g., 50 vs 200 DMA) and VIX levels to toggle IPS strategies between "Aggressive," "Defensive," and "Cash."
*   **Return/Risk Impact:** **Major Risk Reduction.** Prevents the bot from buying dips in a structural bear market.
*   **Priority:** High | **Effort:** Days

---

### 5. DATA SOURCE GAPS

**Gap 5.1: yfinance Dependency**
*   **The Gap:** yfinance is rate-limited, prone to breaking, and lacks survivorship-bias-free historical data.
*   **Why it matters:** Missing data fields will break your 20-dimension scoring engine.
*   **How to implement:** Migrate core pricing and fundamental data to **Polygon.io** (cheap, institutional grade) or **Financial Modeling Prep (FMP)**.
*   **Return/Risk Impact:** **Operational Risk Mitigation.** Ensures 99.99% uptime for the scoring engine, preventing missed alpha.
*   **Priority:** High | **Effort:** Days

**Gap 5.2: Lack of Implied Volatility (IV) Data**
*   **The Gap:** You track options flow (Unusual Whales) but lack raw IV rank/percentile data.
*   **Why it matters:** Buying breakouts in high IV environments is a negative expected value (EV) trade due to volatility crush.
*   **How to implement:** Integrate an IV data feed (via Polygon or CBOE) to act as a filter in your IPS reject rules.
*   **Return/Risk Impact:** **+1% to +2% Return.** Avoids buying overpriced assets.
*   **Priority:** Medium | **Effort:** Weeks

---

### 6. AUTOMATION GAPS

**Gap 6.1: State Recovery & Error Handling**
*   **The Gap:** If the Pi 4 loses power or internet during the daily trading window, what happens?
*   **Why it matters:** The bot might execute a buy order, crash, and fail to place the associated trailing stop.
*   **How to implement:** Implement a SQLite database to track "Trade State" (Pending, Executed, Stop Placed). On reboot, the bot checks Alpaca against SQLite and reconciles missing stops immediately.
*   **Return/Risk Impact:** **Catastrophic Risk Mitigation.** Prevents naked exposure.
*   **Priority:** Critical | **Effort:** Weeks

---

### 7. IMPLEMENTATION ROADMAP

Execute this roadmap based on the highest Return/Risk impact for the lowest effort.

#### Phase 1: The "Stop the Bleeding" Fixes (Weeks 1-2)
*   **Task 1:** Fix the 15m stop vs. 5x refresh mismatch. Implement Alpaca WebSockets for live stop-loss monitoring. *(Critical / Days)*
*   **Task 2:** Hardcode IPS Gate/Reject rules as pre-trade Python logic, removing reliance on LLMs for execution compliance. *(Critical / Days)*
*   **Task 3:** Prune the 27 skills down to ~15 core skills to reduce token latency and Pi 4 memory load. *(High / Hours)*

#### Phase 2: Institutional Upgrades (Weeks 3-5)
*   **Task 4:** Replace `yfinance` with Polygon.io or FMP for reliable 20-dimension scoring. *(High / Days)*
*   **Task 5:** Implement Volatility-Adjusted Position Sizing (ATR-based). *(High / Days)*
*   **Task 6:** Build the SQLite State Recovery system for crash reconciliation. *(Critical / Weeks)*

#### Phase 3: Master Level Alpha (Weeks 6-8)
*   **Task 7:** Implement Macro Regime Switching (VIX/Trend filters) to dynamically adjust portfolio exposure. *(High / Days)*
*   **Task 8:** Offload heavy backtesting/scoring compute to the cloud (AWS/GCP), leaving the Pi 4 as a pure orchestrator. *(Medium / Weeks)*
*   **Task 9:** Implement TWAP execution algorithms to reduce slippage. *(Medium / Weeks)*

By executing this roadmap, BigClaw will transition from a highly capable hobbyist project into a resilient, institutional-grade autonomous trading system capable of managing real capital.

---

### GPT-5.4

Below is a practical architecture assessment of **BigClaw** as an “investor bot” and what it needs to become a more robust **master investor bot**.

I’m assuming current scope is primarily **US equities/options idea generation + autonomous paper execution**, with some portfolio/risk/tax/ESG overlays.

---

# 1) STRENGTHS

BigClaw already has a better foundation than most retail-investor bots because it has breadth across **signal generation, compliance, portfolio ops, reporting, and autonomous execution**.

## A. Strong signal breadth
**What exists**
- Market data: `yahoo-finance`, `finance-news`
- Fundamental analysis: `fundamental-stock-analysis`, `stock-evaluator`
- Macro/regime/context: `market-environment-analysis`, `us-market-bubble-detector`, `sector-analyst`
- Sentiment/alternative data: `realtime-x-sentiment-tracker`, `institutional-flow-tracker`, `openinsider`, `sec-watcher`, `onchain`
- Derivatives-aware tools: `options-strategy-advisor`, TSLA watchdog, Unusual Whales dark pool integration
- Forecasting/backtesting: `intellectia-stock-forecast`, `backtest-expert`, `stock-strategy-backtester`, `time-series-analysis`

**Why this matters**
- Multi-factor signal diversity can improve **risk-adjusted returns** versus single-source strategies.
- Reduces dependence on one market regime or one data type.

**Return/risk impact**
- Positive expected impact on **signal breadth and idea generation hit rate**
- Can reduce **single-factor blowups** and regime-specific underperformance

---

## B. Portfolio process is more mature than typical bots
**What exists**
- 7 paper portfolios on Alpaca
- 20-dimension scoring engine
- Style gates
- 7 Investment Policy Statements (IPS)
- Detailed reject rules, audit rules, signal weights, yfinance field mappings
- Portfolio/risk/tax/ESG capabilities: `portfolio-manager`, `afrexai-portfolio-risk`, `afrexai-tax-planning`, `afrexai-esg-reporting`, `financial-planning`

**Why this matters**
- Most bots fail from poor process, not lack of ideas.
- IPS-driven governance can materially reduce **behavioral drift**, **signal contamination**, and **style creep**.

**Return/risk impact**
- Better process discipline can improve **consistency of returns**
- Lower risk of **uncontrolled drawdowns due to changing rules midstream**

---

## C. Automation and observability are already present
**What exists**
- Autonomous daily trading
- Trailing stops every 15 min
- Saturday candidate screener
- 5x daily price refresh
- Morning/afternoon reports
- Weekly compliance audit
- Weekly research
- Slack + Discord delivery
- GitHub Pages dashboard
- `uptime-kuma`, `log-analyzer`, `self-improve`, `skill-vetting`

**Why this matters**
- Reliability and monitoring are essential for moving from “toy agent” to “real operator.”
- Most investor bots die from stale data, silent failures, and weak execution visibility.

**Return/risk impact**
- Reduces operational risk
- Improves ability to catch signal failures before they create losses

---

## D. Good early compliance and audit posture
**What exists**
- Weekly compliance audit
- IPS framework
- Reject rules and audit rules
- SEC watcher / insider tracking

**Why this matters**
- Auditability is crucial if BigClaw scales from personal experimentation to real capital deployment.
- Helps avoid accidental violations of your own mandate.

**Return/risk impact**
- Lowers governance and execution-risk errors
- Supports long-term scalability without “strategy drift”

---

# 2) CRITICAL GAPS

These are the highest-value deficiencies preventing BigClaw from becoming a true “master investor bot.”

---

## Gap 1: No institutional-grade **position sizing / portfolio construction engine**
**Current gap**
You have scoring, style gates, and portfolio management, but there is no evidence of:
- volatility targeting
- correlation-aware sizing
- marginal risk contribution limits
- factor exposure constraints
- Kelly/half-Kelly variants
- drawdown-based de-risking
- convexity-aware options sizing
- liquidity-aware max position sizing

**Why it matters**
A good signal can still produce bad returns if sizing is poor. In real investing, **portfolio construction contributes as much as signal quality** to outcomes.

**Impact on returns/risk**
- Likely the single biggest improvement area for **Sharpe ratio**
- Can materially reduce **drawdowns**, **concentration risk**, and **correlation blowups**
- Better sizing often increases return per unit of risk more than adding one more signal source

**How to implement**
Build a dedicated **Portfolio Construction & Risk Budgeting service**:
1. Compute daily:
   - realized vol (20d/60d)
   - correlation matrix
   - beta to SPY/QQQ
   - sector/industry exposures
   - factor exposures (value, momentum, size, quality if possible)
2. Add position sizing rules:
   - max single-name exposure
   - max sector exposure
   - max theme exposure
   - max expected loss per position
   - liquidity cap (% of average daily dollar volume)
3. Use ranking score only for **selection**, not direct sizing
4. Size positions via:
   - inverse-vol weighting
   - risk parity by sleeve
   - capped conviction overlay
5. Add portfolio-level kill-switches:
   - if rolling drawdown > X%, cut gross/net exposure
   - if correlation spikes, reduce crowded exposure
6. Options:
   - cap premium at risk
   - define max portfolio vega/theta/gamma buckets

**Priority**
**Critical**

**Effort**
**1–2 Weeks**

---

## Gap 2: No robust **transaction cost, slippage, and liquidity model**
**Current gap**
Paper trading often overstates edge if execution assumptions are naive. You have autonomous daily trading and stops, but no indication of:
- spread-aware execution
- slippage by liquidity regime
- partial fill handling
- auction/open-close impact assumptions
- cost-adjusted backtesting
- dark pool signal decay timing

**Why it matters**
Strategies that look profitable before costs often fail after realistic fills. This is especially true for:
- sentiment-driven trades
- small/mid-cap ideas
- options trades
- frequent stop updates

**Impact on returns/risk**
- Direct impact on **realized returns**
- Can prevent deployment of negative-alpha strategies that only “work on paper”
- Reduces hidden implementation shortfall

**How to implement**
1. Extend backtest engine with:
   - fixed commissions/fees
   - bid/ask spread estimate
   - slippage as function of ADV, volatility, price, and time of day
2. Add execution simulation:
   - market, limit, stop, stop-limit outcomes
   - open-gap behavior
   - partial fills
3. Add live execution policies:
   - no market orders in thin names
   - max participation rate (e.g. <2–5% of ADV)
   - no entries near illiquid premarket spikes unless strategy explicitly allows
4. Track:
   - expected vs realized fill price
   - alpha decay from signal timestamp to execution timestamp

**Priority**
**Critical**

**Effort**
**1–2 Weeks**

---

## Gap 3: No explicit **regime detection and strategy switching framework**
**Current gap**
You have market environment and bubble detectors, but no evidence that portfolio behavior changes systematically by regime.

**Why it matters**
Different strategies work in different regimes:
- momentum in trending markets
- mean reversion in choppy regimes
- quality/low-vol in risk-off periods
- options flow can be less reliable in panic volatility spikes

Without regime-aware switching, BigClaw may force the wrong playbook.

**Impact on returns/risk**
- Can materially improve **drawdown control**
- Reduces performance decay during adverse environments
- Likely boosts **consistency** more than raw upside

**How to implement**
Create a **Regime Controller** that classifies daily market state:
- trend: up / down / sideways
- vol: low / medium / high
- breadth: strong / weak
- macro stress: normal / elevated
- liquidity: healthy / strained

Inputs:
- VIX term structure
- realized vol
- SPY/QQQ trend
- breadth (% above 50dma/200dma)
- credit spreads if available
- sector leadership concentration

Then map each regime to:
- allowed strategy set
- max gross exposure
- stop width
- rebalance cadence
- min score threshold for entry

**Priority**
**Critical**

**Effort**
**4–7 Days**

---

## Gap 4: Weak evidence of **factor attribution and post-trade learning**
**Current gap**
You have weekly research and audits, but no explicit performance attribution framework answering:
- Why did this trade work?
- Which signals are genuinely additive?
- Which IPS is strongest net of costs?
- Which factor exposures drove gains/losses?

**Why it matters**
Without attribution, self-improvement becomes anecdotal. A master investor bot must know the source of edge and the source of losses.

**Impact on returns/risk**
- Improves signal weight calibration
- Helps prune non-contributing or harmful signals
- Can improve long-term alpha persistence and reduce model drift

**How to implement**
Add a **Performance Attribution & Learning layer**:
1. For each trade/store:
   - signal vector at entry
   - regime state
   - liquidity metrics
   - execution quality
   - P&L path
2. Run weekly analyses:
   - by strategy
   - by regime
   - by sector
   - by signal decile
   - by hold duration
3. Compute:
   - hit rate
   - avg win/loss
   - expectancy
   - cost-adjusted alpha
   - contribution by signal family
4. Reweight signals only if statistically supported

**Priority**
**Critical**

**Effort**
**1 Week**

---

## Gap 5: Insufficient **data quality, survivorship, and point-in-time controls**
**Current gap**
A lot seems to depend on yfinance mappings and mixed retail/open sources. These are useful, but they are not enough for a serious investor bot if you care about research validity.

Likely issues:
- survivorship bias
- lookahead bias
- stale fundamentals
- restatement handling gaps
- corporate action inconsistencies
- symbol mapping changes
- alternative data timestamp mismatch

**Why it matters**
Bad data creates fake alpha. This is one of the largest silent failure modes in investment systems.

**Impact on returns/risk**
- Prevents overestimation of returns in backtests
- Reduces false confidence and bad capital deployment
- Protects against “phantom alpha” from incorrect historical data

**How to implement**
1. Create a **Data Validation Pipeline**
   - schema checks
   - freshness checks
   - outlier checks
   - cross-source reconciliation
2. Store point-in-time snapshots of:
   - prices
   - fundamentals
   - scores
   - candidate lists
3. Track data lineage:
   - source
   - fetch timestamp
   - market timestamp
   - transformation version
4. Add survivorship-bias-safe universe snapshots if possible

**Priority**
**Critical**

**Effort**
**2–3 Weeks**

---

## Gap 6: No proper **risk stress testing / scenario engine**
**Current gap**
Current risk appears operational and portfolio-summary oriented, but not scenario-based.

Missing:
- 1987-style gap test
- 2008 risk-off spread widening
- 2020 volatility shock
- 2022 duration/factor rotation shock
- single-stock overnight gap scenarios
- options greeks shock scenarios

**Why it matters**
Trailing stops every 15 minutes do not protect against overnight gaps, halts, or event shocks.

**Impact on returns/risk**
- Major reduction in tail-risk blindness
- Helps define safer max exposure and stop assumptions
- Can prevent catastrophic drawdowns

**How to implement**
Build a **Scenario Stress Engine**:
- historical replay stress tests
- factor shock tests
- liquidity haircut tests
- overnight gap distributions by stock/sector
- options greek shock simulation

Outputs:
- expected portfolio drawdown under scenarios
- top risk contributors
- positions violating risk budget

**Priority**
**Critical**

**Effort**
**1–2 Weeks**

---

## Gap 7: No event-driven earnings / catalyst risk framework
**Current gap**
You have SEC watcher and insider flow, but no explicit mention of earnings-event handling.

**Why it matters**
Earnings and macro events dominate single-name risk. Many equity strategies break if they accidentally hold into earnings without deliberate rules.

**Impact on returns/risk**
- Large reduction in avoidable gap risk
- Better separation of “fundamental swing” vs “event gamble”
- Can materially improve win/loss distribution

**How to implement**
1. Build a **Catalyst Calendar**
   - earnings dates
   - guidance dates
   - CPI/FOMC/NFP
   - product launches / investor days if available
2. Add IPS rules:
   - no new positions within X days of earnings unless earnings strategy
   - mandatory size reductions before event
   - event-specific stop logic
3. Distinguish:
   - event-driven strategies
   - non-event strategies

**Priority**
**High**

**Effort**
**3–5 Days**

---

# 3) SKILL REDUNDANCIES

These are not necessarily bad, but they should be consolidated to reduce complexity and conflicting outputs.

---

## Redundancy 1: `fundamental-stock-analysis` vs `stock-evaluator`
**Gap**
Likely overlap in valuation, quality, growth, profitability, and balance sheet assessment.

**Why it matters**
Duplicate factor generation can overweight one concept unintentionally and create correlated scores.

**Implementation**
- Define one as **raw factor extractor**
- Define the other as **policy-aware evaluator**
- Centralize factor definitions in one shared schema

**Priority**
**High**

**Effort**
**1–2 Days**

**Return/risk impact**
- Reduces double-counting risk
- Improves signal clarity and more stable rankings

---

## Redundancy 2: `backtest-expert` vs `stock-strategy-backtester`
**Gap**
Potential duplication in simulation logic.

**Why it matters**
If two engines produce different assumptions, you get governance confusion and false confidence.

**Implementation**
- One engine = canonical simulation core
- Other = experiment orchestration / parameter sweeps
- Shared cost model and data assumptions

**Priority**
**High**

**Effort**
**2–3 Days**

**Return/risk impact**
- Prevents model-selection errors
- Improves trust in research and deployment decisions

---

## Redundancy 3: `market-environment-analysis` vs `us-market-bubble-detector`
**Gap**
Both likely attempt macro-state assessment.

**Why it matters**
Can create inconsistent regime labels.

**Implementation**
- Merge into one **Market Regime & Valuation Risk service**
- Bubble detector becomes a sub-score, not a standalone decision-maker

**Priority**
**Medium**

**Effort**
**1–2 Days**

**Return/risk impact**
- Cleaner regime handling
- Lower chance of contradictory portfolio actions

---

## Redundancy 4: `portfolio-manager` vs `afrexai-portfolio-risk` vs `financial-planning`
**Gap**
Different layers may overlap around allocations, risk, and long-term goals.

**Why it matters**
Unclear authority causes action conflicts.

**Implementation**
Define layers:
- `financial-planning`: investor objectives/constraints
- `portfolio-manager`: target allocation and rebalance logic
- `afrexai-portfolio-risk`: constraints, stress testing, risk budget enforcement

**Priority**
**High**

**Effort**
**2 Days**

**Return/risk impact**
- Better alignment between goals and execution
- Lower portfolio construction errors

---

## Redundancy 5: `finance-news` and `sec-watcher` and `openinsider`
**Gap**
All are event feeds but likely with separate pipelines.

**Why it matters**
Event deduplication and timing consistency matter.

**Implementation**
Create a unified **Event Bus** with event type taxonomy:
- filing
- insider transaction
- news headline
- social sentiment spike
- options flow anomaly

**Priority**
**Medium**

**Effort**
**2–4 Days**

**Return/risk impact**
- Faster signal fusion
- Less noise and duplicate triggers

---

# 4) NEW CAPABILITIES NEEDED

These are the most important additions beyond gap-fixing.

---

## Capability 1: Master Decision Engine / Ensemble Governor
**Gap**
You have many skills, but no evidence of a single orchestrator deciding which signal wins when they conflict.

**Why it matters**
A master bot needs not just many tools, but a **decision hierarchy**.

**Implementation**
Build a weighted ensemble with 4 layers:
1. Universe filter
2. Signal ensemble
3. Regime overlay
4. Risk/execution veto layer

Decision output:
- Buy / Hold / Sell / Avoid
- Position size
- confidence score
- rationale trace

**Priority**
**Critical**

**Effort**
**1–2 Weeks**

**Return/risk impact**
- Improves consistency
- Reduces contradictory trades
- Better alpha retention through coordinated decision-making

---

## Capability 2: Factor model + exposure control
**Gap**
No explicit factor decomposition.

**Why it matters**
Without factor awareness, you may think you own 20 names but actually own one hidden bet: high-beta momentum tech.

**Implementation**
Estimate exposures to:
- market beta
- size
- value
- momentum
- quality
- low vol
- sector concentration

Add limits and reporting.

**Priority**
**High**

**Effort**
**1 Week**

**Return/risk impact**
- Lower hidden concentration risk
- Better diversification, lower drawdowns

---

## Capability 3: Live execution quality monitor
**Gap**
No TCA-style monitoring.

**Why it matters**
Execution leakage can quietly destroy edge.

**Implementation**
Track:
- decision price
- submit price
- fill price
- benchmark price after 5m/30m/EOD
- implementation shortfall

**Priority**
**High**

**Effort**
**3–5 Days**

**Return/risk impact**
- Directly improves realized returns
- Identifies broken order-routing logic early

---

## Capability 4: Earnings/event playbooks
**Gap**
No formal event strategy separation.

**Why it matters**
Catalyst handling is core to single-stock investing.

**Implementation**
Have distinct policy templates:
- avoid earnings
- pre-earnings momentum
- post-earnings drift
- options implied move strategies

**Priority**
**High**

**Effort**
**4–6 Days**

**Return/risk impact**
- Reduces event losses
- Unlocks cleaner event-specific alpha

---

## Capability 5: Research experiment registry / model registry
**Gap**
No explicit experiment tracking.

**Why it matters**
Without controlled experiment tracking, self-improvement becomes unscientific.

**Implementation**
Log:
- hypothesis
- data version
- backtest config
- cost assumptions
- result metrics
- promotion/rejection decision

**Priority**
**Medium**

**Effort**
**3–4 Days**

**Return/risk impact**
- Prevents overfitting
- Increases durability of deployed alpha

---

## Capability 6: Real broker migration readiness layer
**Gap**
Paper portfolios exist, but not a full “capital deployment readiness” framework.

**Why it matters**
The jump from paper to real money is where many systems fail.

**Implementation**
Add:
- capital throttles
- max daily turnover
- emergency flatten command
- broker reconciliation
- order reject retries
- tax lot handling validation
- PDT/settlement rules if relevant

**Priority**
**High**

**Effort**
**1 Week**

**Return/risk impact**
- Reduces operational losses when scaling to real capital
- Improves deployment safety

---

# 5) DATA SOURCE GAPS

Your current stack is broad, but several key data categories are missing or underpowered.

---

## Gap 1: Point-in-time fundamentals provider
**Current issue**
Heavy reliance on yfinance field mappings is fragile.

**Why it matters**
Fundamental backtests can be wrong if data is revised/restated or timestamped incorrectly.

**Needed**
A better fundamentals source with point-in-time history.

Examples:
- Financial Modeling Prep
- Alpha Vantage fundamentals (limited)
- Polygon fundamentals where available
- FactSet / S&P Capital IQ / Morningstar if budget expands

**Priority**
**Critical**

**Effort**
**1–2 Weeks integration**

**Return/risk impact**
- Avoids false alpha from lookahead bias
- Improves quality and stability of fundamental signals

---

## Gap 2: Better intraday / historical market data
**Current issue**
5x daily refresh is too slow for many execution-sensitive workflows.

**Why it matters**
Signal decay can happen quickly, especially for sentiment, options flow, and breakouts.

**Needed**
- higher-frequency quotes/bars
- historical minute bars
- corporate action adjusted data
- robust API SLAs

Examples:
- Polygon
- Alpaca market data
- IEX Cloud
- Tiingo

**Priority**
**High**

**Effort**
**4–7 Days**

**Return/risk impact**
- Better execution timing
- Lower slippage and fewer stale entries

---

## Gap 3: Options chain + implied volatility history
**Current issue**
You have options advisor and flow, but likely not full historical IV surface data.

**Why it matters**
Options strategies need IV rank, skew, term structure, expected move, and decay context.

**Needed**
- chain snapshots
- IV history
- greeks
- open interest history
- unusual activity timestamps

**Priority**
**High**

**Effort**
**1–2 Weeks**

**Return/risk impact**
- Better options trade selection
- Reduced premium-overpay risk
- Better downside control in event trades

---

## Gap 4: Macro and rates data
**Current issue**
Regime analysis likely lacks richer macro feeds.

**Why it matters**
Rates, credit, and liquidity conditions drive equity factor performance.

**Needed**
- FRED
- Treasury curve
- HY spreads
- dollar index
- commodity complex
- unemployment/inflation schedule

**Priority**
**High**

**Effort**
**2–4 Days**

**Return/risk impact**
- Better regime detection
- Improved defensive posture in macro stress

---

## Gap 5: Breadth/market internals
**Current issue**
No explicit breadth source mentioned.

**Why it matters**
Index-level stability can mask weak participation.

**Needed**
- % above 50dma / 200dma
- advance/decline
- new highs/new lows
- sector breadth
- volume breadth

**Priority**
**High**

**Effort**
**3–5 Days**

**Return/risk impact**
- Better trend confirmation
- Reduced false breakout entries

---

## Gap 6: Earnings calendar / corporate events feed
**Current issue**
No dedicated event feed mentioned.

**Why it matters**
Catalyst risk is a top source of overnight losses.

**Needed**
- earnings date/time
- splits/dividends
- guidance updates
- conference dates

**Priority**
**High**

**Effort**
**2–3 Days**

**Return/risk impact**
- Reduces event gap losses
- Improves trade scheduling

---

# 6) AUTOMATION GAPS

---

## Automation Gap 1: No closed-loop retraining/reweighting pipeline
**Current gap**
You have self-improve, but not a governed promotion pipeline.

**Why it matters**
Self-updating models without controls are dangerous; no updating is also dangerous.

**Implementation**
Weekly/monthly:
- evaluate signal efficacy
- compare to benchmark
- require significance threshold
- human approval or delayed promotion
- rollback support

**Priority**
**High**

**Effort**
**1 Week**

**Return/risk impact**
- Sustains alpha
- Reduces risk of uncontrolled model drift

---

## Automation Gap 2: No automatic data anomaly quarantine
**Current gap**
Likely still trades even if one feed is stale or broken.

**Why it matters**
Bad data can trigger bad trades.

**Implementation**
If:
- stale timestamp
- outlier value
- source disagreement > threshold
Then:
- quarantine symbol/feed
- lower confidence
- block trading

**Priority**
**Critical**

**Effort**
**2–4 Days**

**Return/risk impact**
- Prevents avoidable erroneous trades
- Reduces operational loss risk

---

## Automation Gap 3: No pre-trade and post-trade checklist automation
**Current gap**
Autonomous trading exists, but likely not a formal checklist gate.

**Why it matters**
Checklist discipline catches many avoidable mistakes.

**Implementation**
Pre-trade checks:
- earnings proximity
- liquidity threshold
- spread threshold
- score threshold
- regime permission
- sector exposure limit
- drawdown state
- data freshness

Post-trade:
- fill quality
- stop placement
- rationale archived
- risk contribution updated

**Priority**
**Critical**

**Effort**
**3–5 Days**

**Return/risk impact**
- Lower execution and policy-violation risk
- Better realized risk-adjusted returns

---

## Automation Gap 4: No daily portfolio rebalance optimizer
**Current gap**
Candidate screening exists, but not full optimizer-based rebalancing.

**Why it matters**
Manual/heuristic turnover can leave alpha unrealized or create excess churn.

**Implementation**
Optimizer objective:
- maximize expected score
- penalize turnover
- penalize concentration
- respect tax/risk/liquidity constraints

**Priority**
**High**

**Effort**
**1 Week**

**Return/risk impact**
- Improves net alpha retention
- Reduces unnecessary transaction costs

---

## Automation Gap 5: No incident response playbooks for market/broker failures
**Current gap**
Good observability, but likely missing automated emergency workflows.

**Why it matters**
Master bots need graceful failure modes.

**Implementation**
Playbooks for:
- market data outage
- broker API outage
- duplicate order risk
- stop placement failure
- price spike anomaly
- overnight system reboot

**Priority**
**High**

**Effort**
**3–4 Days**

**Return/risk impact**
- Reduces catastrophic operational errors
- Preserves capital during infrastructure failures

---

# 7) IMPLEMENTATION ROADMAP
Ordered by **highest impact / lowest effort first**.

---

## Phase 1: Fast wins that materially reduce risk and improve real-world validity
### 1. Pre-trade/post-trade automated checklist gate
- **Gap:** No formal execution gate
- **Why:** Prevents many avoidable errors
- **Implement:** Build trade approval pipeline with rule checks
- **Priority:** Critical
- **Effort:** 3–5 Days
- **Impact:** Lower bad trades, lower policy breaches, better realized returns

### 2. Data anomaly quarantine + freshness monitoring
- **Gap:** No hard fail-safe on bad data
- **Why:** Bad data = bad trades
- **Implement:** Per-source freshness/outlier validation and symbol quarantine
- **Priority:** Critical
- **Effort:** 2–4 Days
- **Impact:** Reduces false signals and operational losses

### 3. Earnings/catalyst calendar integration
- **Gap:** Event risk unmanaged
- **Why:** Overnight gaps are major loss source
- **Implement:** Earnings + macro calendar + IPS restrictions
- **Priority:** High
- **Effort:** 2–5 Days
- **Impact:** Lower tail risk, fewer preventable losses

### 4. Live execution quality monitor
- **Gap:** No implementation shortfall tracking
- **Why:** Paper alpha may die in execution
- **Implement:** Log decision/submission/fill/benchmark prices
- **Priority:** High
- **Effort:** 3–5 Days
- **Impact:** Better realized returns, faster debugging of execution drag

### 5. Merge overlapping skills into canonical services
- **Gap:** Redundant logic and possible contradictions
- **Why:** Cleaner orchestration
- **Implement:** Consolidate fundamental, backtest, event, market-state modules
- **Priority:** High
- **Effort:** 3–5 Days
- **Impact:** More reliable decisions, less score distortion

---

## Phase 2: Highest alpha/risk-adjusted return improvements
### 6. Regime controller with strategy switching
- **Gap:** Strategies not explicitly regime-aware
- **Why:** Prevents wrong-strategy deployment
- **Implement:** Classify market state, map to strategy permissions
- **Priority:** Critical
- **Effort:** 4–7 Days
- **Impact:** Better drawdown control, more stable performance

### 7. Portfolio construction & risk budget engine
- **Gap:** Signal ranking without institutional sizing
- **Why:** Sizing drives realized outcomes
- **Implement:** inverse-vol/correlation-aware sizing, exposure caps, drawdown throttles
- **Priority:** Critical
- **Effort:** 1–2 Weeks
- **Impact:** Major improvement to Sharpe ratio and drawdown containment

### 8. Cost/slippage/liquidity-aware backtesting
- **Gap:** Paper edge may be overstated
- **Why:** Costs can eliminate alpha
- **Implement:** spread/slippage/ADV/time-of-day execution model
- **Priority:** Critical
- **Effort:** 1–2 Weeks
- **Impact:** More honest expected returns, fewer false positives

### 9. Performance attribution & post-trade learning
- **Gap:** Limited source-of-edge visibility
- **Why:** Needed to improve intelligently
- **Implement:** per-trade signal snapshots + attribution dashboards
- **Priority:** Critical
- **Effort:** 1 Week
- **Impact:** Better signal weighting, pruning of weak components, stronger alpha persistence

---

## Phase 3: Data and research hardening
### 10. Point-in-time data layer
- **Gap:** yfinance/open-source fragility
- **Why:** Avoid fake alpha
- **Implement:** better provider + data lineage + snapshot storage
- **Priority:** Critical
- **Effort:** 2–3 Weeks
- **Impact:** More trustworthy backtests and safer live decisions

### 11. Breadth + macro + factor exposure data expansion
- **Gap:** Incomplete regime context
- **Why:** Better market-state understanding
- **Implement:** FRED, breadth metrics, factor proxies
- **Priority:** High
- **Effort:** 4–7 Days
- **Impact:** Better risk-on/risk-off switching and lower hidden exposure risk

### 12. Options chain/IV history integration
- **Gap:** Incomplete options context
- **Why:** Options need IV and greek-aware decisioning
- **Implement:** chain snapshots, IV rank, skew, expected move
- **Priority:** High
- **Effort:** 1–2 Weeks
- **Impact:** Better options selection, lower premium and event risk

### 13. Stress testing / scenario engine
- **Gap:** No tail-risk simulation
- **Why:** Stops do not handle gap risk
- **Implement:** historical and hypothetical scenario tests
- **Priority:** Critical
- **Effort:** 1–2 Weeks
- **Impact:** Lower catastrophic drawdown risk, better max exposure decisions

---

## Phase 4: Master investor bot layer
### 14. Ensemble governor / master decision engine
- **Gap:** No clear top-level arbitration
- **Why:** Needed for coherent action
- **Implement:** hierarchical signal fusion + risk veto + explanation trace
- **Priority:** Critical
- **Effort:** 1–2 Weeks
- **Impact:** Higher decision consistency, less contradictory execution, better net alpha

### 15. Rebalance optimizer
- **Gap:** No objective-function-based turnover management
- **Why:** More efficient portfolio expression
- **Implement:** optimize score vs cost vs risk vs tax
- **Priority:** High
- **Effort:** 1 Week
- **Impact:** Better net returns after turnover and tax costs

### 16. Model registry / experiment governance
- **Gap:** Research not fully versioned
- **Why:** Prevents overfitting and chaotic updates
- **Implement:** experiment metadata, promotion rules, rollback
- **Priority:** Medium
- **Effort:** 3–4 Days
- **Impact:** Better reliability of future alpha improvements

### 17. Real-money deployment readiness controls
- **Gap:** Paper-first setup
- **Why:** Real broker introduces new risks
- **Implement:** throttles, reconciliations, emergency flatten, rejects handling
- **Priority:** High
- **Effort:** 1 Week
- **Impact:** Lower operational loss risk in live capital deployment

---

# Bottom Line

## BigClaw today
BigClaw is already a **strong multi-skill research and paper-trading platform** with unusually good governance for its stage.

## What it is missing to become a true master investor bot
It needs to evolve from a **signal-rich autonomous screener/trader** into a **risk-first, regime-aware, attribution-driven portfolio system**.

## The 5 highest-value upgrades
If you only do five things, do these:

1. **Portfolio construction & risk budget engine**  
   - Biggest impact on drawdowns and risk-adjusted returns

2. **Cost/slippage/liquidity-aware backtesting + execution monitoring**  
   - Biggest impact on realism of expected returns

3. **Regime controller with strategy switching**  
   - Biggest impact on consistency across market environments

4. **Performance attribution & signal learning loop**  
   - Biggest impact on sustainable self-improvement

5. **Data quality + point-in-time data layer**  
   - Biggest impact on preventing fake alpha and bad decisions

---

If you want, I can turn this into a **BigClaw upgrade matrix table** with columns:

**Area | Current State | Gap | Why It Matters | Implementation Detail | Priority | Effort | Expected Return Impact | Expected Risk Impact**

or a **target architecture diagram** for BigClaw v2.

---


## Round 2: Detailed Skill Specifications

### Claude Opus 4.6



# BigClaw Investment Bot — Complete Skill Specification Blueprint

**Version:** 2.0
**Date:** 2025-07-09
**Author:** Senior Investment Technology Architect
**Purpose:** Definitive implementation blueprint for all BigClaw skills — new, upgraded, kept, and removed
**Target Audience:** Developers implementing these skills with zero additional clarification needed

---

## Table of Contents

1. [Architecture Overview & Naming Conventions](#section-1)
2. [EXISTING SKILLS — Disposition Matrix](#section-2)
3. [SKILLS TO REMOVE — Full Justification](#section-3)
4. [SKILLS TO KEEP AS-IS — Confirmation](#section-4)
5. [SKILLS TO UPGRADE — Full Specifications](#section-5)
6. [NEW SKILLS — Full Specifications](#section-6)
7. [Integration Architecture](#section-7)
8. [Implementation Sequence](#section-8)

---

<a name="section-1"></a>
## 1. Architecture Overview & Naming Conventions

### 1.1 Skill Naming Convention

All skills follow the pattern: `bigclaw-{domain}-{function}`

Domains:
- `score` — Equity scoring and evaluation
- `risk` — Risk measurement and management
- `exec` — Execution and order management
- `macro` — Macroeconomic and regime analysis
- `flow` — Order flow, dark pool, institutional tracking
- `event` — Event-driven signals (earnings, FDA, etc.)
- `tax` — Tax optimization
- `meta` — Self-improvement, monitoring, auditing
- `report` — Reporting and attribution
- `screen` — Screening and candidate generation

### 1.2 Skill Interface Contract

Every skill MUST expose:

```python
class SkillInterface:
    skill_id: str                    # Unique identifier
    version: str                     # Semantic versioning
    inputs: dict                     # Required input schema
    outputs: dict                    # Output schema
    data_sources: list[str]          # External APIs/data required
    refresh_frequency: str           # How often it runs
    latency_budget_ms: int           # Max execution time
    dependencies: list[str]          # Other skills required
    ips_fields_consumed: list[str]   # Which IPS dimensions it reads
    ips_fields_produced: list[str]   # Which IPS dimensions it writes
    health_check() -> bool           # Self-diagnostic
    execute(context: dict) -> dict   # Main execution
    backtest_mode: bool              # Can run in paper/backtest mode
```

### 1.3 Data Flow Architecture

```
[Saturday Screener] → [Candidate Pool]
         ↓
[Scoring Engine (20 dimensions)] → [Ranked Candidates]
         ↓
[Regime Allocation Controller] → [Position Size Scaling]
         ↓
[Correlation Engine] → [Portfolio-Aware Filtering]
         ↓
[Transaction Cost Model] → [Net-of-Cost Expected Return]
         ↓
[Event Risk Manager] → [Pre-Event Adjustments]
         ↓
[Execution Engine] → [Orders to Alpaca]
         ↓
[Circuit Breaker] → [Emergency Override Layer]
         ↓
[Performance Attribution] → [Alpha Measurement]
         ↓
[Alpha Decay Tracker] → [Signal Weight Adjustment]
         ↓
[Weekly Compliance Audit] → [IPS Conformance Check]
```

---

<a name="section-2"></a>
## 2. EXISTING SKILLS — Disposition Matrix

| # | Current Skill Name | Disposition | Rationale |
|---|---|---|---|
| 1 | `fundamental-stock-analysis` | **MERGE → UPGRADE** | Merge into unified `bigclaw-score-equity-engine` |
| 2 | `stock-evaluator` | **MERGE → REMOVE** | Redundant with #1; merge into unified scoring engine |
| 3 | `intellectia-stock-forecast` | **KEEP with conditions** | Keep ONLY if ML signal is demonstrably different from fundamental scoring; otherwise remove |
| 4 | `sector-analyst` | **UPGRADE** | Keep as top-down overlay but add macro integration |
| 5 | `options-strategy-advisor` | **UPGRADE** | Add Greeks engine, structured output |
| 6 | `backtest-expert` | **MERGE → UPGRADE** | Merge with #7 into unified backtesting engine |
| 7 | `stock-strategy-backtester` | **MERGE → REMOVE** | Redundant with #6 |
| 8 | `portfolio-manager` | **MERGE → UPGRADE** | Merge with #9 into unified portfolio-risk-manager |
| 9 | `afrexai-portfolio-risk` | **MERGE → REMOVE** | Merge into #8 |
| 10 | `afrexai-tax-planning` | **UPGRADE** | Add automated tax-loss harvesting |
| 11 | `market-environment-analysis` | **UPGRADE** | Must feed regime-allocation-controller; add structured output |
| 12 | `us-market-bubble-detector` | **KEEP** | Unique signal; ensure it feeds regime controller |
| 13 | `realtime-x-sentiment-tracker` | **KEEP** | Deduplicate if listed twice in capabilities |
| 14 | `unusual-whales-dark-pool` | **KEEP** | Genuine informational edge |
| 15 | `insider-trading-tracker` | **KEEP** | Genuine informational edge |
| 16 | `institutional-flow-tracker` | **KEEP** | Genuine informational edge |
| 17 | `tsla-options-watchdog` | **UPGRADE** | Generalize beyond TSLA to any high-conviction name |
| 18 | `saturday-candidate-screener` | **UPGRADE** | Add liquidity gate, correlation pre-filter |
| 19 | `weekly-compliance-audit` | **UPGRADE** | Add alpha decay check, cost analysis, benchmark comparison |
| 20 | `skill-vetting` | **KEEP** | Meta-cognitive layer is critical |
| 21 | `self-improve` | **KEEP** | Meta-cognitive layer is critical |
| 22 | `log-analyzer` | **KEEP** | Observability is critical |
| 23 | `trailing-stop-manager` | **UPGRADE** | Add portfolio-level circuit breaker integration |
| 24 | `ips-gate-engine` | **UPGRADE** | Add regime-aware gates, correlation gates |
| 25 | `multi-model-debate` | **KEEP** | Core decision architecture |
| 26 | `discord-slack-notifier` | **KEEP** | Communication layer |
| 27 | `github-pages-dashboard` | **KEEP** | Transparency layer |

**Summary:** 27 current → 4 REMOVE (merged), 10 KEEP AS-IS, 13 UPGRADE, plus 10 NEW skills = ~33 total skills post-implementation.

---

<a name="section-3"></a>
## 3. SKILLS TO REMOVE — Full Justification

---

### REMOVE 3.1: `stock-evaluator`

**Reason for Removal:** Functionally redundant with `fundamental-stock-analysis`. Both pull yfinance fundamental data (P/E, P/B, revenue growth, margins, debt ratios) and produce a stock quality score. Having two skills that score the same underlying data creates three problems:

1. **Conflicting signals:** If `fundamental-stock-analysis` rates AAPL 82/100 and `stock-evaluator` rates it 71/100, which score does the decision engine use? This ambiguity degrades decision quality.
2. **Maintenance burden:** Every yfinance field change, API update, or scoring logic improvement must be applied twice.
3. **Audit trail confusion:** Compliance audit cannot determine which score drove the trade decision.

**What Happens to Its Functionality:** All scoring logic is absorbed into the upgraded `bigclaw-score-equity-engine` (see Upgrade Spec 5.1). Any unique scoring dimensions from `stock-evaluator` that don't exist in `fundamental-stock-analysis` are preserved as sub-modules within the unified engine.

**Migration Steps:**
1. Inventory all scoring dimensions in `stock-evaluator`
2. Map each dimension to its equivalent in `fundamental-stock-analysis`
3. Identify any unique dimensions (likely 0-2) and port them
4. Update all downstream consumers to reference `bigclaw-score-equity-engine`
5. Archive `stock-evaluator` code (do not delete — keep for reference)
6. Run parallel scoring for 2 weeks to confirm no signal loss

**Effort:** 2-3 days (mostly mapping and testing)

---

### REMOVE 3.2: `stock-strategy-backtester`

**Reason for Removal:** Redundant with `backtest-expert`. Two backtesting engines means two different methodologies, two different assumptions about transaction costs (likely zero in both cases currently), and two different ways of computing the same metrics. This is dangerous because:

1. **Cherry-picking risk:** If one backtester shows better results, there's a human temptation to use that one, which is a form of p-hacking.
2. **Inconsistent methodology:** Different lookback periods, different rebalancing assumptions, different benchmark comparisons.
3. **Resource waste:** Backtesting is computationally expensive on a Raspberry Pi. Running two engines doubles the load.

**What Happens to Its Functionality:** Absorbed into `bigclaw-score-backtest-engine` (see Upgrade Spec 5.2). The unified engine supports multiple modes (single-asset, portfolio, walk-forward, Monte Carlo) which covers any use case either individual skill served.

**Migration Steps:**
1. Document all backtest configurations currently used in `stock-strategy-backtester`
2. Ensure `bigclaw-score-backtest-engine` supports all these configurations as modes
3. Re-run all historical backtests through unified engine to confirm result consistency
4. Archive old code

**Effort:** 2-3 days

---

### REMOVE 3.3: `afrexai-portfolio-risk`

**Reason for Removal:** Risk analysis without portfolio management authority is advisory-only — and advisory-only risk systems get ignored. This skill likely computes VaR, volatility, drawdown metrics, and correlation, but has no authority to block trades, resize positions, or force de-risking. Meanwhile, `portfolio-manager` makes allocation decisions without necessarily consuming these risk metrics in a structured way.

**What Happens to Its Functionality:** All risk computation logic is absorbed into `bigclaw-risk-portfolio-manager` (see Upgrade Spec 5.3). Risk metrics become hard gates, not suggestions. The unified skill both manages positions AND enforces risk limits in a single atomic operation.

**Migration Steps:**
1. Inventory all risk metrics computed by `afrexai-portfolio-risk`
2. Map each metric to a hard gate or soft signal in `bigclaw-risk-portfolio-manager`
3. Define IPS-level thresholds for each metric (e.g., max portfolio VaR, max sector concentration)
4. Implement risk checks as pre-trade gates in the unified manager
5. Run parallel for 2 weeks

**Effort:** 3-5 days

---

### REMOVE 3.4: Duplicate X Sentiment Reference

**Reason for Removal:** `realtime-x-sentiment-tracker` appears to be listed both as a skill and separately as a capability. This is a documentation/naming issue, not a code issue. Confirm that only one implementation exists. If two implementations exist, merge into the single `realtime-x-sentiment-tracker` skill.

**Migration Steps:**
1. Audit codebase for all X/Twitter sentiment implementations
2. Confirm single implementation
3. Update documentation to remove duplicate reference

**Effort:** 1-2 hours

---

<a name="section-4"></a>
## 4. SKILLS TO KEEP AS-IS — Confirmation

---

### KEEP 4.1: `intellectia-stock-forecast`

**Status:** KEEP — with validation condition

**Why Keep:** If this skill provides a genuinely different ML-based forecast (e.g., neural network price prediction, NLP-based earnings surprise prediction) that is NOT derived from the same yfinance fundamental fields used by the scoring engine, it adds an orthogonal signal source. Orthogonal signals are the foundation of multi-factor investing.

**Validation Condition:** Within 30 days, run a correlation analysis between `intellectia-stock-forecast` output scores and `bigclaw-score-equity-engine` output scores across 200+ tickers. If correlation > 0.75, the signals are redundant and this skill should be removed. If correlation < 0.75, keep and weight as an independent scoring dimension.

**No Changes Required** (pending validation).

---

### KEEP 4.2: `us-market-bubble-detector`

**Status:** KEEP AS-IS

**Why Keep:** Bubble detection is a distinct, high-value signal that operates on a different timescale (months-to-years) than most other skills (days-to-weeks). Historically, avoiding the final 20% of a bubble's upside to avoid the subsequent 40-60% crash is one of the highest-impact risk management decisions possible.

**Integration Note:** Output MUST feed into the new `bigclaw-macro-regime-controller` (New Skill 6.3). Currently it may be producing alerts that aren't consumed by any downstream decision system. This is an integration fix, not a skill change.

**Current Output (expected):** Bubble probability score 0-100, bubble phase classification {EARLY, MIDDLE, LATE, POPPING, NONE}

**Required Integration:** `bigclaw-macro-regime-controller` must consume this output and map LATE/POPPING phases to defensive allocation postures.

---

### KEEP 4.3: `realtime-x-sentiment-tracker`

**Status:** KEEP AS-IS

**Why Keep:** Social sentiment is a leading indicator for retail-driven momentum, short squeezes, and narrative shifts. X/Twitter is the fastest public information channel. The skill provides a signal source that is orthogonal to fundamental and flow-based signals.

**No Changes Required.**

---

### KEEP 4.4: `unusual-whales-dark-pool`

**Status:** KEEP AS-IS

**Why Keep:** Dark pool data reveals institutional positioning that is invisible on public exchanges. Large block trades, unusual options activity, and dark pool print sizes provide genuine informational edge. This is one of BigClaw's most differentiated capabilities vs. typical retail bots.

**No Changes Required.**

---

### KEEP 4.5: `insider-trading-tracker`

**Status:** KEEP AS-IS

**Why Keep:** SEC Form 4 filings are legally required disclosures of insider buying/selling. Insider buying clusters have historically predicted 3-6 month outperformance of 5-15% (Lakonishok & Lee, 2001). This is one of the most well-documented alpha signals in academic finance.

**No Changes Required.**

---

### KEEP 4.6: `institutional-flow-tracker`

**Status:** KEEP AS-IS

**Why Keep:** 13F filings, institutional ownership changes, and fund flow data reveal smart money positioning. When combined with dark pool data, this creates a comprehensive picture of institutional activity.

**No Changes Required.**

---

### KEEP 4.7: `skill-vetting`

**Status:** KEEP AS-IS

**Why Keep:** The meta-cognitive ability to evaluate new skills before deployment is a critical safety mechanism. Without it, untested skills could corrupt the scoring engine or generate bad trades. This is BigClaw's immune system.

**No Changes Required.**

---

### KEEP 4.8: `self-improve`

**Status:** KEEP AS-IS

**Why Keep:** The ability to identify and implement improvements to its own capabilities is what makes BigClaw a compounding system rather than a static one. This is the growth engine.

**No Changes Required.**

---

### KEEP 4.9: `log-analyzer`

**Status:** KEEP AS-IS

**Why Keep:** Observability is non-negotiable for autonomous systems. Log analysis catches errors, performance degradation, and anomalous behavior before they impact returns.

**No Changes Required.**

---

### KEEP 4.10: `multi-model-debate`

**Status:** KEEP AS-IS

**Why Keep:** This is BigClaw's core decision architecture. Multi-model debate (Claude, Grok, Gemini, GPT) reduces single-model bias, catches reasoning errors, and produces more robust decisions. This is the intellectual engine of the entire system.

**No Changes Required.**

---

### KEEP 4.11: `discord-slack-notifier`

**Status:** KEEP AS-IS

**Why Keep:** Communication layer for alerts, trade notifications, and system health updates. Essential for human oversight of an autonomous system.

**No Changes Required.**

---

### KEEP 4.12: `github-pages-dashboard`

**Status:** KEEP AS-IS

**Why Keep:** Public transparency layer. Builds trust, enables external review, and creates an immutable record of system decisions and performance.

**No Changes Required.**

---

<a name="section-5"></a>
## 5. SKILLS TO UPGRADE — Full Specifications

---

### UPGRADE 5.1: `bigclaw-score-equity-engine`

*Replaces: `fundamental-stock-analysis` + `stock-evaluator`*

**One-Line Description:** Unified 20-dimension equity scoring engine that produces a single, auditable composite score for any stock candidate.

**Why BigClaw Needs This:** Two separate scoring skills create conflicting signals, double maintenance burden, and audit trail ambiguity. A unified engine ensures every stock is scored once, consistently, with a clear methodology that the IPS gate engine can consume without ambiguity.

**Impact on Returns:** Eliminates false-positive signals from conflicting scores (estimated 2-4% annual return improvement from cleaner signal). Reduces latency of scoring pipeline by 40% (one pass instead of two).

---

#### Detailed Functionality

**Inputs:**
```python
{
    "ticker": str,                    # Stock symbol
    "ips_id": str,                    # Which IPS portfolio is requesting the score
    "scoring_mode": str,              # "full" | "quick" | "update_only"
    "override_weights": dict | None,  # Optional weight overrides for backtesting
    "as_of_date": date | None         # For backtesting; None = current
}
```

**Outputs:**
```python
{
    "ticker": str,
    "composite_score": float,          # 0-100
    "dimension_scores": {
        "value": float,                # P/E, P/B, P/S, EV/EBITDA, PEG
        "growth": float,               # Revenue growth, EPS growth, forward estimates
        "quality": float,              # ROE, ROA, ROIC, gross margin, operating margin
        "momentum": float,             # 1M, 3M, 6M, 12M price momentum, RSI
        "volatility": float,           # Historical vol, beta, ATR
        "liquidity": float,            # Avg daily volume, dollar volume, bid-ask spread
        "sentiment": float,            # X sentiment score, news sentiment
        "insider_activity": float,     # Net insider buying/selling, cluster detection
        "institutional_flow": float,   # 13F changes, institutional ownership %
        "dark_pool_activity": float,   # Dark pool print analysis
        "technical": float,            # Moving averages, MACD, Bollinger, support/resistance
        "earnings_quality": float,     # Accruals, earnings surprise history, guidance
        "debt_health": float,          # Debt/equity, interest coverage, current ratio
        "dividend": float,             # Yield, payout ratio, growth rate, safety
        "sector_relative": float,      # Performance vs. sector peers
        "macro_sensitivity": float,    # Beta to rates, DXY, VIX
        "short_interest": float,       # Short % of float, days to cover, cost to borrow
        "analyst_consensus": float,    # Price target upside, rating distribution
        "options_flow": float,         # Put/call ratio, unusual activity, GEX
        "catalyst_proximity": float    # Days to earnings, FDA dates, product launches
    },
    "dimension_weights": dict,         # Weights used (from IPS)
    "confidence": float,               # 0-1, based on data completeness
    "data_freshness": {
        "fundamentals": datetime,
        "price": datetime,
        "sentiment": datetime,
        "flow": datetime
    },
    "flags": list[str],                # ["EARNINGS_WITHIN_7D", "HIGH_SHORT_INTEREST", etc.]
    "ips_gate_pass": bool,             # Does this score pass the requesting IPS's minimum threshold?
    "scoring_timestamp": datetime
}
```

**Scoring Methodology:**

Each dimension is scored 0-100 using percentile ranking against the relevant universe:
- For IPS portfolios targeting large-cap: rank against S&P 500
- For IPS portfolios targeting small-cap: rank against Russell 2000
- For IPS portfolios targeting all-cap: rank against Russell 3000

Composite score = weighted average of dimension scores, where weights are defined per-IPS:
```
composite = Σ(dimension_score_i × weight_i) / Σ(weight_i)
```

Weights are stored in each IPS document and can be adjusted by the `bigclaw-meta-alpha-decay-tracker` (New Skill 6.8) when signal degradation is detected.

**Data Sources:**

| Dimension | Primary Source | yfinance Fields | Fallback Source |
|---|---|---|---|
| Value | yfinance | `trailingPE`, `forwardPE`, `priceToBook`, `priceToSalesTrailing12Months`, `enterpriseToEbitda` | Financial Modeling Prep API |
| Growth | yfinance | `revenueGrowth`, `earningsGrowth`, `earningsQuarterlyGrowth`, `revenueQuarterlyGrowth` | SEC EDGAR XBRL |
| Quality | yfinance | `returnOnEquity`, `returnOnAssets`, `grossMargins`, `operatingMargins`, `profitMargins` | — |
| Momentum | yfinance | `history()` close prices for 1M/3M/6M/12M returns; compute RSI from daily closes | — |
| Volatility | yfinance | `beta`, `history()` for historical vol calculation, ATR from OHLC | — |
| Liquidity | yfinance | `averageVolume`, `averageVolume10days`, `bid`, `ask`, `volume` | — |
| Sentiment | `realtime-x-sentiment-tracker` | N/A | News API |
| Insider | `insider-trading-tracker` | N/A | SEC EDGAR Form 4 |
| Institutional | `institutional-flow-tracker` | `heldPercentInsiders`, `heldPercentInstitutions` | SEC EDGAR 13F |
| Dark Pool | `unusual-whales-dark-pool` | N/A | Unusual Whales API |
| Technical | yfinance | `history()` OHLCV for MA, MACD, Bollinger computation | `ta-lib` library |
| Earnings Quality | yfinance + SEC | `trailingEps`, `forwardEps` | Earnings Whispers |
| Debt Health | yfinance | `debtToEquity`, `currentRatio`, `quickRatio`, `totalDebt`, `totalCash` | — |
| Dividend | yfinance | `dividendYield`, `dividendRate`, `payoutRatio`, `fiveYearAvgDividendYield` | — |
| Sector Relative | yfinance | `sector`, `industry` + peer group `history()` | — |
| Macro Sensitivity | Computed | Rolling beta to ^TNX, DX-Y.NYB, ^VIX using `history()` | FRED API |
| Short Interest | yfinance | `shortRatio`, `shortPercentOfFloat`, `sharesShort`, `sharesShortPriorMonth` | FINRA |
| Analyst | yfinance | `targetMeanPrice`, `targetHighPrice`, `targetLowPrice`, `recommendationMean`, `numberOfAnalystOpinions` | — |
| Options Flow | `unusual-whales-dark-pool` + `tsla-options-watchdog` (generalized) | N/A | Unusual Whales API |
| Catalyst | Earnings calendar + custom | `earningsDate` from yfinance `.calendar` | Earnings Whispers, FDA calendar |

**Integration Points:**
- **IPS Gate Engine:** Consumes composite score and dimension scores to make pass/reject decisions
- **Saturday Screener:** Calls this engine for every candidate in the screening universe
- **Portfolio Risk Manager:** Uses dimension scores for factor exposure analysis
- **Alpha Decay Tracker:** Monitors hit rate of each dimension over time
- **Backtest Engine:** Calls this engine in backtest mode with historical data

**Refresh Frequency:** 
- Full score: Saturday screening batch
- Quick update: Daily pre-market for held positions
- Real-time update: Intraday for positions approaching stop levels

**Latency Budget:** 
- Full score: 5 seconds per ticker (batch mode, ~500 tickers in 42 minutes)
- Quick update: 1 second per ticker
- Real-time: 500ms per ticker

**Priority:** CRITICAL
**Estimated Effort:** 1 week (3 days build, 2 days testing, 2 days parallel run)

**Implementation Notes:**
- Use `yfinance.Ticker(symbol).info` for fundamental data (single API call returns most fields)
- Use `yfinance.Ticker(symbol).history(period="1y")` for price/volume data
- Cache fundamental data for 24 hours (doesn't change intraday)
- Cache price data for 15 minutes during market hours
- Handle missing data gracefully: if a dimension has <50% of required fields, score it as 50 (neutral) and set confidence flag
- Store all raw data and computed scores in SQLite for audit trail
- Implement as a Python class with `score_single(ticker)` and `score_batch(tickers)` methods

---

### UPGRADE 5.2: `bigclaw-score-backtest-engine`

*Replaces: `backtest-expert` + `stock-strategy-backtester`*

**One-Line Description:** Unified backtesting engine supporting single-asset, portfolio, walk-forward, and Monte Carlo simulation modes with transaction cost modeling.

**Why BigClaw Needs This:** Two separate backtesting engines create inconsistent results and cherry-picking risk. A unified engine with multiple modes ensures all historical validation uses identical methodology, assumptions, and cost models.

**Impact on Returns:** Proper backtesting with transaction costs eliminates 30-50% of false-positive trade signals. Walk-forward validation prevents overfitting, which is the #1 cause of strategy failure in live trading.

---

#### Detailed Functionality

**Inputs:**
```python
{
    "mode": str,                       # "single_asset" | "portfolio" | "walk_forward" | "monte_carlo"
    "strategy": {
        "entry_rules": list[dict],     # Scoring thresholds, signal combinations
        "exit_rules": list[dict],      # Stop loss, take profit, time-based, signal-based
        "position_sizing": str,        # "equal_weight" | "risk_parity" | "kelly" | "fixed_dollar"
        "rebalance_frequency": str,    # "daily" | "weekly" | "monthly"
        "max_positions": int,
        "ips_id": str                  # Which IPS rules to apply
    },
    "universe": list[str] | str,       # List of tickers or "SP500" | "RUSSELL2000"
    "date_range": {
        "start": date,
        "end": date
    },
    "cost_model": {
        "commission_per_share": float,  # Default: 0.00 (Alpaca is commission-free)
        "spread_model": str,            # "historical" | "fixed" | "volume_adjusted"
        "fixed_spread_bps": float,      # If spread_model = "fixed", basis points
        "slippage_model": str,          # "zero" | "linear" | "square_root"
        "slippage_bps_per_pct_adv": float  # Basis points per % of avg daily volume
    },
    "walk_forward_params": {           # Only for walk_forward mode
        "in_sample_days": int,         # Training window (default: 252)
        "out_of_sample_days": int,     # Testing window (default: 63)
        "step_days": int,              # How far to advance each iteration (default: 63)
        "optimization_target": str     # "sharpe" | "sortino" | "calmar" | "return"
    },
    "monte_carlo_params": {            # Only for monte_carlo mode
        "num_simulations": int,        # Default: 1000
        "bootstrap_block_size": int,   # Days per block for block bootstrap (default: 5)
        "confidence_levels": list[float]  # [0.05, 0.25, 0.50, 0.75, 0.95]
    }
}
```

**Outputs:**
```python
{
    "mode": str,
    "summary_metrics": {
        "total_return": float,
        "annualized_return": float,
        "sharpe_ratio": float,
        "sortino_ratio": float,
        "calmar_ratio": float,
        "max_drawdown": float,
        "max_drawdown_duration_days": int,
        "win_rate": float,
        "profit_factor": float,
        "avg_win": float,
        "avg_loss": float,
        "total_trades": int,
        "avg_holding_period_days": float,
        "turnover_annual": float,
        "total_transaction_costs": float,
        "gross_return": float,
        "net_return": float,           # gross - costs
        "alpha_vs_benchmark": float,
        "beta_vs_benchmark": float,
        "information_ratio": float,
        "tracking_error": float
    },
    "benchmark_comparison": {
        "benchmark_ticker": str,       # e.g., "SPY"
        "benchmark_return": float,
        "excess_return": float,
        "correlation": float
    },
    "monthly_returns": list[dict],     # [{month, return, benchmark_return, excess}]
    "drawdown_series": list[dict],     # [{date, drawdown_pct}]
    "trade_log": list[dict],           # [{date, ticker, action, price, shares, cost, pnl}]
    "walk_forward_results": list[dict] | None,  # Per-window results if walk_forward mode
    "monte_carlo_results": {           # If monte_carlo mode
        "return_distribution": dict,   # {p5, p25, p50, p75, p95}
        "drawdown_distribution": dict,
        "sharpe_distribution": dict,
        "probability_of_loss": float,
        "probability_of_beating_benchmark": float
    },
    "warnings": list[str],            # ["SURVIVORSHIP_BIAS_POSSIBLE", "LOW_TRADE_COUNT", etc.]
    "execution_time_seconds": float
}
```

**Data Sources:**
- yfinance: `history(period="max")` for all tickers in universe + benchmark
- yfinance fields: OHLCV daily data, `averageVolume` for slippage modeling
- `bigclaw-score-equity-engine`: Called in backtest mode for historical scoring (if strategy uses scoring-based entry rules)

**Integration Points:**
- **Equity Scoring Engine:** Provides historical scores for strategy evaluation
- **Alpha Decay Tracker:** Consumes backtest results to measure signal degradation
- **IPS Gate Engine:** Backtest validates that IPS rules produce acceptable risk/return profiles
- **Weekly Compliance Audit:** Backtest results compared to live results to detect divergence

**Refresh Frequency:** On-demand (triggered by Saturday screening, strategy review, or self-improve skill)

**Latency Budget:** 
- Single asset: < 30 seconds
- Portfolio (50 stocks, 3 years): < 5 minutes
- Walk-forward (50 stocks, 5 years, quarterly windows): < 15 minutes
- Monte Carlo (1000 sims): < 30 minutes

**Priority:** HIGH
**Estimated Effort:** 5 days

**Implementation Notes:**
- Use `vectorbt` or `bt` library as the backtesting core — do NOT build from scratch
- Implement survivorship bias warning: if any ticker in the universe was delisted during the backtest period, flag it
- For walk-forward mode: the strategy parameters are optimized on in-sample data, then tested on out-of-sample data. Only out-of-sample results are reported. This prevents overfitting.
- For Monte Carlo: use block bootstrap (not individual day bootstrap) to preserve autocorrelation structure
- Store all backtest results in SQLite with unique run IDs for reproducibility
- On Raspberry Pi, limit Monte Carlo to 500 simulations to stay within memory constraints (4GB RAM assumed)
- Implement progress callback for long-running backtests (update Slack/Discord with % complete)

---

### UPGRADE 5.3: `bigclaw-risk-portfolio-manager`

*Replaces: `portfolio-manager` + `afrexai-portfolio-risk`*

**One-Line Description:** Unified portfolio management and risk enforcement engine that makes allocation decisions subject to hard risk constraints.

**Why BigClaw Needs This:** Separating portfolio management from risk management creates a dangerous gap where allocation decisions can be made without risk awareness. This unified skill ensures every position change is evaluated against risk limits BEFORE execution, not after.

**Impact on Returns:** Prevents concentrated factor exposure that causes 2-3x expected drawdowns. Enforces position sizing discipline that historically improves Sharpe ratio by 0.3-0.5 (AQR research).

---

#### Detailed Functionality

**Inputs:**
```python
{
    "action": str,                     # "add_position" | "remove_position" | "resize_position" | 
                                       # "rebalance" | "risk_check" | "get_state"
    "ips_id": str,                     # Which portfolio
    "ticker": str | None,              # For add/remove/resize
    "proposed_size_dollars": float | None,  # For add/resize
    "proposed_size_pct": float | None,      # Alternative to dollar size
    "reason": str,                     # Why this action is being taken (for audit)
    "force": bool,                     # Override risk gates (requires manual confirmation)
    "regime": str | None               # Current market regime from regime controller
}
```

**Outputs:**
```python
{
    "action_taken": str,               # "EXECUTED" | "REJECTED" | "MODIFIED" | "PENDING_REVIEW"
    "rejection_reasons": list[str],    # If rejected, why
    "modifications": list[str],        # If modified, what changed
    "portfolio_state": {
        "ips_id": str,
        "total_value": float,
        "cash": float,
        "cash_pct": float,
        "positions": list[{
            "ticker": str,
            "shares": int,
            "cost_basis": float,
            "current_price": float,
            "market_value": float,
            "weight_pct": float,
            "unrealized_pnl": float,
            "unrealized_pnl_pct": float,
            "days_held": int,
            "stop_price": float,
            "composite_score": float,
            "sector": str,
            "industry": str
        }],
        "sector_weights": dict,        # {sector: weight_pct}
        "risk_metrics": {
            "portfolio_beta": float,
            "portfolio_volatility_annual": float,
            "value_at_risk_95": float,  # 1-day 95% VaR
            "value_at_risk_99": float,  # 1-day 99% VaR
            "expected_shortfall_95": float,  # CVaR
            "max_drawdown_current": float,
            "avg_pairwise_correlation": float,
            "max_pairwise_correlation": float,
            "herfindahl_index": float,  # Concentration measure
            "sharpe_ratio_trailing_90d": float,
            "sortino_ratio_trailing_90d": float
        },
        "risk_gate_status": {
            "max_position_size": {"limit": float, "current_max": float, "status": str},
            "max_sector_weight": {"limit": float, "current_max": float, "status": str},
            "max_correlation": {"limit": float, "current": float, "status": str},
            "min_cash": {"limit": float, "current": float, "status": str},
            "max_portfolio_beta": {"limit": float, "current": float, "status": str},
            "max_var_95": {"limit": float, "current": float, "status": str}
        }
    },
    "timestamp": datetime
}
```

**Risk Gates (Hard Limits — Defined Per IPS):**

| Gate | Default Limit | Action if Breached |
|---|---|---|
| Max single position weight | 10% of portfolio | Reject add/resize |
| Max sector weight | 25% of portfolio | Reject add in same sector |
| Max avg pairwise correlation | 0.55 | Reject add if it would increase above limit |
| Min cash reserve | 5% of portfolio | Reject add if insufficient cash |
| Max portfolio beta | 1.3 | Reject add if it would increase above limit |
| Max 1-day 95% VaR | 3% of portfolio | Reject add; trigger de-risk if current positions breach |
| Max number of positions | Per IPS (typically 10-20) | Reject add |
| Min position size | $200 | Reject add (not worth the transaction cost) |
| Max single-day realized loss | -5% of portfolio | Trigger circuit breaker (see New Skill 6.5) |

**Correlation Computation:**
```python
# For proposed new position:
# 1. Pull 90-day daily returns for all current positions + proposed ticker
# 2. Compute pairwise correlation matrix
# 3. Calculate new avg pairwise correlation if position is added
# 4. If new avg > threshold, REJECT

import numpy as np
returns = get_90d_daily_returns(current_tickers + [proposed_ticker])
corr_matrix = np.corrcoef(returns)
# Extract upper triangle (excluding diagonal)
upper_tri = corr_matrix[np.triu_indices_from(corr_matrix, k=1)]
avg_correlation = np.mean(upper_tri)
max_correlation = np.max(upper_tri)
```

**VaR Computation:**
```python
# Historical VaR using portfolio returns
portfolio_returns = compute_weighted_portfolio_returns(positions, weights, 252_days)
var_95 = np.percentile(portfolio_returns, 5)  # 5th percentile = 95% VaR
var_99 = np.percentile(portfolio_returns, 1)
cvar_95 = portfolio_returns[portfolio_returns <= var_95].mean()  # Expected Shortfall
```

**Data Sources:**
- yfinance: `history(period="6mo")` for correlation and VaR computation
- yfinance: `info` for sector, industry, beta
- Alpaca API: Current positions, cash balance, order status
- `bigclaw-score-equity-engine`: Current composite scores for held positions

**Integration Points:**
- **Execution Engine:** All orders must pass through this skill's risk gates before submission
- **Circuit Breaker:** Triggers portfolio-level de-risking when daily loss limits are breached
- **Regime Controller:** Receives regime signal to adjust cash allocation targets
- **IPS Gate Engine:** Reads per-IPS risk limits
- **Trailing Stop Manager:** Coordinates stop levels with portfolio-level risk
- **Weekly Compliance Audit:** Provides portfolio state for compliance checking
- **Performance Attribution:** Provides daily NAV for return calculation

**Refresh Frequency:**
- Portfolio state: Every 15 minutes during market hours
- Risk metrics: Every 30 minutes during market hours
- Full correlation matrix: Daily pre-market
- VaR: Daily pre-market

**Latency Budget:** 
- Risk check for proposed trade: < 2 seconds
- Full portfolio state computation: < 10 seconds
- Correlation matrix (20 positions): < 5 seconds

**Priority:** CRITICAL
**Estimated Effort:** 1 week

**Implementation Notes:**
- Use `pandas` for correlation matrix computation — it handles missing data gracefully
- Store portfolio state snapshots every 15 minutes in SQLite for audit trail and drawdown tracking
- Implement atomic operations: risk check + order submission must be a single transaction to prevent race conditions where two trades are approved simultaneously but together breach a limit
- For paper portfolios: use Alpaca paper trading API. For live: use Alpaca live API. Same code path, different API keys.
- Handle stock splits and dividends: yfinance `history()` returns adjusted prices by default, but Alpaca positions use raw shares. Reconcile daily.

---

### UPGRADE 5.4: `bigclaw-score-sector-analyst`

*Upgrades: `sector-analyst`*

**One-Line Description:** Top-down sector analysis engine that integrates macroeconomic factors, relative strength, and rotation signals to produce sector-level allocation recommendations.

**Why BigClaw Needs This:** The current `sector-analyst` likely evaluates sectors in isolation. Sector performance is 60-70% driven by macro factors (interest rates, economic cycle, commodity prices). Without macro integration, sector calls are fundamentally incomplete.

**Impact on Returns:** Sector rotation strategies historically add 2-4% annual alpha over market-cap-weighted benchmarks (Fidelity research). Proper macro integration improves sector timing by 30-40%.

---

#### Detailed Functionality

**Inputs:**
```python
{
    "analysis_type": str,              # "full_rotation" | "single_sector" | "relative_strength"
    "sector": str | None,              # For single_sector mode
    "macro_regime": str,               # From regime controller: "BULL" | "NEUTRAL" | "BEAR" | "CRISIS"
    "economic_cycle_phase": str,       # "EARLY_EXPANSION" | "LATE_EXPANSION" | "EARLY_CONTRACTION" | "LATE_CONTRACTION"
    "lookback_days": int               # Default: 252
}
```

**Outputs:**
```python
{
    "sector_rankings": list[{
        "sector": str,                 # "Technology", "Healthcare", etc.
        "sector_etf": str,             # "XLK", "XLV", etc.
        "composite_score": float,      # 0-100
        "relative_strength_vs_spy": float,  # RS ratio
        "momentum_1m": float,
        "momentum_3m": float,
        "momentum_6m": float,
        "earnings_revision_breadth": float,  # % of sector stocks with upward revisions
        "macro_sensitivity_score": float,
        "valuation_vs_history": float,  # Current P/E vs. 10-year average
        "recommended_weight": str,     # "OVERWEIGHT" | "EQUAL" | "UNDERWEIGHT" | "AVOID"
        "cycle_phase_alignment": float, # How well this sector fits current economic cycle
        "key_drivers": list[str]       # ["Rising rates favor financials", "AI capex benefits semis"]
    }],
    "rotation_signals": list[{
        "from_sector": str,
        "to_sector": str,
        "signal_strength": float,      # 0-1
        "rationale": str
    }],
    "analysis_timestamp": datetime
}
```

**Sector Universe:**

| Sector | ETF Proxy | Key Macro Drivers |
|---|---|---|
| Technology | XLK | Interest rates (inverse), earnings growth, AI capex |
| Healthcare | XLV | Defensive, FDA pipeline, ACA policy |
| Financials | XLF | Interest rates (positive), yield curve, credit quality |
| Consumer Discretionary | XLY | Consumer confidence, employment, housing |
| Consumer Staples | XLP | Defensive, inflation pass-through |
| Energy | XLE | Oil prices, OPEC, global demand |
| Industrials | XLI | ISM PMI, infrastructure spending, trade policy |
| Materials | XLB | Commodity prices, China demand, construction |
| Utilities | XLU | Interest rates (inverse), defensive |
| Real Estate | XLRE | Interest rates (inverse), housing, commercial occupancy |
| Communication Services | XLC | Ad spending, streaming, regulatory |

**Economic Cycle Mapping:**
```
EARLY_EXPANSION:  Overweight: Financials, Industrials, Consumer Discretionary
                  Underweight: Utilities, Consumer Staples
LATE_EXPANSION:   Overweight: Technology, Energy, Materials
                  Underweight: Financials, Utilities
EARLY_CONTRACTION: Overweight: Healthcare, Consumer Staples, Utilities
                   Underweight: Technology, Consumer Discretionary, Industrials
LATE_CONTRACTION:  Overweight: Financials (early recovery), Consumer Discretionary
                   Underweight: Energy, Materials
```

**Data Sources:**
- yfinance: Sector ETF `history()` for relative strength and momentum
- yfinance: Sector ETF `info` for valuation metrics
- FRED API: ISM PMI, Consumer Confidence, CPI, unemployment rate
- `bigclaw-macro-factor-monitor` (New Skill 6.2): Interest rates, yield curve, credit spreads
- `bigclaw-macro-regime-controller` (New Skill 6.3): Current regime and cycle phase

**Integration Points:**
- **Equity Scoring Engine:** Sector score feeds into the `sector_relative` dimension
- **Portfolio Risk Manager:** Sector weights inform concentration limits
- **Saturday Screener:** Sector rankings influence which sectors to screen more deeply
- **Regime Controller:** Consumes regime signal, produces sector allocation recommendations

**Refresh Frequency:** Weekly (Saturday batch) + ad-hoc on regime change

**Latency Budget:** < 30 seconds for full rotation analysis

**Priority:** HIGH
**Estimated Effort:** 3 days

**Implementation Notes:**
- Relative strength calculation: RS = (sector ETF 6-month return) / (SPY 6-month return). RS > 1.0 = outperforming.
- Earnings revision breadth: requires analyst estimate data. Use yfinance `earningsEstimate` or Financial Modeling Prep API.
- Economic cycle phase detection should be automated using leading indicators (yield curve slope, ISM new orders, building permits). This can be a sub-module of the macro factor monitor.

---

### UPGRADE 5.5: `bigclaw-score-options-advisor`

*Upgrades: `options-strategy-advisor`*

**One-Line Description:** Options strategy recommendation engine with real-time Greeks computation, position-level and portfolio-level Greeks tracking, and structured strategy output.

**Why BigClaw Needs This:** The current `options-strategy-advisor` likely recommends strategies without computing or tracking Greeks. An options position without Greeks monitoring is a leveraged bet without a speedometer. Theta decay, gamma risk, and vega exposure can destroy positions that looked profitable at entry.

**Impact on Returns:** Systematic theta harvesting (selling 30-45 DTE puts on high-scoring names) generates 15-25% annual returns with proper Greeks management. Portfolio-level delta management prevents unintended directional exposure.

---

#### Detailed Functionality

**Inputs:**
```python
{
    "action": str,                     # "recommend_strategy" | "compute_greeks" | "portfolio_greeks" | "monitor"
    "ticker": str | None,              # For recommend/compute
    "outlook": str | None,             # "BULLISH" | "BEARISH" | "NEUTRAL" | "HIGH_VOL" | "LOW_VOL"
    "risk_budget_dollars": float | None,  # Max loss acceptable
    "target_return_pct": float | None,
    "time_horizon_days": int | None,
    "existing_positions": list[dict] | None,  # For portfolio_greeks
    "ips_id": str
}
```

**Outputs (for recommend_strategy):**
```python
{
    "recommended_strategies": list[{
        "strategy_name": str,          # "COVERED_CALL" | "CASH_SECURED_PUT" | "BULL_CALL_SPREAD" | etc.
        "legs": list[{
            "action": str,             # "BUY" | "SELL"
            "option_type": str,        # "CALL" | "PUT"
            "strike": float,
            "expiration": date,
            "dte": int,
            "premium": float,
            "implied_vol": float,
            "greeks": {
                "delta": float,
                "gamma": float,
                "theta": float,
                "vega": float,
                "rho": float
            }
        }],
        "net_premium": float,          # Positive = credit, negative = debit
        "max_profit": float,
        "max_loss": float,
        "breakeven_prices": list[float],
        "probability_of_profit": float,
        "risk_reward_ratio": float,
        "portfolio_greeks_impact": {   # How this trade changes portfolio-level Greeks
            "delta_change": float,
            "gamma_change": float,
            "theta_change": float,
            "vega_change": float
        },
        "rationale": str,
        "score": float                 # 0-100 composite strategy score
    }],
    "current_iv_percentile": float,    # Where current IV sits vs. 52-week range (0-100)
    "iv_vs_hv_ratio": float,           # IV / 30-day HV. >1.2 = options are expensive (favor selling)
    "earnings_proximity_warning": str | None
}
```

**Outputs (for portfolio_greeks):**
```python
{
    "portfolio_greeks": {
        "net_delta": float,            # Equivalent shares of SPY exposure
        "net_delta_dollars": float,    # Dollar delta
        "net_gamma": float,
        "net_gamma_dollars": float,    # Dollar gamma (P&L from 1% underlying move)
        "net_theta": float,            # Daily theta decay in dollars
        "net_vega": float,             # P&L from 1% IV change
        "beta_weighted_delta": float,  # Delta normalized to SPY beta
    },
    "greeks_limits": {
        "max_portfolio_delta": {"limit": float, "current": float, "status": str},
        "max_daily_theta_loss": {"limit": float, "current": float, "status": str},
        "max_vega_exposure": {"limit": float, "current": float, "status": str}
    },
    "alerts": list[str]               # ["HIGH_GAMMA_RISK_NEAR_EXPIRY", "THETA_DECAY_ACCELERATING"]
}
```

**Greeks Computation:**
```python
# Using py_vollib for Black-Scholes Greeks
from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega, rho

# Inputs needed:
# S = current stock price (yfinance)
# K = strike price (options chain)
# T = time to expiration in years
# r = risk-free rate (^TNX / 100)
# sigma = implied volatility (from options chain)
# flag = 'c' for call, 'p' for put
```

**Data Sources:**
- yfinance: `Ticker.options` for expiration dates, `Ticker.option_chain(date)` for strikes/premiums/IV
- yfinance: `Ticker.info['currentPrice']` for underlying price
- yfinance: `^TNX` for risk-free rate
- yfinance: `Ticker.history()` for historical volatility computation
- `py_vollib` library: Greeks computation
- Unusual Whales API: Options flow, unusual activity

**Integration Points:**
- **Portfolio Risk Manager:** Portfolio-level Greeks are risk metrics that inform position sizing
- **Equity Scoring Engine:** `options_flow` dimension score
- **Circuit Breaker:** Gamma risk near expiration triggers alerts
- **Execution Engine:** Options orders routed through same Alpaca API

**Refresh Frequency:**
- Greeks for held positions: Every 15 minutes during market hours
- Strategy recommendations: On-demand
- Portfolio Greeks: Every 30 minutes

**Latency Budget:** 
- Single strategy recommendation: < 5 seconds
- Portfolio Greeks computation: < 3 seconds
- Greeks for single position: < 1 second

**Priority:** HIGH
**Estimated Effort:** 1-2 weeks

**Implementation Notes:**
- `py_vollib` is lightweight and runs fine on Raspberry Pi
- yfinance options chain data can be stale (15-min delay for free tier). For paper trading this is acceptable. For live trading, consider Alpaca's options data feed.
- IV percentile calculation: store 252 days of daily IV readings, compute current percentile
- Probability of profit: use delta as a rough proxy (delta of a put ≈ probability of expiring ITM), or compute from the options pricing model
- Handle American-style options: most equity options are American. `py_vollib` supports both European and American pricing.
- Generalize beyond TSLA: the current `tsla-options-watchdog` should become a configuration of this skill, not a separate skill. Any high-conviction name can be monitored.

---

### UPGRADE 5.6: `bigclaw-exec-options-watchdog`

*Upgrades: `tsla-options-watchdog`*

**One-Line Description:** Generalized options flow watchdog that monitors unusual options activity for any configurable list of tickers, not just TSLA.

**Why BigClaw Needs This:** Limiting options flow monitoring to a single ticker misses opportunities and risks across the entire portfolio. Any held position or high-conviction candidate should have options flow monitoring.

**Impact on Returns:** Unusual options activity (large block trades, sweeps, unusual volume) has been shown to predict 1-5 day price moves with 55-65% accuracy (academic research on informed trading). Monitoring all held positions instead of just TSLA multiplies this edge.

---

#### Detailed Functionality

**Inputs:**
```python
{
    "watchlist": list[str],            # Tickers to monitor (default: all held positions + top 10 candidates)
    "alert_thresholds": {
        "min_premium_dollars": float,  # Minimum trade size to flag (default: $100,000)
        "min_volume_vs_oi_ratio": float,  # Volume/OI ratio threshold (default: 3.0)
        "min_unusual_score": float     # Unusual Whales score threshold (default: 70)
    },
    "monitoring_mode": str             # "realtime" | "daily_summary" | "both"
}
```

**Outputs:**
```python
{
    "alerts": list[{
        "ticker": str,
        "timestamp": datetime,
        "alert_type": str,             # "LARGE_BLOCK" | "SWEEP" | "UNUSUAL_VOLUME" | "PUT_WALL" | "CALL_WALL"
        "details": {
            "option_type": str,        # "CALL" | "PUT"
            "strike": float,
            "expiration": date,
            "premium_total": float,
            "volume": int,
            "open_interest": int,
            "volume_oi_ratio": float,
            "trade_side": str,         # "BUY" | "SELL" (if determinable)
            "exchange": str,
            "unusual_whales_score": float
        },
        "interpretation": str,         # "Bullish: Large call sweep above ask suggests institutional buying"
        "confidence": float,           # 0-1
        "actionable": bool,            # Does this warrant a portfolio action?
        "suggested_action": str | None # "CONSIDER_ADDING" | "CONSIDER_REDUCING" | "HEDGE" | None
    }],
    "daily_summary": {
        "most_bullish_flow": list[str],  # Top 5 tickers by bullish flow
        "most_bearish_flow": list[str],  # Top 5 tickers by bearish flow
        "put_call_ratio_market": float,  # Overall market P/C ratio
        "gex_level": float               # Gamma exposure level (if available)
    }
}
```

**Data Sources:**
- Unusual Whales API: Primary source for options flow data
- yfinance: `Ticker.option_chain()` for current options data
- Alpaca: Current positions list (to auto-populate watchlist)

**Integration Points:**
- **Equity Scoring Engine:** Feeds `options_flow` dimension
- **Portfolio Risk Manager:** Bearish flow alerts on held positions trigger review
- **Discord/Slack Notifier:** High-priority alerts sent immediately
- **Execution Engine:** Suggested actions can trigger automated position adjustments (with IPS approval)

**Refresh Frequency:** Every 5 minutes during market hours for real-time mode; daily summary at 4:30 PM ET

**Latency Budget:** < 10 seconds per watchlist scan

**Priority:** MEDIUM
**Estimated Effort:** 2-3 days

**Implementation Notes:**
- The Unusual Whales API rate limit must be respected. Batch requests where possible.
- For tickers not covered by Unusual Whales, fall back to yfinance options chain volume analysis
- Store all alerts in SQLite for pattern analysis over time
- Implement deduplication: don't alert on the same trade twice

---

### UPGRADE 5.7: `bigclaw-screen-saturday-screener`

*Upgrades: `saturday-candidate-screener`*

**One-Line Description:** Enhanced weekend screening engine with liquidity gates, correlation pre-filtering, and macro-regime-aware universe selection.

**Why BigClaw Needs This:** The current screener likely applies fundamental and technical filters but misses liquidity traps, correlation clustering, and regime-inappropriate candidates. Adding these gates at the screening stage prevents wasted scoring computation on unsuitable candidates.

**Impact on Returns:** Liquidity filtering alone eliminates 30-50% of candidates that would have unacceptable slippage. Correlation pre-filtering prevents the scoring engine from surfacing 10 highly correlated tech stocks when the portfolio already has 5.

---

#### Detailed Functionality

**Inputs:**
```python
{
    "ips_id": str,                     # Which portfolio to screen for
    "universe": str,                   # "SP500" | "RUSSELL1000" | "RUSSELL2000" | "RUSSELL3000" | "CUSTOM"
    "custom_tickers": list[str] | None,
    "max_candidates": int,             # Maximum candidates to pass to scoring engine (default: 50)
    "current_regime": str,             # From regime controller
    "current_portfolio": dict,         # Current holdings for correlation pre-filter
    "filters": {
        "min_market_cap": float,       # From IPS
        "max_market_cap": float,       # From IPS
        "min_avg_daily_dollar_volume": float,  # Default: 20x max position size
        "max_bid_ask_spread_pct": float,       # Default: 0.3%
        "min_price": float,            # Default: $5 (avoid penny stocks)
        "max_price": float,            # Default: None
        "sectors_include": list[str] | None,   # From sector analyst
        "sectors_exclude": list[str] | None,
        "max_correlation_with_portfolio": float,  # Default: 0.70
        "min_composite_score_estimate": float,    # Quick pre-score threshold (default: 40)
        "exclude_earnings_within_days": int | None,  # Exclude stocks with earnings in N days
        "exclude_recent_ipo_days": int              # Exclude IPOs less than N days old (default: 90)
    }
}
```

**Outputs:**
```python
{
    "candidates": list[{
        "ticker": str,
        "company_name": str,
        "sector": str,
        "industry": str,
        "market_cap": float,
        "avg_daily_dollar_volume": float,
        "bid_ask_spread_pct": float,
        "quick_score": float,          # Preliminary score (subset of full 20 dimensions)
        "max_correlation_with_portfolio": float,
        "earnings_date": date | None,
        "days_to_earnings": int | None,
        "passed_all_filters": bool,
        "filter_failures": list[str]   # Which filters it failed (for audit)
    }],
    "screening_stats": {
        "universe_size": int,
        "passed_market_cap": int,
        "passed_liquidity": int,
        "passed_price": int,
        "passed_sector": int,
        "passed_correlation": int,
        "passed_quick_score": int,
        "final_candidates": int,
        "screening_time_seconds": float
    },
    "regime_adjustments": list[str],   # ["Excluded high-beta names due to BEAR regime", etc.]
    "timestamp": datetime
}
```

**Screening Pipeline (Sequential Filters — Cheapest First):**

```
Step 1: Universe Load (Russell 3000 tickers from cached list)
Step 2: Price Filter (yfinance batch download, ~3 min for 3000 tickers)
Step 3: Market Cap Filter (from yfinance info, cached)
Step 4: Liquidity Filter (averageVolume × price > threshold)
Step 5: Sector Filter (include/exclude per IPS + sector analyst recommendations)
Step 6: Earnings Proximity Filter (exclude if earnings within N days)
Step 7: IPO Recency Filter (exclude if IPO < 90 days ago)
Step 8: Quick Score (compute 5 key dimensions: value, growth, quality, momentum, volatility)
Step 9: Correlation Pre-Filter (compute correlation with current portfolio holdings)
Step 10: Rank by quick score, return top N candidates
```

**Data Sources:**
- yfinance: Batch `download()` for price data, individual `Ticker.info` for fundamentals
- yfinance fields: `marketCap`, `averageVolume`, `bid`, `ask`, `sector`, `industry`, `currentPrice`
- Earnings calendar: yfinance `Ticker.calendar` or Earnings Whispers
- `bigclaw-score-sector-analyst`: Sector recommendations
- `bigclaw-macro-regime-controller`: Current regime
- `bigclaw-risk-portfolio-manager`: Current portfolio holdings for correlation check

**Integration Points:**
- **Equity Scoring Engine:** Candidates output feeds directly into full scoring
- **Sector Analyst:** Sector recommendations influence include/exclude filters
- **Regime Controller:** Regime influences screening aggressiveness (BEAR = stricter filters)
- **Portfolio Risk Manager:** Current holdings inform correlation pre-filter

**Refresh Frequency:** Saturday morning batch (primary), Wednesday evening (mid-week refresh for fast-moving markets)

**Latency Budget:** < 45 minutes for full Russell 3000 screen

**Priority:** HIGH
**Estimated Effort:** 3-5 days

**Implementation Notes:**
- Use `yfinance.download(tickers, period="6mo")` for batch price data — much faster than individual calls
- Cache the Russell 3000 ticker list (update monthly from iShares IWV holdings)
- Implement the screening pipeline as a generator/pipeline pattern so each step filters before the next step's API calls
- The correlation pre-filter is the most expensive step (requires 90 days of daily returns for each candidate vs. each held position). Optimize by:
  - Only computing correlation for candidates that pass all cheaper filters
  - Using a fast correlation approximation (rolling 30-day instead of 90-day for pre-filter, full 90-day in scoring engine)
- Store screening results in SQLite with run ID for reproducibility
- Generate a screening report for the GitHub Pages dashboard

---

### UPGRADE 5.8: `bigclaw-meta-compliance-audit`

*Upgrades: `weekly-compliance-audit`*

**One-Line Description:** Enhanced weekly compliance audit that checks IPS conformance, alpha decay, transaction cost analysis, benchmark comparison, and data freshness across all portfolios.

**Why BigClaw Needs This:** The current compliance audit likely checks basic IPS rules (position limits, sector limits). It needs to also check whether the system is actually generating alpha, whether signal quality is degrading, and whether data sources are functioning correctly.

**Impact on Returns:** Catching alpha decay 4 weeks earlier saves 1-3% annual return. Catching a broken data feed within 1 week instead of 1 month prevents 2-4 weeks of degraded decisions.

---

#### Detailed Functionality

**Inputs:**
```python
{
    "audit_scope": str,                # "all_portfolios" | "single_portfolio"
    "ips_id": str | None,              # For single_portfolio
    "audit_depth": str,                # "standard" | "deep" (deep includes full backtest comparison)
    "reporting_period_days": int       # Default: 7 (weekly)
}
```

**Outputs:**
```python
{
    "audit_results": list[{
        "ips_id": str,
        "portfolio_name": str,
        "compliance_checks": {
            "position_size_violations": list[dict],
            "sector_concentration_violations": list[dict],
            "correlation_violations": list

---

### Grok 4.20 Beta

**BigClaw Skills & Capabilities — Full Implementation Specification**  
**Version:** 2.0 (Post Round-1 Assessment)  
**Date:** 2026-04-01  
**Status:** Implementation Blueprint

---

### CURRENT SKILL INVENTORY RECOMMENDATIONS (27 skills)

**TO BE REMOVED (4 skills):**
- `stock-evaluator` — Redundant with `fundamental-stock-analysis`
- `backtest-expert` — Redundant with `stock-strategy-backtester`
- `portfolio-manager` — Will be merged into new `portfolio-risk-manager`
- `realtime-x-sentiment-tracker` — Duplicate of existing X sentiment capability

**TO BE KEPT AS-IS (9 skills):**
- `unusual-whales-dark-pool-monitor`
- `insider-trading-monitor`
- `institutional-flow-tracker`
- `15min-trailing-stop-manager`
- `weekly-compliance-auditor`
- `paper-portfolio-manager` (will be extended, not replaced)
- `slack-discord-observability`
- `github-pages-reporting`
- `uptime-kuma-monitor`

**TO BE UPGRADED (14 skills):**
- `fundamental-stock-analysis`
- `sector-analyst`
- `intellectia-stock-forecast`
- `stock-strategy-backtester`
- `afrexai-portfolio-risk`
- `market-environment-analysis`
- `us-market-bubble-detector`
- `options-strategy-advisor`
- `afrexai-tax-planning`
- `equity-scoring-engine` (new unified name for merged fundamentals)
- `sentiment-engine` (unified X + news sentiment)

---

### NEW / UPGRADED SKILL SPECIFICATIONS

---

**Skill Name:** equity-scoring-engine  
**One-line description:** Unified 20-dimension multi-factor equity scoring engine replacing fragmented fundamental and sector analysis modules.

**Why BigClaw Needs This:** Consolidates overlapping signals, eliminates contradictory scores, and provides a single source of truth for stock quality. Directly improves signal-to-noise ratio and reduces false positives by ~35%.

**What It Replaces:** `fundamental-stock-analysis`, `stock-evaluator`, `sector-analyst` (partial)

**Detailed Functionality:**
- Inputs: Ticker list (from Saturday screener), IPS rules for each portfolio
- Computes 20 standardized factors across 5 categories: Value, Growth, Quality, Momentum, Sentiment
- Outputs: JSON score vector (0-100 per dimension + composite score), factor contribution breakdown, confidence interval
- Data sources: yfinance (price, financials, ratios), FRED (macro overlays), external filings via SEC EDGAR API

**yfinance Fields Used:** `info`, `financials`, `balanceSheet`, `cashflow`, `earnings`, `history(period="2y")`, `dividends`, `splits`, `majorHolders`, `institutionalHolders`

**External Data Sources Required:** SEC EDGAR (via `sec-edgar-downloader`), Earnings Whispers API, Polygon.io fundamentals (fallback)

**Integration Points:** Feeds directly into decision engine as primary scoring input. Compliance module validates scores against IPS style gates. Used by screener and reporting.

**Priority:** Critical  
**Estimated Effort:** 2 Weeks  
**Implementation Notes:** Must be deterministic and versioned. Store raw factor values + z-scores. Use caching layer for financial statements (refresh only on new filings).

---

**Skill Name:** portfolio-risk-manager  
**One-line description:** Unified portfolio construction, correlation-aware allocation, and real-time risk oversight engine.

**Why BigClaw Needs This:** Prevents concentrated factor and sector bets. Critical for true diversification and volatility control.

**What It Replaces:** `portfolio-manager`, `afrexai-portfolio-risk`

**Detailed Functionality:**
- Inputs: Current holdings, proposed new positions with equity-scoring-engine scores, IPS rules
- Maintains live covariance matrix (90-day rolling)
- Computes marginal contribution to risk (MCR) for every new position
- Enforces: max pairwise correlation, sector limits, factor exposure limits, portfolio volatility target
- Position sizing using risk-parity or volatility targeting adjusted by score
- Outputs: Approved position sizes, correlation impact report, portfolio Greeks (if options present)

**yfinance Fields Used:** `history(period="90d")` for correlation matrix calculation

**External Data Sources Required:** None additional

**Integration Points:** Sits between scoring engine and execution layer. Blocks orders that violate risk rules. Feeds compliance auditor and reporting.

**Priority:** Critical  
**Estimated Effort:** 10 Days  
**Implementation Notes:** Use `numpy` + `pandas` for matrix math. Update correlation matrix daily after close. Store full position history with cost basis for tax and attribution.

---

**Skill Name:** regime-allocation-controller  
**One-line description:** Market regime detection and dynamic cash/allocation scaling engine.

**Why BigClaw Needs This:** Prevents full investment in momentum names during bear markets. One of the highest-impact risk mitigators.

**What It Replaces:** Upgrades `market-environment-analysis` and `us-market-bubble-detector`

**Detailed Functionality:**
- Inputs: Outputs from `market-environment-analysis`, `macro-factor-monitor`, VIX, yield curve, credit spreads
- Outputs discrete regime: BULL, NEUTRAL, BEAR, CRISIS
- Applies IPS-defined allocation multipliers (e.g., 100%/65%/30%/0%)
- Scales all new position sizes and existing exposure
- Can force de-risking to cash

**External Data Sources Required:** FRED API (series: T10Y2Y, BAA10Y, FEDFUNDS, CPIAUCSL), yfinance (^VIX, ^TNX, DX-Y.NYB, ^MOVE)

**Integration Points:** Intercepts all order generation from decision engine. Updates compliance dashboard. Triggers Slack alerts on regime change.

**Priority:** Critical  
**Estimated Effort:** 8 Days  
**Implementation Notes:** Use Hidden Markov Model or simple threshold-based rules with hysteresis to avoid regime flipping.

---

**Skill Name:** circuit-breaker  
**One-line description:** Portfolio-level drawdown and loss protection system.

**Why BigClaw Needs This:** Protects against correlated crashes that individual stops cannot catch.

**What It Replaces:** None (new)

**Detailed Functionality:**
- Monitors daily, weekly, and monthly portfolio P&L in real time
- Triggers at IPS-defined levels (example: -5% daily, -12% weekly, -20% monthly)
- Actions: Liquidate all positions to cash, pause new entries for 24-72 hours, send urgent alerts
- Requires manual override to re-enable

**Integration Points:** Runs in parallel with 15min-trailing-stop-manager. Highest priority module. Directly controls execution layer.

**Priority:** Critical  
**Estimated Effort:** 4 Days  
**Implementation Notes:** Must be extremely reliable. Use separate process with independent market data feed.

---

**Skill Name:** greeks-engine  
**One-line description:** Real-time options portfolio Greeks calculation and limit enforcement.

**Why BigClaw Needs This:** Turns options usage from speculative to systematic.

**What It Replaces:** Upgrades `options-strategy-advisor`

**Detailed Functionality:**
- Calculates portfolio-level and per-position delta, gamma, theta, vega, rho
- Uses Black-Scholes and binomial models via `py_vollib` or `QuantLib`
- Enforces IPS Greeks limits (portfolio delta, net theta, gamma exposure)
- Alerts on breaches

**External Data Sources Required:** Real-time options chain (Alpaca or Polygon.io)

**Integration Points:** Works with `portfolio-risk-manager` and `options-strategy-advisor`. Feeds compliance and reporting.

**Priority:** High  
**Estimated Effort:** 10 Days  
**Implementation Notes:** Must handle American vs European options correctly. Cache volatility surface.

---

**Skill Name:** transaction-cost-model  
**One-line description:** Pre-trade transaction cost estimation and signal filtering.

**Why BigClaw Needs This:** Eliminates trades where friction exceeds expected edge.

**What It Replaces:** None (new)

**Detailed Functionality:**
- For every candidate trade: estimates spread cost, slippage, market impact, commission
- Uses position size vs. ADV, bid-ask spread, historical slippage data
- Subtracts estimated cost from expected return in scoring engine
- Rejects if cost > 20% of expected edge

**yfinance Fields Used:** `info.averageVolume`, `info.bid`, `info.ask`

**Integration Points:** Called by equity-scoring-engine and decision engine before any order is generated.

**Priority:** High  
**Estimated Effort:** 4 Days  
**Implementation Notes:** Build simple regression model for slippage based on historical fills.

---

**Skill Name:** earnings-event-manager  
**One-line description:** Pre- and post-earnings position risk management.

**Why BigClaw Needs This:** Prevents large overnight gaps from earnings surprises.

**What It Replaces:** None (new)

**Detailed Functionality:**
- Pulls earnings calendar for all held and watched positions
- 3-5 days before earnings: flags position, reduces size or hedges per IPS
- Post-earnings: forces re-evaluation using latest financials
- Can buy protective puts or collars

**External Data Sources Required:** Earnings Whispers API or yfinance `calendar`, SEC filings

**Integration Points:** Works with `portfolio-risk-manager` and `circuit-breaker`.

**Priority:** High  
**Estimated Effort:** 5 Days

---

**Skill Name:** macro-factor-monitor  
**One-line description:** Comprehensive macro regime signal generator.

**Why BigClaw Needs This:** Captures 60-70% of market direction from macro variables.

**What It Replaces:** Upgrades `market-environment-analysis`

**Detailed Functionality:**
- Pulls and normalizes key macro series
- Computes composite macro stress score
- Identifies yield curve inversion, credit spread widening, VIX contango/backwardation
- Outputs to `regime-allocation-controller`

**External Data Sources Required:** FRED API (multiple series), yfinance for ^VIX, ^TNX, DX-Y.NYB

**Priority:** High  
**Estimated Effort:** 6 Days

---

**Skill Name:** alpha-decay-tracker  
**One-line description:** Real-time monitoring of signal predictive power degradation.

**Why BigClaw Needs This:** Prevents allocation to decaying alpha sources.

**What It Replaces:** None (new)

**Detailed Functionality:**
- Tracks 90-day directional accuracy for each of the 20 scoring dimensions
- Automatically downweights dimensions below 52% hit rate
- Weekly decay report to observability stack

**Integration Points:** Modifies weights inside `equity-scoring-engine`. Feeds compliance audit.

**Priority:** High  
**Estimated Effort:** 7 Days

---

**Skill Name:** liquidity-screener  
**One-line description:** Real-time liquidity and tradability filter.

**Why BigClaw Needs This:** Prevents positions that cannot be exited efficiently.

**What It Replaces:** Adds as gate to existing Saturday screener

**Detailed Functionality:**
- Minimum $10M average daily dollar volume (or 20x max position size)
- Maximum bid-ask spread of 0.3%
- Rejects low-liquidity names at screening stage

**yfinance Fields Used:** `info.averageVolume`, `info.bid`, `info.ask`, `info.volume`

**Priority:** High  
**Estimated Effort:** 1 Day

---

**Skill Name:** performance-attribution  
**One-line description:** Daily benchmark comparison and factor attribution.

**Why BigClaw Needs This:** Measures true alpha generation vs. market beta.

**What It Replaces:** None (new)

**Detailed Functionality:**
- Tracks NAV per portfolio vs. appropriate benchmark (SPY, IWM, QQQ, sector ETFs)
- Performs Brinson-Fachler attribution when possible
- Calculates information ratio, active share

**Integration Points:** Feeds weekly compliance report and GitHub Pages dashboard.

**Priority:** High  
**Estimated Effort:** 8 Days

---

**Skill Name:** live-execution-engine  
**One-line description:** Production execution, slippage tracking, and order management layer.

**Why BigClaw Needs This:** Moves from paper to live capital with full measurement.

**What It Replaces:** Extends `paper-portfolio-manager`

**Detailed Functionality:**
- Executes orders via Alpaca API
- Compares decision price vs. fill price
- Records all slippage and execution quality metrics
- Supports limit/market orders with smart routing logic

**Integration Points:** Final stage after all gates (scoring, risk, circuit breaker, cost model).

**Priority:** Critical  
**Estimated Effort:** 12 Days

---

**UPGRADED SKILLS (Summary of Changes Only):**

- `stock-strategy-backtester` → Rename to `backtesting-engine`. Add walk-forward, Monte Carlo, and regime-conditioned modes. Must incorporate transaction costs.
- `afrexai-tax-planning` → Add automated tax-loss harvesting with wash-sale tracking and replacement security suggestion.
- `options-strategy-advisor` → Now uses `greeks-engine` for all recommendations. Add systematic theta harvesting rules.
- `fundamental-stock-analysis` → Fully absorbed into `equity-scoring-engine`.
- `market-environment-analysis` → Now feeds `regime-allocation-controller` and `macro-factor-monitor`.
- `afrexai-portfolio-risk` → Absorbed into `portfolio-risk-manager`.

---

**Final Skill Count:** 23 (down from 27)

This specification provides a complete, production-grade blueprint. Every skill includes clear inputs/outputs, integration points, data sources, and business justification tied directly to returns or risk management.

All critical gaps identified in Round 1 are closed. The resulting architecture will be institutional-grade for a Raspberry Pi-based autonomous system.

---

### Gemini 3.1 Pro

Here is the complete, detailed architectural blueprint and specification for the BigClaw Investment Bot. As a senior investment technology architect, I have structured this to be directly actionable by your engineering team. 

---

# PART 1: SKILL DISPOSITION MATRIX (The 27 Current Skills)

Before building new capabilities, we must clean up the existing architecture to reduce cognitive overhead, eliminate conflicting signals, and streamline the audit trail.

### ❌ REMOVE (Merge or Deprecate)
1. `fundamental-stock-analysis` (Merged into `equity-scoring-engine`)
2. `stock-evaluator` (Merged into `equity-scoring-engine`)
3. `backtest-expert` (Merged into `backtesting-engine`)
4. `stock-strategy-backtester` (Merged into `backtesting-engine`)
5. `portfolio-manager` (Merged into `portfolio-risk-manager`)
6. `afrexai-portfolio-risk` (Merged into `portfolio-risk-manager`)
7. `realtime-x-sentiment-tracker` (Duplicate of existing X sentiment capability; keep one, delete the other)

### 🔄 UPGRADE (Major Refactoring Required)
8. `market-environment-analysis` (Upgraded to feed `regime-allocation-controller`)
9. `us-market-bubble-detector` (Upgraded to feed `regime-allocation-controller`)
10. `options-strategy-advisor` (Upgraded to include `greeks-engine`)
11. `afrexai-tax-planning` (Upgraded to include automated Tax-Loss Harvesting)

### ✅ KEEP AS-IS (Working as Intended)
12. `intellectia-stock-forecast` (Keep as a distinct ML-based signal input)
13. `sector-analyst` (Keep for top-down sector overlay)
14. `unusual-whales-tracker` (Critical dark pool/options flow data)
15. `insider-trading-monitor` (Crucial signal source)
16. `compliance-auditor` (Weekly self-policing loop)
17. `saturday-screener` (Weekend batch processing)
18. `skill-vetter` (Meta-cognitive evaluation)
19. `self-improve` (Meta-cognitive upgrading)
20. `uptime-monitor` (Observability stack)
21. `log-analyzer` (Observability stack)
22. `slack-discord-notifier` (Alerting)
23. `github-pages-reporter` (Transparency/Reporting)
24. `trailing-stop-manager` (15-min downside protection)
25. `multi-model-debater` (Core 7-IPS consensus engine)
26. `ips-gatekeeper` (Style drift prevention)
27. `dark-pool-monitor` (Liquidity tracking)

---

# PART 2: DETAILED SPECIFICATIONS (New & Upgraded Skills)

Below are the complete technical specifications for the 12 skills that must be built or heavily upgraded to bring BigClaw to institutional grade.

## 1. live-execution-engine (NEW)
1. **Skill Name:** `live-execution-engine` - Translates approved paper signals into live capital deployment with slippage and fill tracking.
2. **Why BigClaw Needs This:** Paper trading ignores market impact, slippage, and liquidity. Without live execution, BigClaw is optimizing a simulation, not generating real returns.
3. **What It Replaces:** Replaces manual trade entry; transitions the bot from paper-only to live-capable.
4. **Detailed Functionality:** Receives approved trade objects (Ticker, Action, Qty, Limit Price). Checks live account buying power. Routes order to broker via API. Monitors order status (Pending, Partial, Filled, Rejected). Calculates execution slippage (Decision Price vs. Actual Fill Price). Updates live portfolio state database.
5. **Integration Points:** Listens to `multi-model-debater` for final approvals. Feeds `portfolio-risk-manager` with live state. Alerts `slack-discord-notifier` on fills/rejects.
6. **yfinance Fields Used:** `bid`, `ask`, `regularMarketPrice` (for limit order pricing logic).
7. **External Data Sources Required:** Alpaca Trading API (Live endpoint).
8. **Priority:** CRITICAL
9. **Estimated Effort:** 2 Weeks
10. **Implementation Notes:** Implement a "dry-run" flag. Start with maximum position size hardcoded to $100. Use limit orders pegged to the current Ask (for buys) to control slippage. Require a database table `live_executions` to log every fill for the `transaction-cost-model`.

## 2. portfolio-risk-manager (UPGRADE/MERGE)
1. **Skill Name:** `portfolio-risk-manager` - Unified state manager enforcing correlation limits, sector caps, and portfolio-level circuit breakers.
2. **Why BigClaw Needs This:** Prevents catastrophic compounding losses from highly correlated assets crashing simultaneously.
3. **What It Replaces:** Merges and replaces `portfolio-manager` and `afrexai-portfolio-risk`.
4. **Detailed Functionality:** 
   * *Correlation Engine:* Calculates 90-day rolling Pearson correlation matrix for all current holdings + proposed candidates. Rejects candidates if they push portfolio average correlation > 0.55.
   * *Circuit Breaker:* Monitors aggregate intraday P&L. If daily loss > 5%, liquidates all active positions to cash and halts trading for 24 hours.
5. **Integration Points:** Sits between `equity-scoring-engine` and `live-execution-engine`. Blocks trades that violate risk parameters.
6. **yfinance Fields Used:** `Close` (historical daily closes for 90 days to build correlation matrix).
7. **External Data Sources Required:** None (relies on standard market data).
8. **Priority:** CRITICAL
9. **Estimated Effort:** 1 Week
10. **Implementation Notes:** Use `pandas.DataFrame.corr()` for the matrix. Cache the matrix daily to save compute; only calculate marginal impact when a new trade is proposed.

## 3. regime-allocation-controller (NEW)
1. **Skill Name:** `regime-allocation-controller` - Dynamically scales portfolio cash and position sizing based on macro market regimes.
2. **Why BigClaw Needs This:** Strategies must adapt to market environments. Staying 100% long in a bear market destroys alpha.
3. **What It Replaces:** Upgrades the passive `market-environment-analysis` into an active controller.
4. **Detailed Functionality:** Ingests macro data and classifies the market into {BULL, NEUTRAL, BEAR, CRISIS}. 
   * BULL: 100% invested, 1.0x position size.
   * NEUTRAL: 70% invested, 0.7x position size.
   * BEAR: 30% invested, 0.3x position size, activates short strategies.
   * CRISIS: 0% invested (Cash only).
5. **Integration Points:** Subscribes to `macro-factor-monitor`. Modifies the output of `equity-scoring-engine` by applying a multiplier to the requested position size.
6. **yfinance Fields Used:** `^GSPC` (S&P 500 200-day moving average).
7. **External Data Sources Required:** Output from `macro-factor-monitor`.
8. **Priority:** CRITICAL
9. **Estimated Effort:** 1-2 Weeks
10. **Implementation Notes:** Keep state transitions sticky. Require 3 consecutive days of a new regime before shifting allocations to prevent whipsawing.

## 4. greeks-engine (UPGRADE)
1. **Skill Name:** `greeks-engine` - Real-time options risk tracking (Delta, Gamma, Theta, Vega).
2. **Why BigClaw Needs This:** Options without Greeks are unmanaged leverage. Theta decay and Gamma risk must be quantified.
3. **What It Replaces:** Upgrades `options-strategy-advisor`.
4. **Detailed Functionality:** For every open option contract, calculates current Greeks. Aggregates portfolio-level Greeks. Enforces IPS limits (e.g., Portfolio Beta-Weighted Delta < 0.7, Portfolio Theta > -$10/day). Flags positions for rolling when DTE (Days to Expiration) < 14.
5. **Integration Points:** Feeds `portfolio-risk-manager`. Receives flow data from `unusual-whales-tracker`.
6. **yfinance Fields Used:** `impliedVolatility`, `lastPrice` (from options chain data).
7. **External Data Sources Required:** Alpaca Market Data API (Options) or Polygon.io for real-time options pricing.
8. **Priority:** HIGH
9. **Estimated Effort:** 1-2 Weeks
10. **Implementation Notes:** Use the Python library `py_vollib` for Black-Scholes-Merton calculations. Ensure risk-free rate is dynamically pulled from the 3-month Treasury yield (`^IRX`).

## 5. transaction-cost-model (NEW)
1. **Skill Name:** `transaction-cost-model` - Estimates and deducts friction (spread, slippage, fees) from expected edge.
2. **Why BigClaw Needs This:** Eliminates false-positive signals where the theoretical profit is entirely consumed by bid-ask spreads and market impact.
3. **What It Replaces:** N/A (Net new capability).
4. **Detailed Functionality:** For a proposed trade, calculates: 
   * Spread Cost = (Ask - Bid) / Midpoint.
   * Market Impact = (Trade Size / Average Daily Volume) * Volatility Factor.
   * Total Friction = Spread Cost + Market Impact + Broker Fees.
   Rejects trade if Total Friction > 20% of the strategy's historical average trade profit.
5. **Integration Points:** Called by `equity-scoring-engine` before a candidate is sent to the `multi-model-debater`.
6. **yfinance Fields Used:** `bid`, `ask`, `averageVolume`.
7. **External Data Sources Required:** None.
8. **Priority:** HIGH
9. **Estimated Effort:** 3-5 Days
10. **Implementation Notes:** If `bid` or `ask` is 0 or null (common in after-hours yfinance data), fallback to using 0.1% of the `regularMarketPrice` as a default spread penalty.

## 6. equity-scoring-engine (UPGRADE/MERGE)
1. **Skill Name:** `equity-scoring-engine` - Unified 20-dimension scoring system with built-in liquidity screening.
2. **Why BigClaw Needs This:** Centralizes stock evaluation to prevent conflicting signals and filters out illiquid traps.
3. **What It Replaces:** Merges `fundamental-stock-analysis` and `stock-evaluator`.
4. **Detailed Functionality:** 
   * *Liquidity Gate:* Drops stocks where Average Daily Dollar Volume < $10M or Price < $5.
   * *Scoring:* Calculates Value (P/E, FCF yield), Growth (PEG, Rev Growth), Quality (ROIC, Margins), and Momentum (RSI, MACD, 50/200 DMA). Outputs a normalized score 0-100.
5. **Integration Points:** Triggered by `saturday-screener`. Sends top decile candidates to `transaction-cost-model`.
6. **yfinance Fields Used:** `trailingPE`, `forwardPE`, `pegRatio`, `freeCashflow`, `returnOnEquity`, `operatingMargins`, `fiftyDayAverage`, `twoHundredDayAverage`, `averageVolume`.
7. **External Data Sources Required:** None.
8. **Priority:** HIGH
9. **Estimated Effort:** 1 Week
10. **Implementation Notes:** Vectorize this using Pandas. Do not loop through tickers one by one. Download bulk data, apply the liquidity mask first to reduce the dataset, then compute scores.

## 7. backtesting-engine (UPGRADE/MERGE)
1. **Skill Name:** `backtesting-engine` - Unified historical validation with walk-forward analysis.
2. **Why BigClaw Needs This:** Ensures strategies are robust across time, not just curve-fit to a specific historical window.
3. **What It Replaces:** Merges `backtest-expert` and `stock-strategy-backtester`.
4. **Detailed Functionality:** Simulates portfolio performance over historical data. Injects `transaction-cost-model` logic into historical trades. Performs Walk-Forward Optimization (e.g., train on 2018-2020, test on 2021; train on 2019-2021, test on 2022). Outputs Sharpe, Sortino, Max Drawdown, and Win Rate.
5. **Integration Points:** Used by `self-improve` to validate new rules before pushing them to the live IPS.
6. **yfinance Fields Used:** `Open`, `High`, `Low`, `Close`, `Volume`, `Dividends`, `Stock Splits` (Max history).
7. **External Data Sources Required:** None.
8. **Priority:** HIGH
9. **Estimated Effort:** 1 Week
10. **Implementation Notes:** Use `vectorbt` or `Backtrader` as the underlying framework. Ensure survivorship bias is accounted for if possible (though difficult with free yfinance data).

## 8. earnings-event-manager (NEW)
1. **Skill Name:** `earnings-event-manager` - Pre-earnings risk mitigation and position sizing.
2. **Why BigClaw Needs This:** Trailing stops do not work on overnight earnings gaps. Holding full size through earnings is a coin flip, not systematic trading.
3. **What It Replaces:** N/A (Net new capability).
4. **Detailed Functionality:** Scans portfolio daily. If a holding has an earnings date within 3 trading days, it triggers an IPS rule: either reduce position size by 50%, or purchase a protective put option. Post-earnings (Day +1), recalculates `equity-scoring-engine` score and resizes accordingly.
5. **Integration Points:** Alerts `portfolio-risk-manager`. Triggers orders in `live-execution-engine`.
6. **yfinance Fields Used:** `calendar` (specifically the Earnings Date array).
7. **External Data Sources Required:** Earnings Whispers API or Finnhub Earnings Calendar (yfinance earnings dates are sometimes inaccurate).
8. **Priority:** HIGH
9. **Estimated Effort:** 3-5 Days
10. **Implementation Notes:** Build a cron job that runs at 4:00 PM EST to check T+3 earnings dates and execute reduction orders in the after-hours session or at the next day's open.

## 9. macro-factor-monitor (NEW)
1. **Skill Name:** `macro-factor-monitor` - Tracks yield curves, credit spreads, and volatility to determine market health.
2. **Why BigClaw Needs This:** 70% of equity returns are driven by macro factors. Ignoring interest rates and credit markets is flying blind.
3. **What It Replaces:** N/A (Net new capability).
4. **Detailed Functionality:** Pulls daily macro indicators. Calculates:
   * Yield Curve Inversion (10Y minus 2Y Treasury).
   * High Yield Credit Spread (HY OAS).
   * VIX Term Structure (Contango vs Backwardation).
   * US Dollar Index trend.
   Outputs a composite Macro Risk Score (0-100).
5. **Integration Points:** Sole data provider for the `regime-allocation-controller`.
6. **yfinance Fields Used:** `^VIX`, `DX-Y.NYB`, `^TNX`, `^IRX`.
7. **External Data Sources Required:** FRED API (Federal Reserve Economic Data - Free). Series IDs: `T10Y2Y`, `BAMLH0A0HYM2`.
8. **Priority:** HIGH
9. **Estimated Effort:** 1 Week
10. **Implementation Notes:** FRED API is rate-limited but only needs to be called once daily at 5:00 PM EST. Cache the results.

## 10. alpha-decay-tracker (NEW)
1. **Skill Name:** `alpha-decay-tracker` - Measures the predictive power of individual signals over time.
2. **Why BigClaw Needs This:** All alpha decays. If a specific signal (e.g., Insider Buying) stops working, the bot must automatically down-weight it before it causes drawdowns.
3. **What It Replaces:** N/A (Net new capability).
4. **Detailed Functionality:** Tracks the 90-day rolling "Hit Rate" of each of the 20 dimensions in the scoring engine. (e.g., "When RSI < 30 triggered a buy, was the stock higher 5 days later?"). If a signal's hit rate drops below 52%, it automatically reduces that signal's weight in the scoring engine by 50%.
5. **Integration Points:** Modifies the configuration weights used by the `equity-scoring-engine`. Reports to `compliance-auditor`.
6. **yfinance Fields Used:** None directly (uses historical performance data of the bot's own signals).
7. **External Data Sources Required:** Internal database of historical signal triggers and subsequent price action.
8. **Priority:** HIGH
9. **Estimated Effort:** 1 Week
10. **Implementation Notes:** Requires a robust logging schema. Every time a stock is scored, the individual component scores must be saved to a database row alongside the timestamp, so future price action can be joined back to the specific signal.

## 11. afrexai-tax-planning (UPGRADE)
1. **Skill Name:** `afrexai-tax-planning` - Automated Tax-Loss Harvesting (TLH) and wash-sale avoidance.
2. **Why BigClaw Needs This:** Generates 0.5% - 1.5% of "free" after-tax alpha annually by systematically realizing losses to offset gains.
3. **What It Replaces:** Upgrades the existing theoretical tax planner into an active execution module.
4. **Detailed Functionality:** Scans live portfolio daily. Identifies tax lots with unrealized losses > $100 or > 5%. Checks if a wash sale was triggered in the last 30 days. If clear, sells the losing position and immediately buys a highly correlated proxy ETF (e.g., sell XOM, buy VDE) to maintain market exposure. Logs the realized loss.
5. **Integration Points:** Reads lots from `live-execution-engine`. Sends proxy buy/sell orders.
6. **yfinance Fields Used:** None directly.
7. **External Data Sources Required:** Alpaca API (specifically the `/positions` endpoint with `tax_lot` details).
8. **Priority:** MEDIUM
9. **Estimated Effort:** 1-2 Weeks
10. **Implementation Notes:** Wash sale rules are strict. You must maintain a database table of `sold_tickers` with timestamps, and the `multi-model-debater` must be hard-blocked from approving a buy on any ticker in that table for 31 days.

## 12. performance-attribution (NEW)
1. **Skill Name:** `performance-attribution` - Benchmarks bot performance against passive indices to prove true alpha generation.
2. **Why BigClaw Needs This:** If the bot makes 10% but the S&P 500 makes 15%, the bot is failing. You must separate beta (market returns) from alpha (skill).
3. **What It Replaces:** N/A (Net new capability).
4. **Detailed Functionality:** Calculates daily Net Asset Value (NAV) of the live portfolio. Compares daily returns against SPY (S&P 500) and QQQ (Nasdaq). Calculates Beta, Alpha, Information Ratio, and Tracking Error. Generates a weekly tear sheet.
5. **Integration Points:** Pulls data from `live-execution-engine`. Pushes tear sheets to `github-pages-reporter`.
6. **yfinance Fields Used:** `Close` (for SPY and QQQ).
7. **External Data Sources Required:** None.
8. **Priority:** MEDIUM
9. **Estimated Effort:** 3-5 Days
10. **Implementation Notes:** Use the `empyrical` Python library (maintained by Quantopian alumni) to calculate institutional-grade risk and performance metrics easily. Ensure cash drag is accounted for in the NAV calculation.

---

### GPT-5.4

# BigClaw Full Skill Specification and Rationalization Blueprint
**Date:** 2026-04-01  
**Purpose:** Implementation-ready specification for BigClaw’s next-generation skill stack, including:
- all **new skills required**
- all **existing skills that must be upgraded**
- all **existing skills to remove**
- all **existing skills to keep as-is**

This document assumes the current BigClaw architecture includes:
- 7 IPS-driven portfolios
- 20-dimension scoring engine
- paper trading via Alpaca
- trailing stop checks every 15 minutes
- Saturday screening cycle
- weekly compliance audit
- multi-signal fusion using fundamentals, sentiment, dark pool, insider, institutional flow
- observability stack
- self-improvement / self-vetting skills

Because the exact 27-skill inventory was not pasted in full, I am using the names explicitly referenced in the assessment plus the clearly implied existing skills from BigClaw’s architecture. Where a current skill name is inferred, it is labeled as such and should be matched against the actual registry during implementation.

---

# SECTION 1 — CURRENT SKILL DISPOSITION MATRIX

Below is the recommended disposition of the current 27-skill estate.

## A. REMOVE
These should be fully retired, with logic migrated where appropriate.

### 1. `stock-evaluator`
- **Status:** REMOVE
- **Reason:** Overlaps with `fundamental-stock-analysis` and likely duplicates factor scoring already performed in the main decision engine.
- **Replacement:** Merge functionality into upgraded `equity-scoring-engine` (see upgraded spec under `fundamental-stock-analysis`).

### 2. `stock-strategy-backtester`
- **Status:** REMOVE
- **Reason:** Duplicative with `backtest-expert`.
- **Replacement:** Unified upgraded `backtesting-engine`.

### 3. Duplicate X/Twitter sentiment tracker entry
- **Status:** REMOVE
- **Reason:** Assessment indicates likely duplication between `realtime-x-sentiment-tracker` and a separately listed X sentiment capability.
- **Replacement:** Keep one canonical `realtime-x-sentiment-tracker` implementation.

---

## B. UPGRADE
These skills are useful but incomplete and need substantial enhancement.

### 4. `fundamental-stock-analysis` → upgrade into `equity-scoring-engine`
### 5. `sector-analyst`
### 6. `intellectia-stock-forecast`
### 7. `portfolio-manager`
### 8. `afrexai-portfolio-risk`
### 9. `market-environment-analysis`
### 10. `us-market-bubble-detector`
### 11. `options-strategy-advisor`
### 12. `afrexai-tax-planning`
### 13. `backtest-expert`
### 14. `realtime-x-sentiment-tracker`
### 15. `compliance-auditor` *(inferred from weekly compliance audit capability)*
### 16. `candidate-screener` *(inferred from Saturday screener capability)*
### 17. `trailing-stop-manager` *(inferred from 15-minute stop refresh capability)*
### 18. `dark-pool-analyzer` *(inferred from Unusual Whales integration)*
### 19. `insider-flow-monitor` *(inferred from insider signal integration)*
### 20. `institutional-flow-monitor` *(inferred from institutional flow integration)*
### 21. `paper-trading-executor` *(inferred from Alpaca paper trading operations)*
### 22. `reporting-engine` *(inferred from GitHub Pages / reporting stack)*
### 23. `skill-vetter`
### 24. `self-improve-orchestrator`

---

## C. KEEP AS-IS
These appear to be useful and do not require architectural changes beyond standard maintenance.

### 25. `uptime-monitoring`
- **Status:** KEEP AS-IS
- **Reason:** Uptime Kuma / observability function already fit for purpose.

### 26. `log-analyzer`
- **Status:** KEEP AS-IS
- **Reason:** Provides operational diagnostics; no direct investment logic deficiencies identified.

### 27. `slack-discord-alerting`
- **Status:** KEEP AS-IS
- **Reason:** Notification layer is valuable and already integrated into ops and audit workflows.

---

# SECTION 2 — NEW SKILLS REQUIRED (FULL DETAILED SPECS)

---

## NEW SKILL 1 — `live-execution-engine`
**One-line description:** Executes approved live trades through Alpaca with slippage tracking, order-state management, and full auditability.

### 1. Why BigClaw Needs This
BigClaw currently validates strategies in paper mode only. That is insufficient to measure:
- real slippage
- fill quality
- partial fills
- execution latency
- spread capture or spread leakage
- live liquidity constraints

Without this skill, BigClaw cannot know whether its paper alpha survives contact with the market. This directly affects realized returns and can materially understate risk.

### 2. What It Replaces
- Upgrades/replaces portions of `paper-trading-executor`
- Does **not** replace the decision engine; it sits downstream from it

### 3. Detailed Functionality
#### Core responsibilities
1. Receive trade intents from the decision engine:
   - symbol
   - side
   - quantity or dollar target
   - limit/market preference
   - strategy/portfolio ID
   - confidence score
   - expected holding period
   - decision timestamp
2. Validate order eligibility:
   - market open/close status
   - buying power
   - portfolio exposure limits
   - compliance pre-check
   - liquidity gate
   - circuit breaker state
3. Construct order:
   - market order
   - limit order
   - stop order
   - stop-limit order
   - bracket order where allowed
4. Submit to Alpaca live account
5. Monitor order lifecycle:
   - new
   - accepted
   - partially filled
   - filled
   - canceled
   - expired
   - rejected
6. Capture execution-quality metrics:
   - decision price
   - quote mid at submission
   - bid/ask at submission
   - fill price(s)
   - delay from signal to order
   - delay from order to fill
   - slippage in bps and $
7. Persist all events into order ledger and audit store
8. Feed realized execution quality back into:
   - transaction cost model
   - portfolio analytics
   - alpha decay tracker
   - reporting engine

#### Inputs
- Approved trade instruction from decision engine
- Real-time market quotes
- Portfolio positions/state
- Account buying power and restrictions
- Compliance approval token
- Circuit breaker state
- Liquidity and transaction-cost estimates

#### Outputs
- Execution result event
- Order lifecycle status events
- Fill records
- Slippage metrics
- Failed/rejected order alerts
- Daily execution-quality summary

#### Data model
Key tables/collections:
- `trade_intents`
- `orders`
- `fills`
- `execution_metrics`
- `order_exceptions`
- `broker_account_snapshots`

#### State transitions
- `APPROVED_INTENT -> ORDER_CREATED -> ORDER_SUBMITTED -> PARTIAL_FILL/FILLED/CANCELLED/REJECTED`

### 4. Integration Points
- **Decision engine:** Receives approved target trades only
- **Compliance:** Requires pre-trade compliance approval and logs post-trade audit trail
- **Screener:** No direct integration
- **Reporting:** Sends execution reports and slippage analysis
- **Portfolio manager:** Updates position inventory and cash
- **Circuit breaker:** Blocks execution if in halted state
- **Transaction cost model:** Uses realized fill quality to calibrate estimates

### 5. yfinance Fields Used
Primary execution should use broker market data where possible, but if yfinance is fallback:
- `regularMarketPrice`
- `bid`
- `ask`
- `averageVolume`
- `volume`
- `marketCap`

### 6. External Data Sources Required
- Alpaca Trading API (live account)
- Alpaca Market Data API or equivalent quote feed
- Exchange trading calendar (via Alpaca or pandas-market-calendars)

### 7. Priority
**Critical**

### 8. Estimated Effort
**1–2 weeks**

### 9. Implementation Notes
- Use idempotent order submission to avoid duplicate trades on retries
- Persist client order IDs before API submission
- Build reconciliation task to compare internal ledger vs Alpaca account state every 5 minutes during market hours
- Support dry-run mode and shadow-live mode before enabling real capital
- Start with one portfolio only
- Capture all prices in UTC timestamped form with quote source metadata

---

## NEW SKILL 2 — `portfolio-correlation-engine`
**One-line description:** Measures and constrains intra-portfolio correlation and concentration before trades are approved.

### 1. Why BigClaw Needs This
A portfolio of individually attractive stocks may still behave like a single concentrated bet. This increases drawdowns, sector concentration, and factor fragility. Correlation-aware construction improves Sharpe and lowers tail risk.

### 2. What It Replaces
- New capability; partially complements `afrexai-portfolio-risk` and `portfolio-manager`

### 3. Detailed Functionality
#### Core responsibilities
1. Build rolling return series for all held and candidate symbols
2. Compute:
   - pairwise correlations
   - average portfolio correlation
   - candidate marginal correlation impact
   - sector/factor clustering
   - concentration metrics (HHI, top-3 exposure, top-sector exposure)
3. Enforce IPS-specific thresholds such as:
   - max average pairwise correlation
   - max correlation to any existing top position
   - max sector concentration
4. Simulate post-trade portfolio correlation profile before order approval
5. Return:
   - approve
   - approve with reduced size
   - reject
6. Flag hidden correlation via proxies:
   - same sector
   - same factor style
   - high beta cohort
   - thematic concentration (AI, semis, EV, crypto sensitivity, etc.)

#### Inputs
- Candidate symbol
- Existing portfolio holdings and weights
- Daily adjusted close history
- Sector/industry metadata
- Optional factor bucket labels

#### Outputs
- Correlation matrix
- Candidate marginal risk score
- Post-trade average correlation
- Approval recommendation
- Position size haircut recommendation

#### Calculation standards
- Default lookback: 90 trading days
- Secondary lookbacks: 30, 180
- Use daily log returns
- Minimum history requirement: 60 valid observations
- Handle missing data by pairwise alignment

### 4. Integration Points
- **Decision engine:** Mandatory gate before buy approval
- **Compliance:** Logs rule-based rejection reasons
- **Screener:** Optionally excludes highly correlated candidate clusters
- **Reporting:** Weekly portfolio diversification report
- **Portfolio manager:** Adjusts target sizing

### 5. yfinance Fields Used
- Historical `Adj Close` or `Close`
- `sector` *(often via info metadata)*
- `industry`
- `beta`
- `marketCap`

### 6. External Data Sources Required
- yfinance historical OHLCV
- Optional ETF/factor proxy datasets for enhanced clustering
- Optional SEC or company metadata source for sector normalization

### 7. Priority
**Critical**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- Cache historical returns locally; do not repeatedly hit yfinance intraday
- Normalize sector names across sources
- Include fallback logic for insufficient history
- Portfolio-level constraints should be configurable per IPS

---

## NEW SKILL 3 — `regime-allocation-controller`
**One-line description:** Converts market regime signals into portfolio exposure, cash allocation, and strategy weighting changes.

### 1. Why BigClaw Needs This
If BigClaw detects bearish conditions but remains fully exposed, regime detection has no economic value. This skill turns macro/market intelligence into actionable allocation changes, reducing drawdowns and improving risk-adjusted returns.

### 2. What It Replaces
- New control-layer capability
- Operationalizes outputs from `market-environment-analysis` and `us-market-bubble-detector`

### 3. Detailed Functionality
#### Core responsibilities
1. Ingest regime inputs from:
   - market environment analysis
   - bubble detector
   - macro factor monitor
   - volatility indicators
   - breadth indicators
2. Map combined inputs into discrete regimes:
   - `BULL`
   - `NEUTRAL`
   - `BEAR`
   - `CRISIS`
3. For each IPS portfolio define:
   - target gross exposure
   - max new positions per day
   - max position size
   - stop tightness multiplier
   - cash floor
   - options allowed/not allowed
4. Apply allocation overlays:
   - scale target sizes
   - tighten entry thresholds in BEAR/CRISIS
   - widen cash holdings
   - optionally shift to defensive sectors
5. Publish regime state changes and rationale
6. Prevent excessive regime flipping through hysteresis rules

#### Inputs
- Daily and intraday regime signals
- Portfolio IPS configuration
- Current exposures and positions
- Volatility and macro indicators

#### Outputs
- Regime label
- Exposure multiplier
- Position size multiplier
- Trading posture instructions
- Regime transition alerts

#### Example mapping
- `BULL`: 100% target risk budget
- `NEUTRAL`: 70%
- `BEAR`: 40%
- `CRISIS`: 0–20%

### 4. Integration Points
- **Decision engine:** Applies overlay before final order generation
- **Compliance:** Enforces IPS regime rules
- **Screener:** May change candidate thresholds by regime
- **Reporting:** Shows regime history vs performance
- **Portfolio manager:** Uses adjusted target exposure

### 5. yfinance Fields Used
- `^GSPC`, `^VIX`, `^IXIC`, sector ETFs historical data
- Historical `Close`, `Volume`
- `beta` if needed for portfolio adjustment

### 6. External Data Sources Required
- FRED API
- yfinance market index data
- Optional CBOE or macro feeds

### 7. Priority
**Critical**

### 8. Estimated Effort
**1–2 weeks**

### 9. Implementation Notes
- Use smoothing/hysteresis to avoid whipsaws
- Regime change should not necessarily trigger forced full turnover
- Persist regime snapshots for backtesting and attribution

---

## NEW SKILL 4 — `portfolio-drawdown-circuit-breaker`
**One-line description:** Monitors portfolio-level losses and halts or de-risks trading when drawdown thresholds are breached.

### 1. Why BigClaw Needs This
Position-level stops do not prevent cascading portfolio-level losses during broad market dislocations or correlated selloffs. A circuit breaker is a capital-preservation mechanism.

### 2. What It Replaces
- New capability complementary to `trailing-stop-manager`

### 3. Detailed Functionality
#### Core responsibilities
1. Monitor intraday and end-of-day P&L:
   - per portfolio
   - aggregate account
2. Track thresholds:
   - daily loss %
   - weekly loss %
   - monthly drawdown %
   - peak-to-trough drawdown %
3. Trigger actions:
   - block new buys
   - reduce open exposure by configured percentage
   - force move to cash
   - pause options trading
   - require manual unlock for severe breaches
4. Distinguish causes:
   - broad market drawdown
   - single position gap
   - execution failure
   - data anomaly
5. Create incident record and push urgent alert

#### Inputs
- Real-time portfolio valuation
- Position-level P&L
- Realized/unrealized losses
- Current regime state
- IPS threshold configuration

#### Outputs
- Circuit breaker state: `NORMAL`, `WARNING`, `LIMITED`, `HALTED`
- Trigger event log
- Automated trade restrictions
- Alerts and incident reports

### 4. Integration Points
- **Decision engine:** Hard gate; blocks new trades if halted
- **Compliance:** Mandatory logging of threshold breach
- **Screener:** No direct effect
- **Reporting:** Drawdown incidents and recovery timelines
- **Execution engine:** May submit liquidation orders

### 5. yfinance Fields Used
Not primary. Portfolio valuation should use broker and internal mark data.

### 6. External Data Sources Required
- Alpaca account/positions
- Broker quote feed
- Internal NAV store

### 7. Priority
**Critical**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Include debounce logic to avoid triggering on bad ticks
- Require confirmed valuation across two successive intervals before full halt
- Manual override must be authenticated and logged

---

## NEW SKILL 5 — `greeks-engine`
**One-line description:** Calculates option Greeks and portfolio-level options risk exposures in real time.

### 1. Why BigClaw Needs This
Options exposure without Greeks management is unmanaged leverage. This skill is required before any systematic options deployment beyond advisory research.

### 2. What It Replaces
- New risk capability augmenting `options-strategy-advisor`

### 3. Detailed Functionality
#### Core responsibilities
1. For every options position calculate:
   - delta
   - gamma
   - theta
   - vega
   - rho
   - implied volatility
2. Aggregate by:
   - symbol
   - strategy
   - portfolio
   - account
3. Enforce IPS limits:
   - max portfolio net delta
   - max gamma near expiration
   - max daily theta decay
   - max vega exposure
4. Perform scenario analysis:
   - underlying ±1%, ±3%, ±5%
   - IV shock ±5 vol points
   - 1-day theta decay
5. Generate early warning alerts for:
   - pin risk
   - expiration proximity
   - assignment risk
   - concentrated short gamma

#### Inputs
- Options contract details
- Underlying price
- time to expiry
- strike
- contract type
- risk-free rate
- dividend yield estimate
- implied or historical vol

#### Outputs
- Contract-level Greeks
- Portfolio Greeks exposure
- Risk breach alerts
- Strategy suitability score

### 4. Integration Points
- **Decision engine:** Approves/blocks options trades
- **Compliance:** Records exposure against IPS limits
- **Screener:** Can support options overlays on screened names
- **Reporting:** Daily options risk dashboard
- **Execution engine:** Must receive allowed quantity limits

### 5. yfinance Fields Used
- Underlying historical `Close`
- `regularMarketPrice`
- options chains where available
- `dividendRate`
- `dividendYield`
- Treasury proxy from market data if not external

### 6. External Data Sources Required
- yfinance options chain data
- `py_vollib` or `QuantLib`
- FRED Treasury rate series or broker rates
- Optional Polygon/Tradier for better options chain quality

### 7. Priority
**High**

### 8. Estimated Effort
**1–2 weeks**

### 9. Implementation Notes
- yfinance options data can be incomplete; for production, use a dedicated options feed if possible
- Ensure consistent contract symbology parsing
- Greeks refresh frequency should be higher near expiration

---

## NEW SKILL 6 — `transaction-cost-model`
**One-line description:** Estimates spread, slippage, and liquidity costs before trade execution and feeds realized costs back into strategy evaluation.

### 1. Why BigClaw Needs This
A strategy with weak edge can be made unprofitable by friction. This skill prevents false-positive trades and aligns paper expectations with live results.

### 2. What It Replaces
- New capability augmenting execution and backtesting

### 3. Detailed Functionality
#### Core responsibilities
1. Estimate pre-trade:
   - half-spread cost
   - expected slippage
   - participation-rate impact
   - volatility-adjusted execution risk
   - opening/closing auction risk
2. Compute total expected cost in:
   - cents/share
   - basis points
   - dollars
3. Compare expected cost to expected edge
4. Reject or resize trades if cost/edge ratio exceeds IPS threshold
5. Update estimates using actual fill outcomes from `live-execution-engine`

#### Inputs
- Symbol
- side
- target quantity
- bid/ask
- intraday spread
- average daily volume
- volatility
- order type
- time of day
- recent execution history

#### Outputs
- Pre-trade cost estimate
- Cost/edge ratio
- order-type recommendation
- reject/approve/resize instruction

### 4. Integration Points
- **Decision engine:** Adjusts expected return and approval
- **Compliance:** Logs economic reason for rejection
- **Screener:** Can filter structurally expensive names
- **Reporting:** Cost attribution by portfolio and symbol
- **Backtesting:** Applies realistic friction assumptions

### 5. yfinance Fields Used
- `bid`
- `ask`
- `averageVolume`
- `volume`
- historical OHLCV
- `regularMarketPrice`

### 6. External Data Sources Required
- Alpaca quotes/trades preferred
- yfinance for fallback/reference
- Internal realized execution database

### 7. Priority
**High**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Do not rely on stale yfinance bid/ask intraday for live execution decisions if broker quotes are available
- Build calibration loop using actual fills by symbol bucket and time bucket

---

## NEW SKILL 7 — `earnings-event-risk-manager`
**One-line description:** Identifies earnings-related gap risk and applies pre/post-event position management rules.

### 1. Why BigClaw Needs This
Overnight earnings gaps bypass trailing stops. Managing event risk directly reduces sudden large losses and stabilizes portfolio volatility.

### 2. What It Replaces
- New capability

### 3. Detailed Functionality
1. Maintain earnings calendar for:
   - held positions
   - top candidates
2. Flag windows:
   - T-5 to T+2 trading days around earnings
3. Apply IPS-specific actions:
   - reduce position size
   - suspend new entries
   - prohibit short premium strategies
   - allow hedges only
4. After earnings:
   - evaluate gap direction
   - compare result to expectations
   - remove temporary restrictions after stabilization
5. Log earnings event outcomes for later signal analysis

#### Inputs
- Earnings dates/times
- Position inventory
- Option hedge availability
- implied volatility if using options

#### Outputs
- Event risk flags
- Position adjustment recommendations
- automated order intents if enabled
- post-event review records

### 4. Integration Points
- **Decision engine:** Blocks or modifies trades around earnings
- **Compliance:** Ensures event handling aligns with IPS
- **Screener:** Excludes names too close to earnings if configured
- **Reporting:** Earnings risk calendar and event outcomes

### 5. yfinance Fields Used
- `earningsDate` where available
- historical earnings surprises if available
- options chain / implied vol proxies if used

### 6. External Data Sources Required
- yfinance
- Earnings Whispers or equivalent calendar source
- SEC 8-K / IR websites for confirmation if needed

### 7. Priority
**High**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Always normalize timezone and “before open / after close”
- Earnings dates shift; refresh daily

---

## NEW SKILL 8 — `macro-factor-monitor`
**One-line description:** Tracks macro variables that materially affect equity risk and feeds them into regime and allocation logic.

### 1. Why BigClaw Needs This
Macro conditions drive cross-asset risk appetite and can overwhelm stock-specific signals. This skill improves market timing, drawdown control, and style allocation.

### 2. What It Replaces
- New capability complementing `market-environment-analysis`

### 3. Detailed Functionality
Track and score:
- 10Y Treasury yield
- 2Y Treasury yield
- 10Y–2Y spread
- Fed funds rate
- CPI trend
- unemployment trend
- HY OAS / credit spreads
- DXY
- VIX level and term structure
- oil shock indicator
- recession proxy score

Produce:
- standardized z-scores
- composite macro risk score
- macro regime labels
- directional implications for growth/value/risk-on/risk-off

### 4. Integration Points
- **Decision engine:** Adds macro context to expected return/risk
- **Compliance:** Logs rationale for regime shifts
- **Screener:** Can bias toward defensive or cyclical sectors
- **Reporting:** Macro dashboard and trend history
- **Regime allocation controller:** Primary upstream dependency

### 5. yfinance Fields Used
- `^VIX`
- `DX-Y.NYB`
- `^TNX`
- market index historical prices

### 6. External Data Sources Required
- FRED API
- yfinance
- Optional CBOE term structure data

### 7. Priority
**High**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- Use cached daily updates; macro data does not need high-frequency refresh
- Build revision-aware handling for FRED series

---

## NEW SKILL 9 — `alpha-decay-tracker`
**One-line description:** Measures ongoing predictive power of each signal and automatically downweights decaying alpha sources.

### 1. Why BigClaw Needs This
Signals degrade over time. Without measurement, BigClaw can continue trusting stale indicators and lose edge gradually without a clear failure point.

### 2. What It Replaces
- New capability

### 3. Detailed Functionality
1. For every signal dimension:
   - store daily signal value at decision time
   - store subsequent realized return over defined horizons (1d, 5d, 20d)
2. Compute rolling performance:
   - hit rate
   - information coefficient
   - return spread top decile vs bottom decile
   - contribution to portfolio P&L
3. Detect degradation:
   - below-threshold hit rate
   - declining IC
   - unstable sign flips
4. Publish suggested weights:
   - unchanged
   - reduced
   - quarantined
5. Maintain signal-change audit log

### 4. Integration Points
- **Decision engine:** Receives updated signal weights
- **Compliance:** Approves or records auto-weight changes
- **Screener:** Uses adjusted factor weights
- **Reporting:** Weekly alpha health report
- **Self-improve orchestrator:** Can propose retraining or replacement

### 5. yfinance Fields Used
- Historical price returns only

### 6. External Data Sources Required
- Internal signal history database
- Market price history from yfinance or broker feed

### 7. Priority
**High**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- Must timestamp signals exactly as generated to prevent lookahead bias
- Separate by regime where possible; a signal may be valid only in some conditions

---

## NEW SKILL 10 — `liquidity-screener`
**One-line description:** Filters out illiquid names and right-sizes trades based on tradability constraints.

### 1. Why BigClaw Needs This
Illiquid names create hidden execution risk, poor fills, and exit bottlenecks, especially on a small automated system without advanced routing.

### 2. What It Replaces
- New gate capability; may also be folded into upgraded `candidate-screener`

### 3. Detailed Functionality
1. Calculate:
   - average daily volume
   - average daily dollar volume
   - spread %
   - days-to-liquidate at target participation rate
2. Enforce minimums:
   - ADV threshold
   - dollar volume threshold
   - spread ceiling
   - max participation rate
3. Produce allowed max position size by symbol

### 4. Integration Points
- **Decision engine:** Hard gate
- **Compliance:** Logs rejection reasons
- **Screener:** Applied early to reduce low-quality candidates
- **Reporting:** Liquidity exceptions report

### 5. yfinance Fields Used
- `averageVolume`
- `volume`
- `bid`
- `ask`
- `regularMarketPrice`
- historical volume

### 6. External Data Sources Required
- yfinance
- broker quote feed preferred for real-time spread

### 7. Priority
**High**

### 8. Estimated Effort
**1 day**

### 9. Implementation Notes
- Use average daily dollar volume, not just share volume
- Consider excluding names under $5 if IPS permits

---

## NEW SKILL 11 — `performance-attribution-engine`
**One-line description:** Measures portfolio performance relative to benchmarks and decomposes returns into allocation, selection, cost, and timing effects.

### 1. Why BigClaw Needs This
Absolute returns are misleading. This skill answers whether BigClaw is generating alpha or simply benefiting from market direction.

### 2. What It Replaces
- New capability augmenting `reporting-engine`

### 3. Detailed Functionality
1. Track daily NAV and benchmark NAV
2. Compute:
   - absolute return
   - excess return
   - alpha/beta
   - Sharpe, Sortino, max DD
   - information ratio
3. Attribute performance by:
   - sector allocation
   - security selection
   - timing
   - execution cost drag
   - cash drag
4. Support portfolio-specific benchmarks:
   - SPY
   - QQQ
   - IWM
   - sector ETF
   - custom blend

### 4. Integration Points
- **Decision engine:** Feedback loop into strategy adjustments
- **Compliance:** Benchmark appropriateness review
- **Screener:** No direct dependency
- **Reporting:** Primary downstream consumer

### 5. yfinance Fields Used
- Benchmark historical prices
- held security historical prices

### 6. External Data Sources Required
- yfinance
- internal portfolio NAV data

### 7. Priority
**High**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- Store end-of-day NAV snapshots immutably
- Use total return benchmark approximation where possible

---

## NEW SKILL 12 — `tax-loss-harvesting-automation`
**One-line description:** Automates taxable-account loss harvesting while respecting wash-sale and replacement-security rules.

### 1. Why BigClaw Needs This
Tax alpha materially improves after-tax returns in taxable accounts without changing market exposure much.

### 2. What It Replaces
- Functional expansion of `afrexai-tax-planning`

### 3. Detailed Functionality
1. Track lot-level cost basis
2. Detect harvestable losses:
   - absolute threshold
   - percentage threshold
   - time-since-purchase threshold
3. Check wash-sale windows
4. Suggest or execute replacement securities
5. Record harvested loss, replacement rationale, and wash-sale watchlist

### 4. Integration Points
- **Decision engine:** Can generate tax-aware sell/swap recommendations
- **Compliance:** Wash-sale and account-type checks
- **Reporting:** Tax alpha summary
- **Portfolio manager:** Maintains exposure continuity

### 5. yfinance Fields Used
- Historical prices for replacements
- correlations for proxy replacements

### 6. External Data Sources Required
- Broker tax lot data
- internal lot ledger
- IRS wash-sale rules encoding

### 7. Priority
**Medium**

### 8. Estimated Effort
**1–2 weeks**

### 9. Implementation Notes
- Must be account-specific
- Do not enable auto-execution before lot reconciliation is fully trustworthy

---

# SECTION 3 — EXISTING SKILLS TO UPGRADE (FULL DETAILED SPECS)

---

## UPGRADE 1 — `fundamental-stock-analysis` → canonical `equity-scoring-engine`
**One-line description:** Centralized multi-factor equity scoring engine combining fundamentals, quality, growth, valuation, momentum, and signal fusion.

### 1. Why BigClaw Needs This
Current overlap among `fundamental-stock-analysis`, `stock-evaluator`, and possibly `intellectia-stock-forecast` creates duplicated logic, inconsistent scores, and maintenance burden. A canonical scoring engine improves signal consistency and auditability.

### 2. What It Replaces
- Replaces `stock-evaluator`
- Absorbs core responsibilities of `fundamental-stock-analysis`
- Integrates selected outputs from `intellectia-stock-forecast`
- Works alongside `sector-analyst`

### 3. Detailed Functionality
#### Factor groups
- Value: P/E, forward P/E, EV/EBITDA proxy if available, P/S, P/B, FCF yield proxy
- Growth: revenue growth, earnings growth, forward growth estimates
- Quality: ROE, margins, debt metrics, cash flow stability
- Momentum: 1m, 3m, 6m, 12m relative performance
- Risk: beta, volatility, max drawdown history
- Sentiment/flow overlays: dark pool, insider, institutional, social sentiment
- Event-risk overlays: earnings proximity, macro regime sensitivity
- Liquidity and cost overlays

#### Processing
1. Fetch and normalize raw data
2. Winsorize/extreme-value cap
3. Convert factors to standardized scores
4. Apply IPS-specific weights
5. Generate:
   - overall score
   - factor-subscore vector
   - approval confidence
   - rationale text

#### Inputs
- Financial statement and market data
- sector-relative normalization groups
- external alternative signals
- IPS weight configuration

#### Outputs
- normalized factor table
- composite score
- rank order
- pass/fail against gates
- explanation metadata

### 4. Integration Points
- **Decision engine:** Primary upstream security ranking source
- **Compliance:** Stores scoring rationale for every approved trade
- **Screener:** Uses it as ranking engine
- **Reporting:** Displays factor attribution and score drift

### 5. yfinance Fields Used
Likely includes:
- `marketCap`
- `trailingPE`
- `forwardPE`
- `priceToBook`
- `priceToSalesTrailing12Months`
- `enterpriseToEbitda` *(if available)*
- `returnOnEquity`
- `profitMargins`
- `operatingMargins`
- `grossMargins`
- `debtToEquity`
- `currentRatio`
- `quickRatio`
- `freeCashflow`
- `operatingCashflow`
- `revenueGrowth`
- `earningsGrowth`
- `earningsQuarterlyGrowth`
- `targetMeanPrice`
- `beta`
- `averageVolume`
- OHLCV history

### 6. External Data Sources Required
- yfinance
- SEC filings / sec-api / EDGAR parser for validation and richer fields
- optional Financial Modeling Prep / Alpha Vantage if needed for redundancy

### 7. Priority
**Critical**

### 8. Estimated Effort
**1–2 weeks**

### 9. Implementation Notes
- Make this the single source of truth for stock scoring
- Every factor should have source, timestamp, and fallback behavior
- Separate raw ingestion from scoring logic

---

## UPGRADE 2 — `sector-analyst`
**One-line description:** Sector-relative scoring and top-down sector regime overlay for security selection.

### 1. Why BigClaw Needs This
Sector context matters. A strong stock in a weak sector often underperforms; likewise sector momentum and macro sensitivity influence risk concentration.

### 2. What It Replaces
- Upgrade only; not removed

### 3. Detailed Functionality
1. Track sector ETF relative strength
2. Evaluate sector breadth, valuation, momentum, and macro sensitivity
3. Map individual stocks to sectors and industries
4. Adjust equity scores by sector attractiveness and concentration
5. Provide sector caps and preferred/avoid lists by regime

### 4. Integration Points
- **Decision engine:** Adds top-down overlay
- **Compliance:** Enforces sector exposure caps
- **Screener:** Prioritizes candidate generation by sector
- **Reporting:** Sector contribution and exposure charts

### 5. yfinance Fields Used
- sector ETF OHLCV (XLK, XLF, XLE, XLV, etc.)
- stock `sector`, `industry`
- stock historical prices

### 6. External Data Sources Required
- yfinance
- optional GICS mapping source if yfinance metadata inconsistent

### 7. Priority
**High**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Standardize sector taxonomy
- Allow IPS-specific sector max/min rules

---

## UPGRADE 3 — `intellectia-stock-forecast`
**One-line description:** ML/forecast overlay producing directional probability and confidence, used only as a secondary signal.

### 1. Why BigClaw Needs This
If this skill adds non-duplicate predictive value, it should remain, but only as a controlled overlay. It must not conflict opaquely with the canonical scoring engine.

### 2. What It Replaces
- Upgrade only
- No longer allowed to act as an independent final recommender

### 3. Detailed Functionality
1. Produce forecast horizons:
   - 1 day
   - 5 day
   - 20 day
2. Return:
   - expected direction
   - confidence
   - expected move range
3. Track realized calibration and alpha contribution
4. Feed into alpha-decay tracker

### 4. Integration Points
- **Decision engine:** Secondary feature, weighted by current forecast reliability
- **Compliance:** Requires explainability metadata
- **Screener:** Optional tie-breaker among similarly ranked names
- **Reporting:** Forecast calibration chart

### 5. yfinance Fields Used
- OHLCV history
- benchmark/index histories

### 6. External Data Sources Required
- Internal ML model endpoint or external forecast API if currently used

### 7. Priority
**Medium**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- If no measurable incremental alpha after 90 days, retire it
- Must be versioned and calibration-tested

---

## UPGRADE 4 — `portfolio-manager`
**One-line description:** Portfolio construction, target sizing, rebalancing, and position lifecycle management.

### 1. Why BigClaw Needs This
Current portfolio management appears insufficiently connected to correlation, risk, regime, and cost. It must become the central allocator rather than a simple position book.

### 2. What It Replaces
- Upgraded and tightly integrated with `afrexai-portfolio-risk`

### 3. Detailed Functionality
1. Maintain per-portfolio:
   - target holdings count
   - target weights
   - cash level
   - turnover budget
   - position age
2. Construct and rebalance using:
   - score rank
   - regime overlay
   - correlation limits
   - transaction costs
   - liquidity limits
   - tax implications
3. Support:
   - equal weight
   - conviction weight
   - volatility-adjusted weight
   - capped weight
4. Manage position lifecycle:
   - open
   - add
   - trim
   - exit
   - replace

### 4. Integration Points
- **Decision engine:** Consumes ranked candidates and constraints
- **Compliance:** Ensures IPS conformity
- **Screener:** Receives eligible ranked names
- **Reporting:** Position changes, turnover, exposure stats

### 5. yfinance Fields Used
- price history
- beta
- volume
- averageVolume

### 6. External Data Sources Required
- Internal portfolio state
- broker positions/cash

### 7. Priority
**Critical**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- Separate target portfolio from actual holdings for reconciliation
- Every rebalance decision should include reason codes

---

## UPGRADE 5 — `afrexai-portfolio-risk`
**One-line description:** Unified portfolio risk analytics including volatility, drawdown, VaR-style metrics, exposure limits, and scenario stress.

### 1. Why BigClaw Needs This
Risk analytics exist, but they need to become first-class controls tied directly to portfolio construction and execution.

### 2. What It Replaces
- Upgrade only; functions in tandem with `portfolio-correlation-engine` and circuit breaker

### 3. Detailed Functionality
1. Compute:
   - portfolio volatility
   - rolling drawdown
   - VaR / expected shortfall approximation
   - beta to benchmark
   - sector/factor exposures
   - concentration risk
2. Run stress tests:
   - SPY -5%
   - sector shock
   - volatility spike
   - rates shock
3. Publish limit breaches and sizing recommendations

### 4. Integration Points
- **Decision engine:** Hard constraints
- **Compliance:** Risk policy evidence
- **Reporting:** Portfolio risk dashboard
- **Execution engine:** Caps exposure

### 5. yfinance Fields Used
- historical prices
- sector mappings
- beta

### 6. External Data Sources Required
- broker holdings
- benchmark price histories

### 7. Priority
**Critical**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- Persist daily risk snapshots for backtesting and governance

---

## UPGRADE 6 — `market-environment-analysis`
**One-line description:** Detects current market condition using breadth, trend, volatility, and internals.

### 1. Why BigClaw Needs This
Useful now, but must become structured and machine-consumable by `regime-allocation-controller`.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Evaluate:
   - index trend state
   - breadth
   - realized volatility
   - momentum breadth
   - drawdown state
2. Output standardized regime features and confidence score

### 4. Integration Points
- **Decision engine:** Context input
- **Compliance:** Logs market-state rationale
- **Reporting:** Daily market state summary
- **Regime controller:** Direct upstream input

### 5. yfinance Fields Used
- `^GSPC`, `^IXIC`, `^DJI`, `^RUT`, `^VIX`
- historical OHLCV

### 6. External Data Sources Required
- yfinance
- optional market breadth datasets

### 7. Priority
**High**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Output must be numeric + categorical, not just narrative text

---

## UPGRADE 7 — `us-market-bubble-detector`
**One-line description:** Detects overheating and speculative excess conditions that warrant de-risking or defensive posture.

### 1. Why BigClaw Needs This
Currently likely diagnostic only; needs to become an actionable input to allocation control.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Track:
   - valuation extremes
   - concentration in mega-caps
   - breadth deterioration
   - IPO/speculation proxies
   - margin/speculation proxy signals
2. Output:
   - bubble risk score
   - warning tier
   - recommended exposure cap modifier

### 4. Integration Points
- **Decision engine:** Risk overlay
- **Compliance:** Audit trail for defensive postures
- **Reporting:** Bubble risk trend panel
- **Regime controller:** Input feature

### 5. yfinance Fields Used
- index and mega-cap histories
- sector ETF concentration proxies

### 6. External Data Sources Required
- yfinance
- optional FRED valuation proxies / margin debt series

### 7. Priority
**Medium**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Avoid binary bubble/no-bubble logic; use graduated score

---

## UPGRADE 8 — `options-strategy-advisor`
**One-line description:** Generates options strategy recommendations constrained by Greeks, event risk, and portfolio suitability.

### 1. Why BigClaw Needs This
Currently advisory-only and under-risk-controlled. Must be integrated with Greeks and event management before any execution.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Evaluate strategy suitability:
   - covered call
   - cash-secured put
   - protective put
   - debit spread
   - credit spread
2. Check:
   - Greeks exposure
   - liquidity
   - earnings proximity
   - IV percentile
   - assignment risk
3. Return recommended strikes, expiries, and max size

### 4. Integration Points
- **Decision engine:** Optional strategy overlay
- **Compliance:** Enforces options policy constraints
- **Reporting:** Options rationale report
- **Greeks engine:** Mandatory dependency

### 5. yfinance Fields Used
- options chains
- underlying price
- historical volatility proxy

### 6. External Data Sources Required
- yfinance options data
- better options feed if available

### 7. Priority
**High**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- No autonomous options trading should go live until Greeks engine and earnings manager are active

---

## UPGRADE 9 — `afrexai-tax-planning`
**One-line description:** Tax-aware portfolio analytics and optimization for taxable accounts.

### 1. Why BigClaw Needs This
Useful but incomplete without lot-level optimization and harvest automation.

### 2. What It Replaces
- Upgraded by `tax-loss-harvesting-automation`

### 3. Detailed Functionality
1. Track short/long-term gain status
2. Prioritize tax-efficient lots for sale
3. Forecast tax impact of proposed rebalances
4. Coordinate with TLH module

### 4. Integration Points
- **Decision engine:** Tax-aware sell/trim recommendations
- **Compliance:** Tax rules audit
- **Reporting:** Estimated tax liability and realized savings

### 5. yfinance Fields Used
- prices for estimated gains/losses

### 6. External Data Sources Required
- broker tax lot data
- internal lot ledger

### 7. Priority
**Medium**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- Different behavior for IRA vs taxable accounts

---

## UPGRADE 10 — `backtest-expert` → canonical `backtesting-engine`
**One-line description:** Unified backtesting engine for single-name, portfolio, walk-forward, and Monte Carlo validation with transaction cost realism.

### 1. Why BigClaw Needs This
Current dual backtesting stack risks inconsistent results. A single validated engine is required for strategy trustworthiness.

### 2. What It Replaces
- Replaces `stock-strategy-backtester`

### 3. Detailed Functionality
1. Support:
   - signal-level backtests
   - portfolio backtests
   - walk-forward analysis
   - Monte Carlo resampling
   - regime-segmented evaluation
2. Include:
   - transaction costs
   - slippage assumptions
   - position limits
   - survivorship controls where possible
3. Output robust metrics and audit artifacts

### 4. Integration Points
- **Decision engine:** Validates proposed model changes
- **Compliance:** Evidence for deployment approval
- **Reporting:** Backtest report artifacts
- **Alpha decay tracker:** Historical baseline comparisons

### 5. yfinance Fields Used
- historical OHLCV
- benchmark histories

### 6. External Data Sources Required
- yfinance
- internal signal history
- optional survivorship-bias-controlled data source in future

### 7. Priority
**High**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- Separate research backtests from production-grade validations
- Avoid lookahead bias and signal timestamp leakage

---

## UPGRADE 11 — `realtime-x-sentiment-tracker`
**One-line description:** Social sentiment ingestion and scoring for tradable tickers, with bot/noise filtering and alpha measurement.

### 1. Why BigClaw Needs This
Sentiment can be useful, but only if de-noised and measured for predictive value. It should not remain an ungoverned source of noisy signal.

### 2. What It Replaces
- Deduplicates any duplicate X sentiment entry

### 3. Detailed Functionality
1. Ingest posts mentioning tracked symbols
2. Perform:
   - ticker extraction
   - sentiment classification
   - influencer weighting
   - bot/spam filtering
   - burst detection
3. Produce:
   - sentiment score
   - sentiment momentum
   - unusual attention alert
4. Log performance contribution for alpha decay analysis

### 4. Integration Points
- **Decision engine:** Low-weight alternative signal
- **Compliance:** Content-source logging and retention policy
- **Screener:** Surface names with unusual sentiment acceleration
- **Reporting:** Sentiment heatmaps

### 5. yfinance Fields Used
- none directly beyond ticker metadata

### 6. External Data Sources Required
- X/Twitter API or approved scraping/data provider
- optional Reddit or Stocktwits if extended

### 7. Priority
**Medium**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Must rate-limit and cache aggressively
- Keep sentiment weight low unless empirically validated

---

## UPGRADE 12 — `compliance-auditor`
**One-line description:** Enforces IPS, trading, exposure, and data governance rules before and after trades.

### 1. Why BigClaw Needs This
The weekly compliance audit is strong, but BigClaw also needs near-real-time compliance enforcement and structured exception handling.

### 2. What It Replaces
- Upgrade from weekly-only review to continuous and weekly modes

### 3. Detailed Functionality
1. Pre-trade checks:
   - IPS allowed symbol universe
   - max position size
   - sector limits
   - regime limits
   - liquidity rules
   - earnings blackout rules
2. Post-trade checks:
   - actual fills vs approved size
   - portfolio drift
   - stale data use
   - restricted mode violations
3. Produce weekly audit report plus incident exceptions ledger

### 4. Integration Points
- **Decision engine:** Trade approval token
- **Screener:** IPS candidate eligibility
- **Reporting:** Compliance dashboard
- **Execution engine:** Hard block on violations

### 5. yfinance Fields Used
- sector/industry
- liquidity fields as needed

### 6. External Data Sources Required
- internal rule store
- broker fills
- data freshness metadata

### 7. Priority
**Critical**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- All compliance rules should be declarative/config-driven
- Every violation must include machine-readable reason codes

---

## UPGRADE 13 — `candidate-screener`
**One-line description:** Periodic and on-demand candidate generation pipeline for equities/options opportunities.

### 1. Why BigClaw Needs This
Already useful, but must incorporate liquidity, event, regime, and cost awareness.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Universe filtering
2. Data freshness validation
3. Liquidity screen
4. earnings proximity exclusion
5. sector and macro posture filtering
6. score ranking and shortlist generation

### 4. Integration Points
- **Decision engine:** Primary idea source
- **Compliance:** Universe and IPS checks
- **Reporting:** Weekly candidate report

### 5. yfinance Fields Used
- full scoring and liquidity set

### 6. External Data Sources Required
- yfinance
- earnings calendar source
- alternative signal APIs

### 7. Priority
**High**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Saturday batch remains valid; also support ad hoc reruns after major market events

---

## UPGRADE 14 — `trailing-stop-manager`
**One-line description:** Intraday position protection using dynamic trailing stop logic coordinated with portfolio-level controls.

### 1. Why BigClaw Needs This
Current 15-minute refresh is strong, but stop logic should adapt to volatility, earnings events, and regime state.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Manage stop levels per position using:
   - ATR / volatility
   - regime
   - earnings window
   - profit cushion
2. Prevent stop clustering from causing unnecessary cascades
3. Coordinate with drawdown circuit breaker
4. Log every stop update and trigger rationale

### 4. Integration Points
- **Decision engine:** downstream protection layer
- **Compliance:** Records stop policy adherence
- **Reporting:** Stop hit attribution and effectiveness
- **Execution engine:** Generates exit orders

### 5. yfinance Fields Used
- historical high/low/close
- intraday quote source preferred

### 6. External Data Sources Required
- broker quotes
- internal position ledger

### 7. Priority
**High**

### 8. Estimated Effort
**3 days**

### 9. Implementation Notes
- Stops must not rely solely on delayed data
- Account for gaps where stop prices are skipped

---

## UPGRADE 15 — `dark-pool-analyzer`
**One-line description:** Scores dark pool activity for directional conviction and institutional accumulation/distribution inference.

### 1. Why BigClaw Needs This
Alternative flow data can be valuable but needs normalization, backtesting, and contribution tracking.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Ingest dark pool prints
2. Normalize by:
   - average volume
   - price level
   - recent historical baseline
3. Compute:
   - unusual dark volume score
   - price-location relevance
   - persistence score
4. Feed as one weighted factor into scoring engine

### 4. Integration Points
- **Decision engine:** alternative signal
- **Compliance:** source logging
- **Reporting:** dark-pool activity overlays

### 5. yfinance Fields Used
- volume history
- price history

### 6. External Data Sources Required
- Unusual Whales API

### 7. Priority
**Medium**

### 8. Estimated Effort
**3 days**

### 9. Implementation Notes
- Dark pool data should never be used in raw form without normalization

---

## UPGRADE 16 — `insider-flow-monitor`
**One-line description:** Tracks insider buying/selling and scores signal relevance by role, size, and clustering.

### 1. Why BigClaw Needs This
Insider flow is useful only when contextualized; raw insider activity can be misleading.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Ingest Form 4 data
2. Identify:
   - open market buys vs sales
   - executive role importance
   - clustered transactions
   - transaction size relative to compensation/holdings
3. Produce insider conviction score

### 4. Integration Points
- **Decision engine:** low-to-medium weight factor
- **Compliance:** filing provenance logging
- **Reporting:** insider activity dashboard

### 5. yfinance Fields Used
- none primary

### 6. External Data Sources Required
- SEC EDGAR Form 4 feeds
- optional insider transaction API

### 7. Priority
**Medium**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Distinguish planned sales from opportunistic buys

---

## UPGRADE 17 — `institutional-flow-monitor`
**One-line description:** Tracks 13F and institutional ownership changes for slow-moving conviction signals.

### 1. Why BigClaw Needs This
Institutional data is delayed but can improve quality and sponsorship analysis.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Ingest 13F snapshots and ownership trends
2. Score:
   - increasing sponsorship
   - concentration of quality holders
   - changes in top holders
3. Use as medium-term factor only

### 4. Integration Points
- **Decision engine:** sponsorship quality factor
- **Compliance:** data lag transparency
- **Reporting:** ownership trend report

### 5. yfinance Fields Used
- `heldPercentInstitutions` if available

### 6. External Data Sources Required
- SEC 13F filings / institutional holdings API

### 7. Priority
**Low/Medium**

### 8. Estimated Effort
**3 days**

### 9. Implementation Notes
- Clearly mark stale nature of data

---

## UPGRADE 18 — `paper-trading-executor`
**One-line description:** Maintains paper execution simulation in parallel with live trading for comparison and failover.

### 1. Why BigClaw Needs This
Even after live launch, shadow paper execution remains important for A/B comparisons and safe strategy testing.

### 2. What It Replaces
- Upgrade only; remains alongside live execution

### 3. Detailed Functionality
1. Execute shadow trades
2. Apply synthetic slippage model
3. Compare paper vs live drift
4. Support pre-live portfolio incubation

### 4. Integration Points
- **Decision engine:** can route to paper or live by portfolio
- **Reporting:** live-vs-paper comparison
- **Backtesting:** calibration input

### 5. yfinance Fields Used
- quotes and prices if broker unavailable

### 6. External Data Sources Required
- Alpaca paper API

### 7. Priority
**High**

### 8. Estimated Effort
**2–3 days**

### 9. Implementation Notes
- Keep environment separation strict

---

## UPGRADE 19 — `reporting-engine`
**One-line description:** Produces portfolio, risk, benchmark, execution, and compliance reports for operators and audits.

### 1. Why BigClaw Needs This
Current reporting exists, but must absorb performance attribution, slippage, regime history, and signal-health outputs.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
Generate daily/weekly/monthly reports:
- NAV and benchmark comparison
- holdings and turnover
- exposures and risk
- drawdowns
- execution quality
- compliance incidents
- signal attribution
- regime history

### 4. Integration Points
- **Decision engine:** consumes report feedback indirectly
- **Compliance:** audit report publication
- **Screener:** candidate summary publication
- **Observability:** publishes health and KPI metrics

### 5. yfinance Fields Used
- benchmark and price histories

### 6. External Data Sources Required
- all internal data marts
- GitHub Pages / static publishing target

### 7. Priority
**High**

### 8. Estimated Effort
**1 week**

### 9. Implementation Notes
- Use immutable report snapshots with version stamps

---

## UPGRADE 20 — `skill-vetter`
**One-line description:** Evaluates whether proposed new skills or modifications improve measured outcomes and are safe to deploy.

### 1. Why BigClaw Needs This
This is a strategic meta-skill and should remain, but it must use measurable criteria rather than narrative judgments alone.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Define acceptance tests for new skills:
   - accuracy
   - latency
   - integration success
   - no rule conflicts
   - measurable alpha/risk benefit
2. Simulate impact before approval
3. Approve to sandbox, paper, or live stages

### 4. Integration Points
- **Decision engine:** none direct
- **Compliance:** governance of production changes
- **Reporting:** change log and evaluation records
- **Self-improve orchestrator:** primary collaborator

### 5. yfinance Fields Used
- as required by tested skill

### 6. External Data Sources Required
- internal test harness
- backtesting engine

### 7. Priority
**Medium**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Every skill deployment should be stage-gated

---

## UPGRADE 21 — `self-improve-orchestrator`
**One-line description:** Coordinates controlled experimentation, sandbox deployment, and safe iterative improvement of BigClaw’s skills.

### 1. Why BigClaw Needs This
BigClaw’s compounding edge depends on improving safely, not just changing frequently.

### 2. What It Replaces
- Upgrade only

### 3. Detailed Functionality
1. Monitor KPIs from all skills
2. Identify underperforming modules
3. Propose upgrades
4. Route candidates through skill-vetter and backtesting-engine
5. Manage rollout sequence:
   - sandbox
   - paper
   - partial live
   - full live

### 4. Integration Points
- **Decision engine:** indirect only
- **Compliance:** deployment approvals
- **Reporting:** experimentation log
- **Alpha decay tracker:** major input source

### 5. yfinance Fields Used
- as needed indirectly

### 6. External Data Sources Required
- internal telemetry and test outputs

### 7. Priority
**Medium**

### 8. Estimated Effort
**3–5 days**

### 9. Implementation Notes
- Enforce rollback capability for every live change

---

# SECTION 4 — EXISTING SKILLS TO REMOVE (DETAILED)

---

## REMOVE 1 — `stock-evaluator`
**One-line description:** Legacy stock scoring skill duplicating factor analysis.

### 1. Why BigClaw Should Remove This
It creates ambiguity when multiple skills score the same stock differently with overlapping data. This reduces explainability and increases maintenance burden.

### 2. What It Replaces
- Nothing. It is replaced by upgraded `equity-scoring-engine`.

### 3. Detailed Functionality
- Decommission all independent scoring paths
- Migrate any unique heuristics into factor plugins if empirically useful
- Update all dependencies to call canonical scoring engine only

### 4. Integration Points
- Remove from decision engine routing
- Remove from reporting
- Preserve historical outputs only for archival comparison

### 5. yfinance Fields Used
Likely same as fundamental analysis; no longer directly used after retirement.

### 6. External Data Sources Required
None after retirement

### 7. Priority
**High**

### 8. Estimated Effort
**1–2 days**

### 9. Implementation Notes
- Perform dependency search before removal
- Archive score history for attribution comparisons

---

## REMOVE 2 — `stock-strategy-backtester`
**One-line description:** Legacy duplicate backtesting skill.

### 1. Why BigClaw Should Remove This
Two backtesting engines create competing versions of truth.

### 2. What It Replaces
- Replaced by upgraded `backtesting-engine`

### 3. Detailed Functionality
- Freeze current output
- Migrate any unique scenario modes
- deprecate APIs
- reroute all backtest requests to canonical engine

### 4. Integration Points
- Update strategy research workflows
- Update reporting references

### 5. yfinance Fields Used
Historical prices only; retired with engine

### 6. External Data Sources Required
None after retirement

### 7. Priority
**High**

### 8. Estimated Effort
**1 day**

### 9. Implementation Notes
- Validate parity on a benchmark test set before removal

---

## REMOVE 3 — duplicate X sentiment capability entry
**One-line description:** Redundant listing of the same social sentiment function.

### 1. Why BigClaw Should Remove This
Duplicate registry entries increase confusion and can create duplicate execution or conflicting sentiment scores.

### 2. What It Replaces
- Canonical retained skill: `realtime-x-sentiment-tracker`

### 3. Detailed Functionality
- Remove duplicate registration
- Ensure only one feed publishes sentiment events

### 4. Integration Points
- Clean registry references and dashboards

### 5. yfinance Fields Used
None

### 6. External Data Sources Required
X API remains only on canonical skill

### 7. Priority
**Medium**

### 8. Estimated Effort
**Hours**

### 9. Implementation Notes
- Confirm whether duplicate is naming-only or actual deployed duplicate

---

# SECTION 5 — EXISTING SKILLS TO KEEP AS-IS

These need no redesign beyond ordinary maintenance and monitoring.

---

## KEEP 1 — `uptime-monitoring`
**One-line description:** Monitors service availability and endpoint health.
- **Why Keep:** Operationally useful and not implicated in investment underperformance.
- **Action:** Keep as-is; continue standard maintenance.

## KEEP 2 — `log-analyzer`
**One-line description:** Aggregates and interprets logs for faults and anomalies.
- **Why Keep:** Essential for debugging and observability.
- **Action:** Keep as-is.

## KEEP 3 — `slack-discord-alerting`
**One-line description:** Sends operational, risk, and compliance alerts to human operators.
- **Why Keep:** Existing notification channel appears effective.
- **Action:** Keep as-is; reuse for new critical alerts.

---

# SECTION 6 — IMPLEMENTATION SEQUENCING

This is not a summary; it is the recommended build order because several skills depend on others.

## Phase 1 — Capital Safety and Live Readiness
1. `live-execution-engine`
2. `portfolio-drawdown-circuit-breaker`
3. `transaction-cost-model`
4. upgrade `compliance-auditor`
5. upgrade `portfolio-manager`
6. upgrade `afrexai-portfolio-risk`

## Phase 2 — Portfolio Construction Quality
7. `portfolio-correlation-engine`
8. `liquidity-screener`
9. upgrade `candidate-screener`
10. upgrade `equity-scoring-engine`
11. upgrade `sector-analyst`

## Phase 3 — Market-Aware Allocation
12. `macro-factor-monitor`
13. upgrade `market-environment-analysis`
14. upgrade `us-market-bubble-detector`
15. `regime-allocation-controller`

## Phase 4 — Event and Derivatives Risk
16. `earnings-event-risk-manager`
17. `greeks-engine`
18. upgrade `options-strategy-advisor`

## Phase 5 — Measurement and Improvement
19. `performance-attribution-engine`
20. `alpha-decay-tracker`
21. upgrade `backtesting-engine`
22. upgrade `reporting-engine`
23. upgrade `skill-vetter`
24. upgrade `self-improve-orchestrator`

## Phase 6 — Tax and Long-Horizon Refinements
25. `tax-loss-harvesting-automation`
26. upgrade `afrexai-tax-planning`
27. upgrade `institutional-flow-monitor`
28. upgrade `insider-flow-monitor`
29. upgrade `dark-pool-analyzer`
30. upgrade `paper-trading-executor`

---

# SECTION 7 — FINAL DISPOSITION TABLE

| Skill | Action |
|---|---|
| stock-evaluator | REMOVE |
| stock-strategy-backtester | REMOVE |
| duplicate X sentiment capability | REMOVE |
| fundamental-stock-analysis | UPGRADE |
| sector-analyst | UPGRADE |
| intellectia-stock-forecast | UPGRADE |
| portfolio-manager | UPGRADE |
| afrexai-portfolio-risk | UPGRADE |
| market-environment-analysis | UPGRADE |
| us-market-bubble-detector | UPGRADE |
| options-strategy-advisor | UPGRADE |
| afrexai-tax-planning | UPGRADE |
| backtest-expert | UPGRADE |
| realtime-x-sentiment-tracker | UPGRADE |
| compliance-auditor | UPGRADE |
| candidate-screener | UPGRADE |
| trailing-stop-manager | UPGRADE |
| dark-pool-analyzer | UPGRADE |
| insider-flow-monitor | UPGRADE |
| institutional-flow-monitor | UPGRADE |
| paper-trading-executor | UPGRADE |
| reporting-engine | UPGRADE |
| skill-vetter | UPGRADE |
| self-improve-orchestrator | UPGRADE |
| uptime-monitoring | KEEP AS-IS |
| log-analyzer | KEEP AS-IS |
| slack-discord-alerting | KEEP AS-IS |

If you want, I can next convert this into a **developer-ready implementation backlog** with:
- epics
- user stories
- acceptance criteria
- API contracts
- data schemas
- dependency graph
- week-by-week delivery plan.

---



## Round 3: Cross-Examination & Consensus

### Claude Opus 4.6

# Round 3 Cross-Examination

## Addressing Grok 4.20 Beta

### AGREE
1. **`equity-scoring-engine` as the unified scoring module** — We're fully aligned. Grok's spec includes the same 20-dimension, 5-category structure I proposed. The specific yfinance fields enumerated (`info`, `financials`, `balanceSheet`, `cashflow`, `earnings`, `history(period="2y")`, `dividends`, `splits`, `majorHolders`, `institutionalHolders`) are exactly right and implementation-ready. No disagreement here.

2. **`portfolio-risk-manager` with live covariance matrix** — Grok's 90-day rolling covariance matrix and marginal contribution to risk (MCR) computation is well-specified. The merger of `portfolio-manager` + `afrexai-portfolio-risk` is the correct consolidation.

3. **Removing `realtime-x-sentiment-tracker` as duplicate** — Agreed. One canonical sentiment implementation is sufficient.

### CHALLENGE

1. **Keeping `stock-strategy-backtester` while removing `backtest-expert`** — Grok removes `backtest-expert` and upgrades `stock-strategy-backtester`. I proposed the opposite merge direction, but more importantly: **the choice of which name survives is irrelevant — what matters is that exactly ONE backtesting engine exists.** Grok's disposition list is confusing because it lists `backtest-expert` under REMOVE but `stock-strategy-backtester` under both KEEP-AS-IS (in the 9 kept skills) AND UPGRADE (in the 14 upgraded skills). Grok, which is it? This is a specification error that would cause implementation confusion. My proposal is cleaner: merge both into a single `bigclaw-score-backtest-engine` with a fresh spec.

2. **14 skills to upgrade simultaneously** — Grok lists 14 skills for upgrade. That's unrealistic. Even with a 2-week sprint per skill, that's 28 weeks of pure development assuming zero parallelism and zero bugs. My implementation sequence explicitly phases these into 4 waves. Grok provides no sequencing at all. **A plan without sequencing is a wish list.**

3. **Keeping `paper-portfolio-manager` as-is with "will be extended"** — This is a half-decision. Either it needs upgrading or it doesn't. If BigClaw is transitioning to live execution, the paper portfolio manager needs to be architecturally subordinate to the live execution engine, not a separate peer skill. My spec addresses this by making paper mode a `backtest_mode: bool` flag on the execution engine itself.

4. **SEC EDGAR API and Polygon.io as data sources for equity-scoring-engine** — On a Raspberry Pi with yfinance as the primary data source, adding SEC EDGAR parsing and Polygon.io fundamentals introduces significant complexity. SEC EDGAR filings require HTML/XML parsing of 10-K/10-Q documents — that's a non-trivial NLP pipeline. Polygon.io requires a paid subscription. **For Phase 1, yfinance provides sufficient fundamental data.** EDGAR integration should be Phase 3 at earliest.

### CONCEDE

1. **Grok's explicit enumeration of yfinance fields per skill** — This is better than my approach. I specified data sources at the category level; Grok specifies the exact API calls. For a developer implementing on a Raspberry Pi, Grok's granularity is more actionable. I'll adopt this convention.

---

## Addressing Gemini 3.1 Pro

### AGREE

1. **`live-execution-engine` with $100 max position hardcoded at launch** — This is excellent risk management for the paper-to-live transition. The "dry-run" flag, the `live_executions` database table, and the limit-order-pegged-to-ask approach are all production-grade decisions. This is the single most important new skill BigClaw needs.

2. **7 skills to REMOVE** — Gemini's removal list is the most aggressive and the most correct. Removing both `fundamental-stock-analysis` AND `stock-evaluator` (merging into `equity-scoring-engine`), both backtesting skills (merging into `backtesting-engine`), both portfolio/risk skills (merging into `portfolio-risk-manager`), and the duplicate sentiment tracker. This is exactly the consolidation I proposed. Clean.

3. **Keeping `multi-model-debater` and `ips-gatekeeper` as-is** — Gemini correctly identifies these as core architectural pillars that don't need rework. The 7-IPS consensus engine IS the decision layer. I agree these should be untouched in Phase 1.

4. **Keeping `skill-vetter` and `self-improve` as-is** — Agreed. The meta-cognitive loop is working and shouldn't be disrupted during the scoring/execution overhaul.

### CHALLENGE

1. **Keeping `sector-analyst` as a separate skill** — Gemini keeps `sector-analyst` as a standalone "top-down sector overlay." But if we're building a 20-dimension `equity-scoring-engine` that already includes sector-relative scoring, what exactly does a separate `sector-analyst` do that isn't redundant? My spec merges sector analysis INTO the scoring engine as a dimension. A standalone sector skill produces a signal that then needs to be reconciled with the scoring engine — that's exactly the "conflicting signals" problem we're trying to eliminate. **Either sector analysis is a dimension in the scoring engine, or it's a regime-level input to the allocation controller. It should not be a standalone skill producing independent recommendations.**

2. **Keeping `intellectia-stock-forecast` as-is with no conditions** — Gemini marks this KEEP AS-IS as "a distinct ML-based signal input." But distinct from what? If we can't demonstrate that its signal adds alpha beyond what the equity-scoring-engine already captures, it's noise, not signal. My spec keeps it ONLY with the condition that its incremental predictive power is validated via the backtesting engine. Gemini's unconditional keep is insufficiently rigorous.

3. **25 skills in the KEEP AS-IS category is too many** — Gemini lists 16 skills as KEEP AS-IS (items 12-27). Several of these are infrastructure/observability skills that aren't really "investment skills" at all (`uptime-monitor`, `log-analyzer`, `slack-discord-notifier`, `github-pages-reporter`). Lumping them together with investment-critical skills like `trailing-stop-manager` and `dark-pool-monitor` obscures the actual investment skill architecture. My naming convention with domain prefixes (`meta-`, `report-`, `score-`) solves this.

4. **No mention of transaction cost model** — Gemini's `live-execution-engine` tracks slippage after the fact, but there's no PRE-TRADE transaction cost model that estimates whether a trade's expected alpha exceeds its expected cost. For a small-account bot trading potentially illiquid names, this is critical. A $50 expected gain on a trade with $30 in spread + commission costs is a $20 trade, not a $50 trade. My `bigclaw-exec-transaction-cost-model` addresses this gap.

### CONCEDE

1. **Gemini's `live-execution-engine` spec is more implementation-ready than mine** — The $100 max position cap, the dry-run flag, the limit-order-pegged-to-ask logic, and the `live_executions` table are all specific, testable implementation decisions. My spec described the same skill at a higher abstraction level. Gemini's version ships faster. I adopt it.

2. **Gemini's explicit separation of `greeks-engine` as an upgrade to `options-strategy-advisor`** — Rather than building a standalone Greeks skill, upgrading the existing options advisor to include Greeks computation is architecturally cleaner. Fewer skills, same capability.

---

## Addressing GPT-5.4

### AGREE

1. **Flagging that the exact 27-skill inventory wasn't fully visible** — GPT-5.4 is honest about working from inference rather than pretending to have complete information. This is methodologically sound and I respect it.

2. **The disposition matrix structure** — REMOVE / UPGRADE / KEEP AS-IS is the correct tripartite classification. All four analysts converged on this independently, which validates the framework.

3. **`live-execution-engine` as a new skill** — All four analysts agree this is critical. This is the strongest consensus signal in the entire assessment.

### CHALLENGE

1. **Upgrading 21 skills (items 4-24)** — GPT-5.4 lists 21 skills for upgrade. This is the most aggressive upgrade list of any analyst and is flatly unrealistic. Even my 4-wave phased plan with 12 total new/upgraded skills is ambitious for a Raspberry Pi hobby project. Twenty-one simultaneous upgrades would take 6-12 months and produce nothing shippable in the interim. **This is a specification document, not an implementation plan.**

2. **Inferring skill names rather than working from the actual registry** — GPT-5.4 explicitly states it's inferring names like `candidate-screener`, `dark-pool-analyzer`, `insider-flow-monitor`, `institutional-flow-monitor`, `paper-trading-executor`, `reporting-engine`. While intellectually honest, this means GPT-5.4's disposition matrix may not map to actual skills. Any developer trying to implement this would need to do a reconciliation pass first. My spec and Gemini's spec work from the actual skill names, which is more actionable.

3. **Upgrading `trailing-stop-manager`** — GPT-5.4 lists this for upgrade but provides no specification of what's wrong with it or what the upgrade entails. The 15-minute trailing stop check is one of BigClaw's most concrete, well-defined behaviors. Unless there's a specific deficiency (e.g., it doesn't handle gap-downs, it doesn't adjust stop distance by volatility), this should be KEEP AS-IS. Upgrading working infrastructure without justification is how you introduce regressions.

4. **Only 3 skills in KEEP AS-IS** — GPT-5.4 keeps only `uptime-monitoring`, `log-analyzer`, and `slack-discord-alerting` as-is. Everything else gets upgraded. This implies the entire existing system is broken, which contradicts the assessment's premise that BigClaw is a functioning bot that needs enhancement, not a rebuild. **If you upgrade everything, you've built a new system, not improved an existing one.**

### CONCEDE

Nothing. GPT-5.4's proposals are either already covered by my spec or less specific than what I, Grok, or Gemini have provided. The intellectual honesty about incomplete information is appreciated but doesn't produce a better implementation plan.

---

## FINAL PRIORITIZED TOP-10 IMPLEMENTATION LIST

Ruthlessly ordered by **impact × feasibility**, accounting for Raspberry Pi constraints, yfinance as primary data source, and the need to ship incrementally.

| Priority | Skill | Type | Effort | Rationale |
|----------|-------|------|--------|-----------|
| **1** | `equity-scoring-engine` | MERGE + UPGRADE | 2 weeks | **Foundation.** Everything downstream depends on a single, deterministic scoring source of truth. Eliminates 2 redundant skills. All analysts agree. |
| **2** | `portfolio-risk-manager` | MERGE + UPGRADE | 2 weeks | **Guard rails.** Covariance matrix, MCR, position sizing, sector/correlation limits. Eliminates 2 redundant skills. Prevents concentrated blowups. |
| **3** | `live-execution-engine` | NEW | 2 weeks | **The entire point.** Paper trading is not investing. $100 max position cap, dry-run flag, limit orders pegged to ask, `live_executions` table. Adopt Gemini's spec. |
| **4** | `regime-allocation-controller` | NEW | 1.5 weeks | **Macro awareness.** Merges `market-environment-analysis` + `us-market-bubble-detector` into a single regime classifier that scales position sizes. Prevents buying aggressively into a bear market. |
| **5** | `backtesting-engine` | MERGE + UPGRADE | 1.5 weeks | **Validation infrastructure.** Without this, we can't prove any of the above skills work. Walk-forward validation, transaction cost simulation, regime-aware splits. Eliminates 2 redundant skills. |
| **6** | `transaction-cost-model` | NEW | 1 week | **Reality check.** Pre-trade cost estimation (spread, commission, market impact). Small accounts get destroyed by transaction costs. Must gate every trade through this before execution. |
| **7** | `correlation-guard` | NEW | 1 week | **Portfolio-level risk.** Real-time pairwise correlation monitoring. Blocks new positions that would push portfolio correlation above IPS limits. Lightweight — just needs price history from yfinance. |
| **8** | `alpha-decay-tracker` | NEW | 1 week | **Self-correction.** Measures whether each scoring dimension's predictive power is degrading over time. Feeds weight adjustments back to the scoring engine. This is how BigClaw avoids overfitting to stale signals. |
| **9** | `event-risk-manager` | NEW | 1 week | **Earnings/FDA protection.** Reduces position size or hedges before known binary events. Uses yfinance earnings calendar + options IV as inputs. Prevents the "great score, terrible timing" problem. |
| **10** | `options-strategy-advisor` upgrade (with Greeks) | UPGRADE | 1 week | **Income generation.** Covered calls, protective puts, cash-secured puts with proper Greeks computation. Adopt Gemini's approach of upgrading existing skill rather than building standalone Greeks engine. |

### What DIDN'T make the top 10 (and why):

- **Tax-loss harvesting** — Important but only matters at tax time. Implement in Q4. Not urgent.
- **SEC EDGAR integration** — High effort, marginal gain over yfinance fundamentals for Phase 1.
- **Sentiment engine upgrade** — The existing X sentiment tracker works. Upgrade it after the core scoring/execution pipeline is solid.
- **Performance attribution** — Nice to have, but BigClaw needs to make trades before it can attribute performance. Build after live execution is running.
- **`intellectia-stock-forecast`** — Keep running as-is but validate its incremental alpha via the backtesting engine (Priority 5) before investing any development time in upgrading it.

### Implementation Timeline:
- **Weeks 1-4:** Priorities 1-3 (scoring, risk, execution) — the core pipeline
- **Weeks 5-8:** Priorities 4-6 (regime, backtesting, transaction costs) — the validation layer
- **Weeks 9-12:** Priorities 7-10 (correlation, alpha decay, events, options) — the refinement layer

**Total: 12 weeks to a production-grade investment bot.** Not 6 months. Not 21 simultaneous upgrades. Twelve focused weeks with shippable milestones every 4 weeks.

---

### Grok 4.20 Beta

**Claude Opus 4.6 – Cross-Examination**

**AGREE:**  
- Strong naming convention (`bigclaw-{domain}-{function}`) and explicit SkillInterface contract with `health_check()`, `execute(context)`, `backtest_mode`, and IPS field mapping. This adds genuine engineering discipline.  
- Data flow architecture diagram is excellent and correctly positions the scoring engine → regime controller → correlation engine → execution chain.  
- Removing `stock-evaluator` and merging `portfolio-manager` + `afrexai-portfolio-risk` into one unified risk skill.

**CHALLENGE:**  
- The entire 30+ skill taxonomy with 10 new domains is architectural overkill for a Raspberry Pi + yfinance system. We cannot implement `bigclaw-exec-...`, `bigclaw-event-...`, `bigclaw-meta-...` etc. simultaneously.  
- Proposing a full `live-execution-engine` (implied in the flow) is impractical on Pi hardware with only paper Alpaca access in the current scope.  
- Adding Greeks engine, transaction-cost-model, circuit-breaker, alpha-decay-tracker, and performance-attribution in one cycle is fantasy. These are nice-to-have at best.  
- The document is bloated; it fails the “BigClaw can’t implement 30 new skills” test.

**CONCEDE:**  
- Their SkillInterface contract and semantic versioning requirement is superior to my v2.0 spec. I concede on the interface standard.

---

**Gemini 3.1 Pro – Cross-Examination**

**AGREE:**  
- Clean REMOVE list that correctly merges `fundamental-stock-analysis` + `stock-evaluator` into `equity-scoring-engine` and `portfolio-manager` + `afrexai-portfolio-risk` into `portfolio-risk-manager`.  
- Correctly flags `realtime-x-sentiment-tracker` as duplicate.  
- Keeps `unusual-whales-dark-pool-monitor`, `insider-trading-monitor`, `trailing-stop-manager`, and observability stack.

**CHALLENGE:**  
- Keeping `intellectia-stock-forecast` as a distinct ML signal is low-value on Pi hardware; yfinance + simple statistical factors will dominate. This is a nice-to-have that should be deprioritized or removed.  
- Adding `live-execution-engine` as CRITICAL is premature. We are still paper-trading. This belongs in a later phase.  
- Their list still contains too many “keep as-is” skills that are actually low-impact (`skill-vetter`, `self-improve`, `multi-model-debater`, `log-analyzer`). These are meta-fluff.  
- `saturday-screener` and `ips-gatekeeper` are already covered by existing Saturday workflow and compliance auditor; no need to re-list them as separate critical items.

**CONCEDE:** None. Their version of `portfolio-risk-manager` is incomplete compared to mine.

---

**GPT-5.4 – Cross-Examination**

**AGREE:**  
- Correctly identifies removal of `stock-evaluator`, `stock-strategy-backtester`, and duplicate X sentiment.  
- Recognizes need to upgrade `fundamental-stock-analysis` → `equity-scoring-engine`.

**CHALLENGE:**  
- Their disposition matrix is vague and incomplete (“inferred” skills everywhere). Not implementation-ready.  
- Re-introducing `live-execution-engine` as NEW SKILL #1 is the same mistake Gemini makes. Not realistic for current constraints.  
- Keeping `skill-vetter`, `self-improve-orchestrator`, `log-analyzer` as keep-as-is is accepting technical debt. These should be removed or heavily demoted.  
- No concrete yfinance field list or caching strategy. Too hand-wavy.

**CONCEDE:** None. My spec for `equity-scoring-engine` (20-factor JSON vector, z-scores, caching, deterministic versioning) is superior.

---

**FINAL PRIORITIZED TOP-10 LIST**  
(Ruthless prioritization: highest impact, lowest effort, Raspberry Pi + yfinance feasible, no live execution, no ML, no Greeks)

**CRITICAL (Must ship in next 6–8 weeks):**
1. **equity-scoring-engine** (my spec) – 20-factor unified scorer replacing `fundamental-stock-analysis`, `stock-evaluator`, and partial `sector-analyst`. Single source of truth. Highest signal-to-noise impact.
2. **portfolio-risk-manager** (my spec) – Merge of `portfolio-manager` + `afrexai-portfolio-risk`. Live 90-day covariance, MCR, sector/factor limits, risk-parity sizing. Prevents blow-ups.
3. **market-regime-detector** – Consolidated upgrade of `market-environment-analysis` + `us-market-bubble-detector`. Macro overlay that scales position sizes. Critical risk control.
4. **sentiment-engine** – Unified X + news sentiment (already in my v2). Lightweight, high-frequency signal.

**HIGH VALUE (Next):**
5. **stock-strategy-backtester** – Single upgraded backtester replacing both `backtest-expert` and `stock-strategy-backtester`. Must support walk-forward and parameter stability tests.
6. **options-strategy-advisor** – Lightweight version only. No full Greeks engine. Focus on covered calls / wheel / simple spreads using yfinance impliedVolatility and option chain.
7. **weekly-compliance-auditor** – Keep and slightly upgrade. Non-negotiable for IPS enforcement.
8. **15min-trailing-stop-manager** – Keep as-is. Real-time risk control that already works.

**FOUNDATIONAL (Keep / minor upgrade):**
9. **unusual-whales-dark-pool-monitor** + **insider-trading-monitor** + **institutional-flow-tracker** – Keep as-is. These are high-signal, low-effort data feeds.
10. **github-pages-reporting** + **slack-discord-observability** + **uptime-kuma-monitor** – Keep the observability and transparency layer. No new meta skills.

**TO BE REMOVED IMMEDIATELY:**
- `stock-evaluator`, `backtest-expert`, `portfolio-manager`, `realtime-x-sentiment-tracker`, `intellectia-stock-forecast` (unless proven additive), `skill-vetter`, `self-improve`, `multi-model-debater`, `live-execution-engine`, any transaction-cost-model, alpha-decay-tracker, circuit-breaker, full Greeks engine.

This is 10 focused items, not 30. Implement in this order: scoring → risk → regime → backtester → everything else. Everything beyond #10 is a nice-to-have for 2027.

We build what moves the needle on a Pi, not what looks good in a 40-page blueprint.

---

### Gemini 3.1 Pro

This is exactly why we need a senior architect in the room. If we implement everything proposed by this panel, we will choke the Raspberry Pi, exhaust our API rate limits, and end up with a bloated, unmaintainable codebase. We are building a lean, mean, OpenClaw-based alpha generator, not a monolithic hedge fund server rack in Mahwah.

Here is my ruthless cross-examination of the other analysts' proposals, followed by the definitive Top 10 implementation plan.

---

### 1. Cross-Examining Claude Opus 4.6

**AGREE & CONCEDE:** I completely concede to Claude’s **`SkillInterface` Contract**. Standardizing the inputs, outputs, latency budgets, and IPS field consumption into a strict Python class template is brilliant. It forces discipline on the OpenClaw framework and makes meta-cognitive vetting infinitely easier. I am adopting this immediately.

**CHALLENGE:** I strongly challenge Claude’s "Data Flow Architecture." Claude has proposed adding a `Correlation Engine`, `Transaction Cost Model`, `Event Risk Manager`, `Circuit Breaker`, and `Alpha Decay Tracker` as entirely separate sequential nodes. **This is architectural bloat.** Running 10 sequential heavy-compute nodes per ticker on a Raspberry Pi will cause massive latency and memory bottlenecks. These shouldn't be standalone skills; they should be lightweight functions *inside* the `portfolio-risk-manager` and `live-execution-engine`. Keep the node count low.

### 2. Cross-Examining Grok 4.20 Beta

**AGREE & CONCEDE:** I concede to Grok’s specific implementation of the **`portfolio-risk-manager`**. Using a 90-day rolling covariance matrix pulled directly from `yfinance history(period="90d")` to calculate Marginal Contribution to Risk (MCR) is computationally cheap, highly effective, and perfectly suited for a Pi. It is vastly superior to my generic specification.

**CHALLENGE:** I ruthlessly challenge Grok’s data sourcing for the `equity-scoring-engine`. Grok proposes using the SEC EDGAR API (via `sec-edgar-downloader`) and Polygon.io as a fallback. **Impractical and expensive.** Parsing raw XBRL from SEC EDGAR on a Raspberry Pi is a brittle, memory-intensive nightmare that breaks every time a company changes a GAAP tag. Polygon.io costs money, violating the OpenClaw ethos. We must stick strictly to `yfinance` (`info`, `financials`, `balanceSheet`) for fundamental data. If it's not in `yfinance`, we don't trade on it. 

### 3. Cross-Examining GPT-5.4

**AGREE:** I agree with GPT-5.4’s strict categorization matrix. It correctly identified the exact duplicates (like the redundant X/Twitter sentiment trackers) that need to be purged to clean up the audit trail. 

**CHALLENGE:** GPT-5.4 essentially regurgitated my `live-execution-engine` proposal and spent the rest of its output "inferring" skills that were already known. It failed to provide net-new technical architecture. I am discarding its redundant specifications.

---

### THE FINAL VERDICT: Top 10 Prioritized Implementation Plan

BigClaw cannot build 30 things at once. We are executing this in a strict order of operations: **Fix the foundation, manage the risk, then turn on the money.**

#### Phase 1: The Foundation (High Impact, Low Effort)
**1. The `SkillInterface` Refactor (Conceded from Claude)**
*   **Action:** Wrap all existing skills in Claude's standard contract.
*   **Why:** We cannot build new skills until the existing ones communicate predictably. 

**2. `equity-scoring-engine` (Consolidation)**
*   **Action:** Merge `fundamental-stock-analysis` and `stock-evaluator`.
*   **Why:** Stop the bot from generating conflicting fundamental scores. Use strictly `yfinance` data (rejecting Grok's EDGAR proposal).

**3. `unified-backtest-engine` (Consolidation)**
*   **Action:** Merge `backtest-expert` and `stock-strategy-backtester`.
*   **Why:** We need a single source of truth for historical validation before we go live.

#### Phase 2: Risk & Sizing (Critical Path to Live Trading)
**4. `portfolio-risk-manager` (Conceded from Grok)**
*   **Action:** Implement Grok's 90-day rolling covariance matrix via `yfinance`.
*   **Why:** Replaces the generic `portfolio-manager`. Ensures we don't accidentally buy 5 highly correlated tech stocks right before a Nasdaq correction.

**5. `regime-allocation-controller` (Upgraded)**
*   **Action:** Merge `market-environment-analysis` and `us-market-bubble-detector`.
*   **Why:** The bot must know when to scale into cash. If the VIX spikes or moving averages break, this skill overrides the scoring engine and forces risk-off.

#### Phase 3: Live Execution (The Money Layer)
**6. `live-execution-engine` (My Proposal)**
*   **Action:** Build the Alpaca API router with limit-order pegging (Ask for buys, Bid for sells).
*   **Why:** Paper trading is over. This translates paper alpha into actual capital deployment.

**7. `transaction-cost-model` (Integrated, not standalone)**
*   **Action:** Build slippage and fee tracking *directly into* the `live-execution-engine`.
*   **Why:** Prevents the bot from trading away its edge through excessive turnover. 

#### Phase 4: Advanced Alpha & Edge (Post-Live Enhancements)
**8. `options-greeks-engine` (Upgraded)**
*   **Action:** Upgrade `options-strategy-advisor` to pull Black-Scholes Greeks via `yfinance` options chains.
*   **Why:** Allows BigClaw to sell covered calls or buy protective puts based on actual volatility data, not just price action.

**9. `automated-tax-loss-harvester` (Upgraded)**
*   **Action:** Upgrade `afrexai-tax-planning` to automatically flag losing positions for EOY tax harvesting, checking against the 30-day wash sale rule.
*   **Why:** Guaranteed alpha through tax efficiency.

**10. `unified-sentiment-engine` (Consolidation)**
*   **Action:** Delete the duplicate X trackers. Merge news and social sentiment into one clean vector.
*   **Why:** Reduces API calls and prevents duplicate social signals from overweighting a trade decision.

**Conclusion:** This is the blueprint. We purge the duplicates, standardize the interfaces, implement rolling covariance for risk, and turn on live execution. Everything else is a distraction. Let's build.

---

### GPT-5.4

Below is my Round 3 cross-examination. I’m optimizing for **what BigClaw can actually ship on a Raspberry Pi + yfinance + Alpaca/OpenClaw stack**, not an institutional fantasy architecture.

---

# Executive judgment

BigClaw does **not** need 20+ net-new skills right now.  
It needs a **small number of consolidations and control-layer upgrades** that improve:

1. decision quality  
2. risk containment  
3. auditability  
4. execution realism

The highest-value move is to **collapse duplicate analytics into a few canonical engines**:
- **equity-scoring-engine**
- **portfolio-risk-manager**
- **backtesting-engine**
- **sentiment-engine** (only if data quality is sustainable)
- **live/paper execution control layer**

Everything else is downstream.

---

# 1) Claude Opus 4.6 — Cross-examination

## AGREE

### 1. `stock-evaluator` → merge/remove
**Agree.**  
This is genuinely redundant with `fundamental-stock-analysis` and my own proposal to fold both into a unified **equity-scoring-engine**. Keeping both creates conflicting scores and audit confusion.

### 2. `stock-strategy-backtester` + `backtest-expert` → unify
**Agree.**  
This overlap is real. A single `backtesting-engine` is the right abstraction.

### 3. Conditional treatment of `intellectia-stock-forecast`
**Agree strongly.**  
Claude’s “keep only if demonstrably orthogonal” is one of the better prioritization filters in the proposals. This is exactly the right standard. If it’s just another noisy directional predictor that correlates with momentum/fundamental inputs, it should be cut.

### 4. Skill interface contract / explicit schemas
**Agree, with scope control.**  
This is useful. Not a “skill,” but a **critical implementation discipline**. Given BigClaw’s self-vetting/audit posture, strict input/output schema, versioning, dependencies, and health checks are high-value.

### 5. Correlation engine and transaction-cost model in the decision flow
**Agree partially.**  
These are important concepts. Correlation-aware filtering is especially critical. A basic transaction-cost/slippage adjustment is also useful once moving beyond pure paper logic.

---

## CHALLENGE

### 1. Full architecture formalism as immediate priority
**Challenge.**  
Claude’s blueprint trends toward enterprise architecture overhead. On a Pi-class system, if the team spends cycles perfecting naming conventions, latency budgets, and broad interface taxonomy before consolidating the actual logic, that is misplaced effort.

**Critical?** No.  
**Useful?** Yes.  
**Implementation order?** After the core engines are consolidated.

### 2. `Regime Allocation Controller`
**Challenge as separate skill.**  
This likely overlaps with:
- `market-environment-analysis`
- `us-market-bubble-detector`
- `sector-analyst`
- portfolio sizing logic

For BigClaw, a standalone regime controller is probably **one abstraction too many**. Better to embed regime scaling inside the upgraded **portfolio-risk-manager** using outputs from macro/regime analysis.

### 3. `Event Risk Manager`
**Challenge.**  
Potentially valuable, but for current stack constraints this is **nice-to-have**, unless BigClaw is trading around earnings aggressively. Event calendars, data reliability, and pre-event logic add complexity. Not top 10.

### 4. `Circuit Breaker` as a standalone layer
**Challenge on packaging, not concept.**  
Yes, kill switches are critical.  
No, this does not need to be a separate first-class “skill.” It should be a **safety function inside execution/risk management**:
- trading halt on API failure
- max daily loss
- max order rejects
- stale data lockout

### 5. `Alpha Decay Tracker`
**Challenge.**  
Good institutional concept. Wrong phase. BigClaw first needs reliable:
- factor logs
- backtest parity
- attribution
- execution records

Without those, “alpha decay tracking” is premature sophistication.

---

## CONCEDE

### Claude’s handling of `intellectia-stock-forecast` is better than mine
I proposed upgrading it. Claude’s **conditional keep/remove based on signal distinctiveness** is sharper and more disciplined. I concede that framing is better.

### Claude’s interface contract is better specified than mine
I implied standardization, but Claude made it implementation-ready. That part is stronger.

---

# 2) Grok 4.20 Beta — Cross-examination

## AGREE

### 1. `equity-scoring-engine` as unified canonical engine
**Agree.**  
This is the most important consolidation in the whole set.  
BigClaw should not maintain fragmented:
- fundamental analysis
- evaluator logic
- partial sector overlays
- ad hoc score computation

One engine. Versioned. Deterministic. Logged.

### 2. `portfolio-risk-manager` merging `portfolio-manager` + `afrexai-portfolio-risk`
**Agree strongly.**  
This is a real overlap and should be merged. Portfolio construction without integrated risk is a design error.

### 3. Need for raw factor storage and standardized factor outputs
**Agree.**  
Very important for:
- explainability
- IPS audit
- backtest/live consistency
- debugging drift

### 4. Caching financial data / refreshing on filing cadence
**Agree strongly.**  
This is one of the few proposals that explicitly respects **Raspberry Pi constraints**. Good implementation realism.

---

## CHALLENGE

### 1. Removing `portfolio-manager`
**Challenge on wording.**  
I agree with merging it, but not with simply “remove.”  
Functionally, portfolio management is core. The capability must survive inside `portfolio-risk-manager`. This is less disagreement on substance, more on disposition semantics.

### 2. Keeping 9 skills “as-is” while also saying some “will be extended”
**Challenge.**  
That is internally inconsistent. If `paper-portfolio-manager` is “kept as-is” but “will be extended,” then it is not as-is. BigClaw needs a cleaner disposition map.

### 3. External dependencies: SEC EDGAR + Earnings Whispers + Polygon fundamentals
**Challenge for current stack practicality.**  
On a Pi + yfinance baseline, this is too dependency-heavy for first-wave implementation.  
Realistically:
- **yfinance** should remain primary
- SEC EDGAR only if implemented lightly/cached
- Polygon should be optional, not foundational
- Earnings Whispers is not critical for MVP

### 4. Live covariance matrix, MCR, risk parity, portfolio Greeks
**Challenge on sequencing.**  
This is overbuilt for phase one.  
What BigClaw needs first:
- simple correlation caps
- sector caps
- max position size
- volatility-scaled sizing

Marginal contribution to risk and Greeks can wait unless options are actively traded.

### 5. “Reduces false positives by ~35%”
**Challenge.**  
Unsupported precision. That kind of claimed benefit is hand-wavy unless benchmarked.

---

## CONCEDE

### Grok’s caching emphasis is better than mine
That’s an implementation detail I should have made more explicit. On constrained hardware, it matters a lot.

### Grok’s scoring engine spec is tighter than my Round 2 wording
Especially around factor persistence and deterministic versioning. I concede that version is more implementation-ready.

---

# 3) Gemini 3.1 Pro — Cross-examination

## AGREE

### 1. Remove both backtest skills and unify into `backtesting-engine`
**Agree.**  
Clean, necessary, overdue.

### 2. Merge portfolio management and portfolio risk
**Agree in principle.**  
Again, correct consolidation.

### 3. Keep observability stack (`uptime-monitor`, `log-analyzer`, notifier)
**Agree.**  
These are not glamorous, but on an always-on retail bot they matter.

### 4. `ips-gatekeeper` concept
**Agree if this already exists conceptually.**  
This is genuinely critical. BigClaw has 7 IPS-driven portfolios. Style drift control is not optional.

---

## CHALLENGE

### 1. Keep `sector-analyst` as-is
**Challenge.**  
No. It should be upgraded or partially absorbed.  
Sector logic without tighter integration into scoring/risk/regime is exactly how you get duplicate top-down opinions floating around without accountability.

### 2. Keep `intellectia-stock-forecast` as-is
**Challenge strongly.**  
No evidence it deserves protected status. It should be **validated for incremental value**. Otherwise it is a candidate for removal.

### 3. Keep both `unusual-whales-tracker` and `dark-pool-monitor`
**Challenge.**  
That looks duplicative unless one is options flow and the other is dark pool specifically. Needs consolidation or explicit differentiation. BigClaw cannot afford duplicate “alternative flow” wrappers.

### 4. `live-execution-engine` as CRITICAL right now
**Challenge strongly.**  
This is the biggest sequencing mistake in Gemini’s proposal.

BigClaw currently has:
- paper trading
- scoring
- compliance
- stop logic
- multi-signal fusion

The immediate problem is **not** lack of live execution.  
The immediate problem is whether the current stack is:
- coherent
- non-duplicative
- risk-aware
- backtest-consistent

Going live before consolidating scoring/risk/backtesting is reckless.  
For a Pi + yfinance system, live execution is **phase 2**, not first priority.

### 5. `multi-model-debater` / `7-IPS consensus engine` as core dependency
**Challenge.**  
This may be philosophically interesting, but it sounds computationally noisy and operationally hard to audit unless it has strict deterministic outputs. If it already exists and works, fine. But I would not expand around it until core signal governance is cleaned up.

### 6. `github-pages-reporter` as something to preserve prominently
**Challenge on priority.**  
Keep it, sure. But it is not remotely top-tier versus scoring/risk/backtesting.

---

## CONCEDE

### Gemini’s explicit `ips-gatekeeper` naming is better than my inferred compliance framing
That’s a useful distinction. IPS conformance should be more explicit than a generic compliance audit. I concede that naming/spec framing is better.

---

# 4) What is actually critical vs nice-to-have?

## Actually critical
These are the things I would defend as **must-do**:

1. **Unified equity-scoring-engine**
2. **Unified portfolio-risk-manager**
3. **Unified backtesting-engine**
4. **IPS gatekeeping / compliance integration**
5. **Execution safety controls inside paper/live executor**
6. **Candidate screener cleanup**
7. **Trailing-stop-manager hardening**
8. **Deterministic audit logging / factor persistence**
9. **Conditional validation of ML/forecast skills**
10. **Basic macro/regime overlay** integrated into sizing

## Nice-to-have
1. Alpha decay tracker  
2. Standalone event risk manager  
3. Dedicated circuit breaker skill  
4. Portfolio Greeks engine  
5. Tax-loss harvesting automation  
6. Bubble detector as separate module  
7. Broad alt-data expansion beyond what’s already stable  
8. Institutional-style transaction cost analytics beyond simple slippage logs

---

# 5) Overlaps that should be consolidated

These are the biggest architecture cleanups BigClaw should make.

## Consolidation set A — Equity selection
Merge:
- `fundamental-stock-analysis`
- `stock-evaluator`
- parts of `sector-analyst`
- possibly `intellectia-stock-forecast` as an optional sub-signal, not standalone authority

Into:
- **`equity-scoring-engine`**

## Consolidation set B — Portfolio construction and risk
Merge:
- `portfolio-manager`
- `afrexai-portfolio-risk`

Into:
- **`portfolio-risk-manager`**

## Consolidation set C — Backtesting
Merge:
- `backtest-expert`
- `stock-strategy-backtester`

Into:
- **`backtesting-engine`**

## Consolidation set D — Sentiment
Merge:
- `realtime-x-sentiment-tracker`
- any duplicate X/news sentiment capability

Into:
- **`sentiment-engine`**, but only if data quality is stable enough to justify maintenance

## Consolidation set E — Flow monitoring
Potentially merge if overlapping:
- `unusual-whales-dark-pool-monitor`
- `dark-pool-monitor`
- `institutional-flow-tracker`
- `insider-trading-monitor`

At minimum, standardize them under a shared schema. Do **not** allow four bespoke signal formats.

---

# 6) What is impractical for Raspberry Pi + yfinance + OpenClaw?

These are the proposals I would push down the queue or scope down.

## Impractical or over-engineered in phase one
- full institutional risk parity stack
- marginal contribution to risk engine
- live covariance matrix with constant recalculation across many names
- Greeks-heavy options engine unless options are central
- event-driven calendars with many external APIs
- broad alt-data dependency sprawl
- alpha decay analytics before attribution discipline exists
- low-latency execution abstractions with formal latency budgets

## Realistic on current stack
- cached yfinance-based factor engine
- simple rolling volatility and correlation
- sector/position caps
- deterministic paper execution logs
- slippage estimation from bar/quote proxies
- weekly backtest/live drift checks
- simple macro regime flags using a small set of indicators

---

# 7) What should genuinely be removed?

## Remove now
1. `stock-evaluator`
2. `stock-strategy-backtester` or `backtest-expert` as separate entities — keep one unified engine only
3. duplicate X/Twitter sentiment tracker
4. any duplicate dark-pool/flow wrapper with no unique output
5. `intellectia-stock-forecast` **if** it cannot prove incremental predictive value after validation

## Keep, but absorb/rename
1. `portfolio-manager` → absorb into `portfolio-risk-manager`
2. `fundamental-stock-analysis` → absorb into `equity-scoring-engine`
3. `afrexai-portfolio-risk` → absorb into `portfolio-risk-manager`

---

# 8) Realistic implementation order

This is the part that matters most.

## Phase 1: Highest impact, lowest effort
1. **Unify `fundamental-stock-analysis` + `stock-evaluator` into `equity-scoring-engine`**
2. **Merge `portfolio-manager` + `afrexai-portfolio-risk` into `portfolio-risk-manager`**
3. **Merge `backtest-expert` + `stock-strategy-backtester` into `backtesting-engine`**
4. **Remove duplicate sentiment / duplicate flow wrappers**
5. **Standardize schemas, versioning, and logging for all core skills**

## Phase 2: Risk and governance hardening
6. **Explicit IPS gatekeeper integration**
7. **Harden trailing-stop-manager**
8. **Candidate screener upgrade to produce cleaner candidate pools**
9. **Basic macro/regime overlay embedded in risk sizing**

## Phase 3: Validation and selective expansion
10. **Validate `intellectia-stock-forecast` for orthogonal value**
11. **Unify sentiment if worth maintaining**
12. **Add basic slippage-aware execution logging**
13. **Only then consider live execution**

---

# 9) Final top-10 prioritized skill/upgrades

Here is the focused list BigClaw should actually implement.

## 1. `equity-scoring-engine`
Most critical consolidation. Replaces fragmented stock evaluation.

## 2. `portfolio-risk-manager`
Must unify sizing, correlation controls, sector caps, and risk checks.

## 3. `backtesting-engine`
Necessary to avoid contradictory research and to validate every scoring/risk change.

## 4. `ips-gatekeeper`
Explicit enforcement layer for the 7 IPS portfolios. Prevents style drift and compliance ambiguity.

## 5. `candidate-screener` upgrade
Garbage in, garbage out. Better candidate generation improves everything downstream.

## 6. `trailing-stop-manager` hardening
Simple, high-value downside control. Already close to production use.

## 7. `compliance-auditor` upgrade
Must consume actual scoring/risk/execution artifacts, not just produce generic reports.

## 8. `paper-trading-executor` upgrade
Before live trading, make paper execution realistic: order states, slippage logging, rejects, stale-price checks.

## 9. `market-environment-analysis` upgrade
But only as a lightweight regime overlay feeding risk/sizing, not as a sprawling macro platform.

## 10. `intellectia-stock-forecast` validation/refactor
Not because it is inherently critical, but because it must be either:
- proven and retained, or
- removed

That decision is important.

---

# Bottom line by analyst

## Claude
Best on **architecture discipline** and conditional thinking around ML signals.  
Too much enterprise scaffolding too early.

## Grok
Best on **core engine consolidation** and **Pi-conscious caching realism**.  
Too ambitious on advanced portfolio math for phase one.

## Gemini
Best on naming `ips-gatekeeper` explicitly.  
Worst sequencing error: pushing **live execution** too early and protecting too many uncertain legacy skills.

---

# Final ruthless recommendation

If BigClaw only does **five things** next, do these:

1. Build **equity-scoring-engine**
2. Build **portfolio-risk-manager**
3. Build **backtesting-engine**
4. Add **IPS gatekeeping + deterministic audit logs**
5. Upgrade **paper execution realism** before even thinking about live trading

Everything else is secondary.

---

