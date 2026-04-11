# Nuclear Renaissance Portfolio — Investment Policy Statement

**Portfolio #6: Nuclear Renaissance**
**Investment Style:** Nuclear Energy / Domain Expertise / Thematic Structural
**Thesis Author:** Curtis Biggs (43 years nuclear power — Comanche Peak, systems engineering, I&C, QA)
**Document Version:** 1.0 — April 1, 2026
**Derived From:** Multi-model thesis debate (Claude Opus 4.6, Grok 4.20 Beta, Gemini 3.1 Pro, GPT-5.4)
**Foundation:** Nuclear Renaissance Thesis Document (February 16, 2026, 16 pages)
**Approved By:** Curtis Biggs (Moderator)

---

## 1. Investment Thesis

### 1.1 Core Philosophy

Nuclear power is the only energy source that simultaneously satisfies Big Tech's three non-negotiable requirements: massive baseload capacity, 24/7 reliability, and carbon-free credentials. The nuclear renaissance is not speculative — it is a structural shift driven by three megatrends that are already in motion and accelerating.

This portfolio is fundamentally different from all other BigClaw portfolios. The competitive edge is not a published investment methodology from a famous investor — it is **Curtis Biggs's 43 years of nuclear power industry experience**. Curtis can evaluate NRC licensing readiness, aging management programs, reactor coolant system design trade-offs, digital I&C common-cause failure risk, and plant operational culture in ways that no sell-side analyst or AI model can replicate. The ExpertOverride signal is weighted at the maximum (2.0) because Curtis's domain judgment IS the strategy.

### 1.2 Three Megatrends

**1. AI Data Center Power Demand**
Big Tech's AI infrastructure buildout demands massive, reliable, carbon-free power. The $650B+ in committed AI capex (aggregated from AMZN, GOOGL, META, MSFT Q4 2025 earnings calls) requires gigawatts of new baseload generation. Solar and wind cannot provide 24/7 baseload at the scale needed. Nuclear can.

**2. Policy Tailwinds**
- Executive Order 14300 (January 2025): Directs federal agencies to accelerate nuclear deployment
- ADVANCE Act (Public Law 118-67, July 2024): Reforms NRC licensing to reduce timelines
- Bipartisan Congressional support for nuclear energy — rare policy consensus

**3. Energy Security and Grid Reliability**
Grid strain from electrification, EV charging, and data centers is exposing the fragility of intermittent renewable-dependent grids. Nuclear provides the baseload reliability that no combination of solar, wind, and batteries can match at scale.

### 1.3 The Licensing Timeline Framework (Crown Jewel)

The single most important insight in this thesis: **NRC licensing timeline — not reactor design elegance — determines which companies win Big Tech contracts.** Big Tech doesn't care about theoretical reactor superiority. They care about "when can you deliver megawatts?"

This framework correctly separates companies into tiers based on their proximity to delivering actual power:

| Tier | Definition | Allocation | Examples |
|------|-----------|-----------|---------|
| **Tier 1: Core** | Profitable, cash-generating, operating NOW | 79% | CEG, VST, GEV, CCJ, BWXT |
| **Tier 2: Speculative** | High risk, pre-revenue or thin revenue, NRC in process | 13% | LEU, OKLO, SMR |
| **Tier 3: Watchlist** | Don't buy yet — concept stage or NRC not engaged | 0% (watch) | NNE, FLR |

**Barbell Strategy:** 79% core (profitable + FCF) / 13% speculative / 5% cash reserve. Position sizing follows conviction, which follows information quality — Curtis has the deepest edge on Tier 1 companies (operating plants he's walked through) and diminishing edge on Tier 2/3 (pre-revenue companies whose NRC applications he hasn't reviewed firsthand).

### 1.4 Risk Philosophy

**Balance Sheet Discipline for Core Holdings**
Core holdings must be profitable and generating free cash flow. Nuclear utilities and fuel companies that have survived 40+ years of regulatory, political, and market cycles have proven their business models. The requirement for positive FCF ensures BigClaw only holds companies that are generating cash, not consuming it.

**Tolerance for Speculative Positions (Capped)**
Tier 2 speculative holdings (LEU, OKLO, SMR) are allowed because the asymmetric upside of a successful SMR deployment or uranium enrichment monopoly is enormous. But exposure is capped at 13% of the portfolio — a total loss of all speculative positions would be painful but not catastrophic.

**The "No Chase" Rule**
Never chase any name that's up >5% on a given day. Nuclear stocks are prone to sharp moves on policy announcements, NRC milestones, and Big Tech contract news. Chasing these moves is how retail investors get caught at the top of sentiment spikes. (Source: Nuclear Renaissance Thesis, Risk Management section)

**Key Risk: Narrative Concentration**
All positions are correlated to a single narrative: "nuclear is the answer to AI power demand." If that narrative breaks — AI winter, cheaper alternatives, or a nuclear safety event — every position declines simultaneously. The portfolio has zero hedges against its own thesis failing.

*Mitigation:* Monitor 60-day pairwise rolling correlation across holdings. When average correlation exceeds 0.85, flag "narrative concentration risk" and consider increasing cash reserve from 5% to 10-15%.

### 1.5 Behavior Across Market Regimes

| Regime | Expected Behavior | Portfolio Action |
|--------|-------------------|-----------------|
| Bull market + nuclear narrative | Excellent — thesis tailwind | Hold, let winners run, trim at valuation extremes |
| Bull market + nuclear out of favor | Lags — narrative not in focus | Patience — fundamentals unchanged if plants still operating |
| Bear market / recession | Utilities (CEG, VST) defensive; speculative names hit hard | Core holds, speculative positions may need trimming |
| Rising rates | Mixed — hurts project financing (SMR, OKLO) but utilities pass through costs | Monitor debt levels; speculative positions most vulnerable |
| Nuclear safety event (accident/incident) | Severe drawdown across all holdings | ExpertOverride critical — Curtis evaluates actual safety implications vs market panic |
| AI winter / demand collapse | Thesis-breaking — all positions correlated to AI power demand | Cash reserves, correlation audit triggers, thesis reassessment |
| Political reversal (2028+) | EO 14300 can be reversed by next president | Increase cash in election years; monitor NRC commissioner appointments |

### 1.6 Known Weaknesses

1. **Single-Narrative Concentration:** All positions are correlated to the nuclear renaissance thesis. Diversification within the portfolio is an illusion — it's all one bet with different risk profiles.

2. **GEV Classification Ambiguity:** GE Vernova is classified as "Core" but nuclear is a small fraction of GEV's revenue. GEV is primarily gas turbines, wind, and grid equipment. The BWRX-300 SMR is optionality, not current nuclear revenue. This provides accidental diversification but overstates nuclear purity.

3. **Valuation Blindness:** The original thesis had no valuation ceilings. CEG at P/E 33 and CCJ at P/E 114 were treated with equal conviction. P/E is now an audit warning (not gate) for Core holdings per debate consensus.

4. **Construction Cost Risk (Unquantifiable):** Every new-build nuclear project in the US has experienced catastrophic cost overruns (Vogtle: $14B to $35B+, 7 years late). For SMR and OKLO, this risk is real but not measurable via yfinance. Requires monitoring SEC filings and NRC docket submissions.

5. **Uranium Price Sensitivity:** CCJ and LEU are directly exposed to uranium spot prices. URA ETF serves as a proxy for uranium market sentiment via `yf.Ticker('URA')`.

6. **Political Fragility:** EO 14300 is an executive order — reversible by the next president. NRC's institutional culture resists acceleration mandates regardless of political direction.

---

## 2. Gate Rules (Hard Buy Filters)

A candidate is **BLOCKED** if any gate fails.

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| G1 | Sector Whitelist | Ticker must be on manually maintained nuclear/uranium whitelist | Manual list (not yfinance sector strings) | Thesis sector definition. All 4 analysts agree yfinance sector/industry is unreliable for nuclear classification. | Unanimous |
| G2 | Market Cap Floor | marketCap >= $3B | `info['marketCap']` | Moderator decision: captures all major nuclear operators and viable SMR companies, excludes concept-stage micro-caps. [Moderator override — Claude proposed $500M, Grok $10B] | Moderator |
| G3 | Positive FCF (Core only) | freeCashflow > 0 for Tier 1 Core holdings | `info['freeCashflow']` | Thesis: "profitable, cash-generating, operating NOW." Speculative (Tier 2) exempt. | Unanimous |
| G4 | Positive Revenue | revenue > 0 (any amount) | `info['totalRevenue']` | Thesis tier system — Tier 1 requires operating companies. Tier 2 may have minimal revenue. Tier 3 (zero revenue) = watchlist only. | Claude/GPT consensus |
| G5 | No-Chase | Do not buy if stock is up >5% on the day | `info['currentPrice']` vs prior close | Nuclear Renaissance Thesis, Risk Management. | Unanimous |
| G6 | Data Sufficiency | Key fields (revenue, sector, price) not None/NaN | Multiple | Implementation requirement. | Unanimous |

### Gate Calibration Notes

**G1 (Sector Whitelist):** All 4 models independently concluded that yfinance `info['sector']` and `info['industry']` cannot reliably identify nuclear companies. CEG shows as "Utilities," CCJ as "Energy," BWXT as "Industrials," OKLO as "Utilities." A manually maintained whitelist is the only reliable approach. This is the one gate that requires human curation.

**G2 (Market Cap $3B):** Claude proposed $500M, Grok proposed $10B, Gemini $1B, GPT $300M. Moderator sets $3B — this captures all current Tier 1 names (CEG ~$80B, VST ~$45B, GEV ~$218B, CCJ ~$30B, BWXT ~$12B) and viable Tier 2 (LEU ~$4B, SMR ~$3B) while excluding barely-in-it concept stage companies. OKLO at ~$5B passes; NNE at ~$2B correctly excluded (Tier 3 watchlist).

**G3 (FCF — Core only):** Tier 2 speculative holdings are exempt because pre-revenue or early-revenue nuclear companies will have negative FCF by definition. Requiring positive FCF for Core ensures BigClaw's base positions are generating cash.

---

## 3. Reject Rules (Hard Sell Triggers)

A holding **MUST be sold** if any reject rule triggers.

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| R1 | Removed from Whitelist | Ticker removed from nuclear whitelist by ExpertOverride | Manual | Thesis sector constraint. | Unanimous |
| R2 | Short Interest Extreme | shortPercentOfFloat > 35% | `info['shortPercentOfFloat']` | Thesis warning at 25% + 10-point operational buffer. [Threshold derived — 35% calibrated from thesis NNE treatment at ~30% plus buffer for data staleness.] | Claude/Grok |
| R3 | Core FCF Negative (Sustained) | Core holding with negative FCF for 2 consecutive periods | `info['freeCashflow']` + state tracking | Thesis: Core = "profitable, cash-generating." Sustained negative FCF means the thesis has broken for this holding. | Claude/Grok |
| R4 | Revenue Collapse (Core) | Core revenue declines >30% YoY | `info['revenueGrowth']` | Structural deterioration of nuclear operations. [Threshold estimated — calibrated from utility regulatory risk.] | Claude/Grok |

### Reject Calibration Notes

**R2 (Short Interest 35%):** The thesis flags short interest >25% as a warning. The 35% reject provides a 10-point buffer between warning and reject. This buffer is operationally important because yfinance short interest data (`shortPercentOfFloat`) can be stale by days or weeks. A 5-point buffer (reject at 30%, per Gemini) is too fragile given data quality.

**R3 (Sustained Negative FCF):** A single quarter of negative FCF can happen due to timing of capex or working capital. The "sustained" requirement (2 consecutive periods) prevents false sells while catching genuine operational deterioration.

---

## 4. Audit Rules (Weekly Compliance Checks)

Warnings for human review, not automatic sells.

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| A1 | Pre-Revenue Concentration | Pre-revenue/speculative holdings > 15% of portfolio | Portfolio state | Thesis barbell allocation. | Unanimous |
| A2 | Short Interest Elevated | shortPercentOfFloat > 25% | `info['shortPercentOfFloat']` | Thesis weekly audit. | Unanimous |
| A3 | Core Negative FCF | Core holding with freeCashflow < 0 | `info['freeCashflow']` | Thesis: Core must generate cash. | Unanimous |
| A4 | P/E Extreme (Core) | Core holding with P/E > 50 | `info['trailingPE']` | Valuation sanity check — audit, not gate. P/E is less meaningful for utilities with regulated returns but extreme values warrant review. | Claude/Grok (audit only, not gate) |
| A5 | Revenue Deterioration | revenueGrowth < 0 | `info['revenueGrowth']` | Contract pipeline concern. | Unanimous |
| A6 | Relative Underperformance vs URA | 63-day return trails URA ETF | yfinance price history for ticker and URA | Holding lagging its own sector proxy. | Claude/GPT |
| A7 | Correlation Clustering | Average 60-day pairwise correlation across holdings > 0.85 | `yf.download([tickers])` correlation matrix | Narrative concentration risk. [Threshold estimated — 0.85 as high-correlation flag.] | Unanimous |
| A8 | Liquidity Deterioration | averageVolume * currentPrice < $3M daily | `info['averageVolume']`, `info['currentPrice']` | Practical tradability. [Threshold estimated.] | GPT proposed, adopted |
| A9 | Insider Ownership Decline | heldPercentInsiders declining period-over-period | `info['heldPercentInsiders']` | Insiders understand NRC timelines better than market. [Static snapshot only — transaction-level data Not measurable via yfinance.] | Claude/Grok |
| A10 | Dividend Cut (Core) | Core holding cuts dividend | `info['dividendYield']` change detection | Operational stress signal for utilities. | Claude |

---

## 5. Signal Weight Matrix

| Signal | Weight | Justification |
|--------|--------|---------------|
| **ExpertOverride** | **2.0** | Curtis's 43-year domain expertise IS the strategy. Unanimous maximum weight across all 4 analysts. |
| **FCF** | **2.0** | Core holdings must generate cash. "Profitable, cash-generating, operating NOW." Unanimous. |
| **Revenue** | **1.5** | Revenue growth signals contract pipeline and capacity utilization. Nuclear revenue = megawatts sold. |
| **Earnings** | **1.5** | Profitability matters for Core. Less meaningful for speculative pre-revenue names. |
| **Debt** | **1.0** | Nuclear is capital-intensive by nature. Moderate weight — don't penalize normal utility leverage but flag excessive debt. |
| **ShortInterest** | **1.0** | High shorts on small nuclear names = key risk signal. Thesis explicitly monitors this. |
| **InsiderFlow** | **1.0** | Nuclear insiders understand NRC timelines and plant operations better than the market. Yfinance limitation: static snapshot only. |
| **RelativeStrength** | **1.0** | Relative performance vs sector (URA) and market matters for thematic portfolio. |
| **PE** | **0.5** | Limited utility for nuclear — regulated utilities have compressed P/E ranges, pre-revenue has no P/E. Audit use only. |
| **ROE** | **0.5** | Business quality indicator. Less meaningful for capital-intensive utilities with regulated returns. |
| **GrossMargin** | **0.5** | Operational efficiency. Varies widely between utilities (regulated margins) and fuel companies. |
| **BondYield** | **0.5** | Nuclear project economics are highly sensitive to financing costs. Rate environment matters for this sector. Claude maintains over others' 0.0. | 
| **DividendYield** | **0.5** | Core utilities pay dividends. Dividend cut = operational stress signal. 0.0 for speculative. |
| **PEG** | **0.0** | Not meaningful for thematic/sector-constrained portfolio. Nuclear companies aren't selected by PEG. |
| **PayoutSafety** | **0.5** | Relevant for Core utility holdings. |
| **RSI** | **0.0** | Minimal technical utility for thesis-driven portfolio. |
| **MACD** | **0.0** | Not applicable to thesis-driven investing. |
| **SMA50/200** | **0.0** | Core below SMA200 is an audit warning, but not a scoring signal. |
| **GoldenCross** | **0.0** | Not applicable. |

### Weight Hierarchy

1. **Tier 1 (2.0):** ExpertOverride, FCF — domain expertise and cash generation
2. **Tier 2 (1.5):** Revenue, Earnings — operational fundamentals
3. **Tier 3 (1.0):** Debt, ShortInterest, InsiderFlow, RelativeStrength — risk monitoring
4. **Tier 4 (0.5):** PE, ROE, GrossMargin, BondYield, DividendYield, PayoutSafety — supporting signals
5. **Tier 5 (0.0):** PEG, RSI, MACD, SMA, GoldenCross — not applicable to thematic investing

### Key Contrast with Other Portfolios

| Signal | Growth Value (Lynch) | Nuclear Renaissance |
|--------|---------------------|-------------------|
| ExpertOverride | 0.0 (Lynch rejected experts) | **2.0** (Curtis IS the expert) |
| PEG | 2.0 (central metric) | **0.0** (not meaningful for thematic) |
| BondYield | 0.0 (Lynch ignored macro) | **0.5** (nuclear is rate-sensitive) |
| Technical signals | All 0.0 | Mostly 0.0 but RS at 1.0 |

---

## 6. yFinance Field Map

| Field | Accessor | Usage | Reliability |
|-------|---------|-------|-------------|
| Market Cap | `info['marketCap']` | G2 | High |
| Free Cash Flow | `info['freeCashflow']` | G3, R3, A3 | High |
| Total Revenue | `info['totalRevenue']` | G4, R4, A5 | High |
| Current Price | `info['currentPrice']` | G5, A6, A8 | High |
| Short % of Float | `info['shortPercentOfFloat']` | R2, A2 | Moderate — can be stale |
| Revenue Growth | `info['revenueGrowth']` | R4, A5 | Moderate |
| Trailing P/E | `info['trailingPE']` | A4 | High (but N/A for pre-revenue) |
| Held % Insiders | `info['heldPercentInsiders']` | A9 | High — static snapshot only |
| Average Volume | `info['averageVolume']` | A8 | High |
| Dividend Yield | `info['dividendYield']` | A10 | High |
| Sector/Industry | `info['sector']`, `info['industry']` | NOT USED — whitelist instead | Unreliable for nuclear |
| URA ETF Price | `yf.Ticker('URA').history()` | A6, uranium proxy | High |
| Portfolio Correlation | `yf.download([tickers])` → `.corr()` | A7 | High (computed) |

---

## 7. Style Differentiation

### How This Portfolio Avoids Convergence

| Other Portfolio | Key Differentiator |
|----------------|-------------------|
| **Value Picks (Buffett/Graham)** | Nuclear is sector-constrained; Value is sector-agnostic. Nuclear uses ExpertOverride at 2.0; Value uses 0.0. |
| **Innovation Fund (Cathie Wood)** | Innovation targets 5 disruptive platforms; Nuclear targets one sector. Some overlap possible (OKLO) but different evaluation criteria. |
| **Growth Value (Lynch)** | Lynch uses PEG as central metric (2.0 weight); Nuclear uses PEG at 0.0. Lynch rejects macro (BondYield 0.0); Nuclear monitors rates (0.5). |
| **Income Dividends** | Income requires dividend yield >= 1.5%; Nuclear doesn't require dividends. Different universes except for utility overlap (CEG). |
| **Momentum Growth (O'Neil)** | O'Neil requires price near 52-week high, positive relative strength, market direction gate. Nuclear buys on thesis, not momentum. |
| **AI Defense & Autonomous** | Both are thematic/sector-constrained but to different sectors. Defense focuses on Pentagon procurement; Nuclear focuses on energy generation. |

The **hard sector whitelist** is the primary differentiator. No stock enters this portfolio without being manually classified as nuclear/uranium by the ExpertOverride authority. This is unique among all 7 portfolios.

---

## 8. Data Gaps and Limitations

| Item | Measurability | Workaround |
|------|-------------|-----------|
| NRC licensing status and timeline | [Not measurable via yfinance] | Manual ExpertOverride — Curtis monitors NRC ADAMS database and commissioner proceedings |
| Construction cost vs estimates | [Not measurable via yfinance] | Monitor SEC filings and earnings call transcripts |
| Uranium spot price | [Not directly available] | URA ETF as proxy: `yf.Ticker('URA')` |
| Insider buying/selling transactions | [Not measurable — static snapshot only] | `heldPercentInsiders` as proxy; consider adding OpenInsider skill |
| NRC commissioner appointments | [Not measurable via yfinance] | Manual monitoring of NRC.gov and Congressional records |
| Political/regulatory reversal risk | [Not measurable] | Increase cash reserves in election years (2028) |
| FERC interconnection queue status | [Not measurable via yfinance] | Manual monitoring of FERC filings |
| Plant capacity factor / availability | [Not measurable via yfinance] | Available from EIA and NRC databases — manual input |
| Tier classification (Core/Speculative/Watchlist) | Requires domain judgment | ExpertOverride — Curtis classifies based on NRC licensing status, revenue stage, and operational maturity |

---

## 9. Tier-Dependent Signal Adjustments

The Nuclear portfolio uniquely requires different signal treatment for Core vs Speculative holdings:

| Signal | Core (Tier 1) | Speculative (Tier 2) | Rationale |
|--------|--------------|---------------------|-----------|
| FCF | 2.0 (required positive) | 0.5 (exempt from gate) | Pre-revenue companies can't have positive FCF |
| PE | 0.5 (audit use) | 0.0 (no PE for pre-revenue) | P/E is meaningless without earnings |
| DividendYield | 0.5 | 0.0 | Speculative names don't pay dividends |
| ShortInterest | 1.0 | 1.5 (elevated) | High shorts on small speculative names = higher risk |
| Debt | 1.0 | 1.5 (elevated) | Speculative companies with high debt have higher bankruptcy risk |

---

## 10. Documents and References

### Primary Sources
- **Nuclear Renaissance Thesis** (Curtis Biggs, February 16, 2026) — 16-page foundation document covering CEG, VST, GEV, CCJ, BWXT, LEU, OKLO, SMR, NNE, FLR, URA
- **VST Deep Dive** — Comanche Peak + Comanche Circle data center campus (5 GW)
- **SMR vs OKLO Comparison** — MSR landscape analysis (Natura, Kairos, TerraPower, ACU)
- **Georgia PSC filings and Southern Company 10-K** — Vogtle cost overrun documentation
- **EO 14300** (Federal Register, January 2025) — Nuclear deployment acceleration
- **ADVANCE Act** (Public Law 118-67, July 2024) — NRC licensing reform

### Domain Knowledge Sources
- Curtis Biggs: 43 years nuclear power experience, Comanche Peak
- NRC ADAMS database (public document system)
- EIA nuclear generation data
- FERC interconnection queue filings
- NRC Inspector General reports (institutional culture documentation)

### Recommended Additional Sources
- [Requires access: NRC staff capacity analysis — internal NRC workforce planning documents]
- [Requires access: EPRI SMR deployment cost studies]
- [Requires access: Big Tech data center power procurement contracts with nuclear utilities — typically confidential]

---

## 11. Nuclear Sector Whitelist

The whitelist is maintained in `nuclear_whitelist.json` and is the authoritative source for gate G1. yfinance sector/industry fields are NOT used for nuclear classification.

**Eligible (>= $3B market cap) — 22 companies:**

| Category | Tickers | Count |
|----------|---------|-------|
| Nuclear Utilities | CEG, VST, EXC, SO, D, PEG, ETR, TLN | 8 |
| Uranium Mining/Fuel | CCJ, UEC, UUUU, NXE, DNN, LEU | 6 |
| Nuclear Manufacturing/Services | BWXT, GEV, FLR, J, CW | 5 |
| SMR Developers | OKLO, SMR | 2 |

**Watchlist ($500M-$3B) — tracked, not eligible until cap exceeds $3B:**
- NNE (Nano Nuclear, $1.1B) — concept stage, no NRC engagement
- URG (Ur-Energy, $620M) — small ISR uranium miner

**ETF Benchmarks (reference, not for purchase):**
- URA (Global X Uranium) — primary sector proxy for correlation audit and relative performance
- URNM (Sprott Uranium Miners)
- NLR (VanEck Uranium+Nuclear)

**Review:** Quarterly, or when new nuclear IPOs/SPACs emerge. ExpertOverride authority to add/remove.

---

## 12. Implementation Checklist

- [ ] Deploy `nuclear_whitelist.json` to Pi at `~/.openclaw/workspace/config/`
- [ ] Integrate whitelist into `candidate_screener.py` for Nuclear Renaissance portfolio
- [ ] Update `PORTFOLIO_STYLES.md` with these rules
- [ ] Update `style_compliance.py` gate checks to match G1-G6
- [ ] Update `style_compliance.py` reject rules to match R1-R4
- [ ] Update `style_compliance.py` audit rules to match A1-A10
- [ ] Implement tier-dependent signal weight adjustments (Core vs Speculative)
- [ ] Update `decision_engine.py` signal weights to match weight matrix
- [ ] Add correlation clustering audit (60-day pairwise, threshold 0.85)
- [ ] Add URA ETF relative performance tracking
- [ ] Add liquidity deterioration check
- [ ] Run compliance audit against current Nuclear Renaissance holdings with new rules
- [ ] Update website sources.html with thesis reference
- [ ] Update DBD Section 5 portfolio definitions
- [ ] Deploy to Pi and test with next trading cycle

---

*This document was developed through a structured multi-model AI debate. Four frontier AI models independently reviewed Curtis Biggs's 16-page Nuclear Renaissance thesis, then cross-examined each other through three rounds of structured debate. The moderator (Curtis Biggs, assisted by Claude Opus 4.6) synthesized the consensus. Tiebreaker rule: Claude/Grok agreement prevails over Gemini/GPT dissent. Market cap floor of $3B set by moderator override. All thresholds grounded in the thesis document with source citations where available. Thresholds marked [Threshold estimated] are calibrated from thesis principles but not exact thesis quotes.*
