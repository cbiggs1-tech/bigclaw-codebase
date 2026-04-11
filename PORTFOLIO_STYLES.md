# PORTFOLIO_STYLES.md — Investment Style Definitions & Compliance Rules

## Purpose
This document defines the investment philosophy, style rules, gate checks, and compliance criteria for each of BigClaw's 7 portfolios. Use this as the authoritative reference when:
- Discussing portfolio strategy or holdings with Curtis
- Evaluating whether a stock belongs in a specific portfolio
- Explaining why the compliance audit flagged a holding
- Recommending trades or swaps

## The Convergence Problem
Without style enforcement, the decision engine's 15-dimension scoring system would gradually cause all 7 portfolios to converge into one generic fund. The style weights only *prefer* certain characteristics — they don't *enforce* them. Style fidelity operates at three layers:
1. **Gate Check (before buying)** — Hard filters. If a candidate fails, blocked regardless of score.
2. **Ongoing Audit (weekly)** — Catches drift in current holdings.
3. **Enforcement (2-month watchlist)** — Flagged holdings get 2 months: compete for a spot in a fitting portfolio, or sell. No extensions.

---

## 1. Value Picks (Buffett/Graham — Quality Value)

**Philosophy:** Warren Buffett and Benjamin Graham. Buy wonderful companies at fair prices. Durable competitive advantages (moats), predictable earnings, strong management, long-term compounding. Evolved from Graham's "cigar-butt" deep value to Buffett/Munger's quality-at-a-fair-price.

**Core Principles:**
- Circle of competence — invest in understandable businesses
- Economic moats — brands, network effects, switching costs, cost advantages
- Margin of safety — buy below intrinsic value
- "Price is what you pay; value is what you get"
- Ideal holding period: forever
- "Be fearful when others are greedy, greedy when others are fearful"
- High ROE without excessive leverage
- Strong free cash flow generation
- Honest, competent, shareholder-oriented management

**Berkshire Hathaway Reference (Q4 2025 13F):**
Top holdings: AAPL 22.6%, AXP 20.5%, BAC 10.4%, KO 10.2%, CVX 7.2%, MCO 4.6%, OXY 4.0%, CB 3.9%
Sectors: ~35% financials, ~25% tech (consumer moat), ~14% consumer staples, ~11% energy
$373B cash reserve. Top 5 = 71% of portfolio. Net seller for 12+ quarters.

**Gate Checks (Before Buying):**
| Check | Criteria |
|---|---|
| ROE | >= 15% (Buffett targets 20%+, 15% is hard floor) |
| Free cash flow | Positive FCF |
| Earnings | Positive trailing EPS — no money-losing companies |
| P/E at purchase | < 25 (fair price, not speculative) |
| Debt-to-equity | < 2.0 for non-financials (banks exempted — inherently leveraged) |
| Gross margin | >= 30% (pricing power signal) |

**Weekly Audit:**
| Check | Type | Criteria |
|---|---|---|
| P/E drift | warning | P/E > 30 (getting expensive) |
| P/E extreme | REJECT | P/E > 60 (no value case at this level) |
| ROE drop | warning | ROE falls below 12% |
| FCF negative | warning | FCF turns negative |
| Negative earnings | REJECT | Trailing earnings go negative |
| Dividend | warning | Does not pay a dividend (most Buffett holdings do) |
| Portfolio avg yield | audit | Target >= 1% average |

**What makes it unique:** P/E ceiling, ROE floor, FCF requirement, gross margin gate. Would never buy near 52-week highs. No technical checks — Buffett ignores charts entirely. No market direction gate — buys in bear markets.

---

## 2. Growth Value (Peter Lynch — GARP)

**Philosophy:** Peter Lynch's Growth At a Reasonable Price. Managed Fidelity Magellan Fund 1977-1990 (29% avg annual return, $20M to $14B). Core belief: ordinary investors can outperform Wall Street by using common sense, everyday observations, and thorough fundamental research. "Invest in what you know." The PEG ratio is the central valuation metric.

**Core Principles:**
- PEG ratio is the primary valuation tool (PEG < 1.0 = attractive, > 2.0 = avoid)
- Invest in what you know — start with products/companies you encounter daily
- Six stock categories: Slow Growers, Stalwarts, Fast Growers, Cyclicals, Turnarounds, Asset Plays
- Focus on Stalwarts (10-20% EPS growth) and Fast Growers (20-50% EPS growth)
- Bottom-up fundamental analysis, not macro predictions
- Strong balance sheet is "the single most important factor" in surviving downturns
- Patience — big winners need time to compound
- Avoid "hot" stocks in hot industries, unsustainable growth (>50%), and companies you don't understand
- Dividend-adjusted PEG (PEGY) for slower growers: PEGY = P/E / (EPS Growth % + Dividend Yield %)

**PEG Ratio Guide:**
| PEG | Lynch's View |
|---|---|
| < 0.5 | Very attractive — strong buy |
| 0.5 - 1.0 | Buy zone |
| 1.0 | Fair value |
| 1.0 - 1.5 | Getting expensive |
| > 1.5 | Overvalued — avoid |
| > 2.0 | Way too expensive — sell |

**AAII Lynch Screen Reference:** PEG < 1.0, P/E 5-40, EPS growth 15-50% (fast growers) or 10-20% (stalwarts), D/E < 0.33 preferred, positive FCF, inventory growth <= revenue growth.

**Validea Lynch Model Top Scorers:** Typically regional banks, insurance, small industrials with P/Es in the 7-15 range — "boring companies that make money."

**Gate Checks (Before Buying):**
| Check | Criteria |
|---|---|
| PEG ratio | < 1.5 (ideally < 1.0) |
| P/E range | Between 5 and 40 (Lynch's operating range) |
| EPS growth | Between 10% and 50% (no slow growers, no unsustainable rockets) |
| Positive earnings | Must have positive EPS |
| Debt-to-equity | < 0.80 (Lynch preferred < 0.33 for fast growers) |
| Free cash flow | Positive FCF |

**Weekly Audit:**
| Check | Type | Criteria |
|---|---|---|
| PEG extreme | REJECT | PEG > 2.0 (Lynch would sell) |
| P/E extreme | REJECT | P/E > 40 (outside Lynch's operating range) |
| PEG drift | warning | PEG > 1.5 (getting expensive) |
| Earnings decline | warning | Earnings growth turning negative |
| EPS too hot | warning | EPS growth > 50% (unsustainable per Lynch) |
| Inventory buildup | warning | Inventory growing faster than revenue |
| D/E high | warning | D/E > 0.80 |

**What makes it unique:** The "goldilocks" portfolio — not as cheap as Buffett (pays up to P/E 40 for growth), not as expensive as Wood (demands PEG < 1.5), not as technical as O'Neil (pure fundamentals, no chart patterns). Lynch doesn't care about new highs, market direction, or momentum — just earnings growth at a reasonable price. Requires positive earnings (unlike Innovation Fund). The PEG ratio is the single differentiating metric that separates this from every other style.

---

## 3. Income Dividends (Dividend Aristocrats — Income)

**Philosophy:** Reliable, growing dividend income. Capital appreciation is secondary. Modeled after Dividend Aristocrats (25+ years consecutive dividend increases) and Dividend Kings (50+ years). The power of compounding dividends over decades. Combines yield with dividend growth to generate total return through income.

**Core Principles:**
- Dividend yield is the primary selection criterion
- Dividend growth history matters more than current yield alone
- The Chowder Rule: Yield + 5-Year Dividend Growth Rate = total return proxy
- Payout ratio discipline — sustainable dividends, not funded by debt
- Avoid yield traps (unsustainably high yield from a falling stock price)
- Entity-type awareness: REITs, MLPs, and ETFs have different payout metrics
- Reinvest dividends for compounding
- Stability and predictability over growth

**Dividend Hierarchy:**
- Dividend Kings: 50+ consecutive years of increases (~50 stocks)
- Dividend Aristocrats: 25+ consecutive years, S&P 500 member (~67 stocks)
- Dividend Champions: 25+ years (no S&P 500 requirement, ~140 stocks)
- Dividend Contenders: 10-24 consecutive years (~350 stocks)
- Dividend Challengers: 5-9 consecutive years (~400 stocks)

**The Chowder Rule (Key Metric):**
Chowder Number = Current Yield + 5-Year Dividend Growth Rate
- Normal stocks (yield < 3%): Chowder # >= 12
- High-yield stocks (yield >= 3%): Chowder # >= 8
- Utilities / REITs / MLPs: Chowder # >= 8

**Payout Ratio Safety Thresholds:**
| Payout Ratio | Assessment | Historical Cut Probability |
|---|---|---|
| < 50% | Very safe | ~4% |
| 50-60% | Safe | ~6% |
| 60-75% | Caution | ~10-15% |
| > 75% | Danger zone | ~25-30% |
| > 100% | Paying from reserves/debt | ~55-65% |

**Entity-Type Rules:**
- Standard stocks: Earnings payout < 70%, D/E < 2.0
- REITs (e.g., O): Use AFFO payout ratio (not earnings). Safe < 80%. Must distribute 90%+ of taxable income by law.
- MLPs (e.g., EPD, KMI): Use DCF coverage ratio. Safe > 1.2x. Issue K-1 forms.
- ETFs (e.g., SCHD): Skip payout/debt checks. Auto-pass safety. Apply Chowder rule to distribution yield + growth. Can hold up to 20% of portfolio.

**Yield Trap Detection (auto-flag if):**
- Yield > 6% standard stock (> 8% REIT, > 9% MLP)
- Yield > 2x sector average
- Payout > 90% AND yield > 5%
- Price down >30% in 12 months while yield spiked

**Reference ETFs:** SCHD (3.5% yield, ~12% growth), NOBL (2.2% yield, Aristocrats), VIG (1.8% yield, growth focus), HDV (3.8% yield, high income)

**Gate Checks (Before Buying):**
| Check | Criteria |
|---|---|
| Pays dividend | Must pay a dividend — non-negotiable |
| Dividend yield | >= 1.5% at purchase |
| Chowder number | >= 8 (high yield/REIT/MLP) or >= 12 (low yield) |
| Payout ratio | < 75% earnings (standard), < 80% AFFO (REIT), DCF coverage > 1.2x (MLP) |
| Positive FCF | Must have positive free cash flow (or AFFO/DCF equivalent) |
| Not a yield trap | Yield < 6% standard / < 8% REIT / < 9% MLP, unless strong safety metrics |

**Weekly Audit:**
| Check | Type | Criteria |
|---|---|---|
| Zero dividend | REJECT | Dividend eliminated — immediate violation |
| Dividend cut | REJECT | Dividend reduced from prior period |
| Payout extreme | REJECT | Payout > 90% (standard) or AFFO payout > 90% (REIT) |
| Yield trap | REJECT | Yield > 8% standard stock with declining earnings |
| Chowder fail | warning | Chowder number falls below threshold |
| Payout elevated | warning | Payout 70-90% (standard) |
| Yield below floor | warning | Yield drops below 1.0% |
| D/E high | warning | D/E > 2.0 (non-financial) |
| Portfolio avg yield | audit | Target >= 2% average |

**What makes it unique:** Most mechanically distinctive portfolio. Hard dividend gate blocks all non-dividend stocks. Entity-type awareness (REIT/MLP/ETF different rules). Chowder Rule enforces yield + growth combination. Payout safety checks at multiple thresholds with yield trap detection. This portfolio would never hold TSLA, PLTR, BRK-B, or any growth stock that reinvests instead of distributing.

---

## 4. Innovation Fund (Cathie Wood — Disruptive Innovation)

**Philosophy:** ARK Invest style. Aggressive, thematic growth investing focused on disruptive innovation across 5 converging technology platforms. Willing to accept extreme valuations and pre-profit companies for transformative potential. 7+ year investment horizon.

**Core Principles:**
- Disruptive innovation is the key driver of long-term value creation
- 5 converging innovation platforms (must connect to at least one):
  1. **AI / Machine Learning / Compute**
  2. **Robotics / Autonomous Systems** (commercial applications)
  3. **Energy Storage / Clean Energy**
  4. **Genomics / Multiomics / Precision Medicine**
  5. **Blockchain / Fintech / Crypto / Next-Gen Internet**
- Wright's Law: costs fall predictably with cumulative production
- High conviction, concentrated positions
- Capital appreciation only — dividends irrelevant
- Hold through drawdowns by conviction

**ARKK Top Holdings Reference (March 27, 2026):**
TSLA 10.6%, CRSP 6.3%, TEM 5.0%, SHOP 4.8%, CRCL 4.7%, COIN 4.5%, HOOD 4.4%, AMD 4.1%, ROKU 3.8%, PLTR 3.7%
41-44 positions. Top 10 = ~52%. Heavy genomics, blockchain/fintech, AI, autonomous tech.
TSLA spans 3 platforms (AI, autonomous, energy storage) = highest conviction.

**Gate Checks (Before Buying):**
| Check | Criteria |
|---|---|
| Innovation platform | Must connect to at least one of the 5 platforms above |
| Revenue growth | Revenue growing >10% YoY |

**Weekly Audit:**
| Check | Type | Criteria |
|---|---|---|
| Revenue collapse | REJECT | Revenue declining 2+ consecutive quarters |
| Legacy business | REJECT | Pure consumer staples, traditional banking, insurance, legacy utility |
| High yield flag | warning | Dividend yield >3% (suggests income stock, not innovator) |
| Revenue stalling | warning | Revenue growth 0-10% |

**What makes it unique:** No P/E ceiling. No earnings requirement. No technical momentum gates. No market direction filter. Tolerates pre-profit companies. A company in a "traditional" sector (e.g., Deere in ARKK) is fine IF it is applying one of the 5 platforms to transform its business. The gate is about the innovation thesis, not the SIC code.

---

## 5. Momentum Growth (William O'Neil — CANSLIM)

**Philosophy:** William O'Neil's CANSLIM methodology from "How to Make Money in Stocks." Find proven winners with accelerating fundamentals and ride the momentum. Combines technical analysis (price action, volume, relative strength) with fundamental requirements (earnings acceleration, ROE). Sector-agnostic.

**CANSLIM Acronym:**
- **C** — Current quarterly earnings growing (>=20% YoY)
- **A** — Annual earnings consistent (ROE >=15%, positive growth)
- **N** — New highs after a base pattern (price within 15% of 52-week high)
- **S** — Supply and demand (no share dilution >10% YoY)
- **L** — Leader, not laggard (relative strength vs S&P 500 positive)
- **I** — Institutional sponsorship (ownership 20-95%)
- **M** — Market direction (S&P 500 above 200-day SMA)

**Core Principles:**
- Momentum backed by earnings, not just charts
- Buy at pivot points (breakouts from bases) on volume
- 7-8% stop-loss below purchase price
- Concentrate in 4-8 high-conviction names
- Only buy in confirmed market uptrends
- "Buy on fundamentals and technicals, sell primarily on technicals"

**Gate Checks (Before Buying):**
| Check | Criteria |
|---|---|
| Quarterly EPS growth | >= 20% QoQ vs same quarter last year |
| ROE | >= 15% |
| Near highs | Price within 15% of 52-week high |
| Relative strength | 3-month RS vs S&P 500 positive (outperforming) |
| Institutional ownership | 20-95% |
| Market direction | S&P 500 above 200-day SMA (confirmed uptrend) |

**Weekly Audit:**
| Check | Type | Criteria |
|---|---|---|
| Earnings decline x2 | REJECT | Two consecutive quarters declining earnings |
| Share dilution | REJECT | Shares outstanding up >10% YoY |
| RS bottom quartile | REJECT | Relative strength bottom 25% for 60+ days |
| Trend broken | REJECT | Price below both SMA50 and SMA200 |
| Below high | warning | Price >25% below 52-week high |
| RS negative | warning | Relative strength negative for 30+ days |
| Volume fading | warning | Volume consistently below average |

**What makes it unique:** Only portfolio that stops buying in bear markets (M gate). Requires earnings acceleration (unlike Innovation Fund). Buys near highs (unlike Value). Sector-agnostic (unlike Nuclear/Defense). The "why behind the momentum" — not random chart chasing.

---

## 6. Nuclear Renaissance (Domain Expertise — Nuclear/Energy)

**Philosophy:** Thematic portfolio built on Curtis's 43 years of nuclear power industry experience (Comanche Peak, systems engineering, I&C, QA). Nuclear is the only energy source satisfying Big Tech's simultaneous demands for massive baseload capacity, 24/7 reliability, and carbon-free credentials.

**Three Megatrends:**
1. AI data center power demand ($650B Big Tech infrastructure spend in 2026)
2. Policy tailwinds (EO 14300, NRC reform, ADVANCE Act)
3. Energy security and grid reliability

**Thesis Tiers:**
- **Tier 1 Core (proven operators):** CEG, VST, GEV, CCJ, BWXT — profitable, cash-generating, operating NOW
- **Tier 2 Speculative:** LEU, OKLO, SMR — high risk, pre-revenue or thin revenue
- **Tier 3 Watchlist:** NNE, FLR — don't buy yet

**Barbell Strategy:** 79% core (profitable + FCF), 13% speculative, 5% cash reserve.

**Key Differentiator:** NRC licensing timeline is the single most important variable. Big Tech doesn't care about theoretical reactor superiority — they care about "when can you deliver megawatts?"

**Source Documents:**
- Nuclear Renaissance Thesis (Feb 16, 2026): ~/.openclaw/workspace/research/nuclear-renaissance-thesis-2026-02-16.md
- Covers CEG, VST, GEV, CCJ, BWXT, LEU, OKLO, SMR, NNE, FLR, URA
- VST deep dive: Comanche Peak + Comanche Circle data center campus (5 GW)
- SMR vs OKLO comparison, MSR landscape (Natura, Kairos, TerraPower, ACU)

**Gate Checks (Before Buying):**
| Check | Criteria |
|---|---|
| Sector fit | Must be nuclear power, uranium, nuclear fuel/services, or nuclear-adjacent energy |

**Weekly Audit:**
| Check | Type | Criteria |
|---|---|---|
| Sector mismatch | REJECT | Not in nuclear/uranium/energy sector |
| Pre-revenue heavy | warning | Pre-revenue holdings exceed 15% of portfolio |
| Short interest | warning | Short interest >25% |
| Core FCF | warning | Core-tier holding with negative FCF |

**What makes it unique:** Hard sector constraint. Curtis's domain expertise is the edge — he can evaluate NRC licensing readiness, aging management programs, and plant operational culture in ways Wall Street analysts cannot.

---

## 7. AI Defense & Autonomous (Pentagon Thematic — Defense/AI)

**Philosophy:** The Pentagon is shifting from "few and exquisite" to "many and autonomous." This portfolio captures the generational procurement shift toward AI-enabled autonomous systems, JADC2, CCA, FLRAA, Replicator Initiative, and Counter-UAS.

**Key Programs:**
- Replicator Initiative — thousands of autonomous systems across all domains
- JADC2 — AI-powered networking of sensors, shooters, decision-makers
- CCA — Autonomous wingman drones alongside manned fighters
- FLRAA — Bell V-280 Valor replacing Black Hawk fleet
- Counter-UAS — massive investment in defeating enemy drones

**Thesis Tiers:**
- **Tier 1 Genuine AI/Autonomous:** PLTR, KTOS, AVAV, LDOS — AI/autonomy is core revenue
- **Tier 2 Strong AI Pivot:** NOC, LHX, RTX, BAH — traditional primes genuinely transforming
- **Tier 3 Traditional Defense + AI Upside:** LMT, GD, TXT — AI is additive, not transformational
- **Tier 4 Speculative:** RCAT — pre-profit, high short interest

**Portfolio Characteristics:** Weighted beta ~0.65 (defensive), ~1.2% dividend yield, 100% Defense/Aerospace by design.

**Source Documents:**
- AI Defense & Autonomous Thesis (Feb 16, 2026): ~/.openclaw/workspace/research/defense-ai-portfolio-2026-02-16.md
- Bell Helicopter deep dive (TXT) with supply chain analysis for retired Bell executives
- 12-stock ranking with tier assignments and risk assessments

**Gate Checks (Before Buying):**
| Check | Criteria |
|---|---|
| Sector fit | Must be Defense, Aerospace, Gov IT/AI, or Autonomous Systems |

**Weekly Audit:**
| Check | Type | Criteria |
|---|---|---|
| Sector mismatch | REJECT | Not in defense/aerospace/gov-IT sector |
| Revenue declining | warning | Revenue growth negative (procurement shift thesis failing) |
| Pre-profit | warning | Pre-profit company (RCAT-type risk) |
| Short interest | warning | Short interest >20% |

**What makes it unique:** Hard sector constraint. 100% Defense/Aerospace concentrated by design. Informed by input from retired Bell Helicopter executives with insider supply chain knowledge.

---

## Cross-Portfolio Move Policy

When a holding drifts out of style compliance:
1. Weekly audit flags the violation
2. Goes on **2-month compliance watchlist** (hard deadline, no extensions)
3. During watch period: decision engine evaluates if the stock fits another portfolio
4. At deadline: **move** to a fitting portfolio (if it wins a spot) OR **sell**
5. **Block additional buys** in the original portfolio during the watch period
6. Signals page shows pending moves for Curtis's 30-minute supervisory review window

---

## Portfolio Differentiation Summary

| Portfolio | Core Question | Named Style |
|---|---|---|
| Value Picks | Is it cheap relative to what it earns? | Buffett/Graham |
| Growth Value | Is it growing at a reasonable price? | Peter Lynch |
| Income Dividends | Does it pay me reliably? | Dividend Aristocrats |
| Innovation Fund | Is it disrupting an industry? | Cathie Wood |
| Momentum Growth | Is it a proven winner accelerating now? | William O'Neil |
| Nuclear Renaissance | Does it fit the nuclear thesis? | Domain Expertise |
| AI Defense & Autonomous | Does it fit the Pentagon autonomy thesis? | Pentagon Thematic |

3 fundamental styles (value, GARP, income), 1 disruption/speculative, 1 technical+fundamental momentum, 2 thematic/sector-constrained. Clean separation.

---

*Last updated: March 28, 2026*
*Thesis sources: defense-ai-portfolio-2026-02-16, nuclear-renaissance-thesis-2026-02-16*
*Berkshire 13F: Q4 2025. ARKK holdings: March 27, 2026.*
