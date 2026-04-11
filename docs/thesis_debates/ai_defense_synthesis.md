# AI Defense & Autonomous Portfolio — Investment Policy Statement

**Portfolio #7: AI Defense & Autonomous**
**Investment Style:** Pentagon Spending Thesis / AI-Enabled Defense Procurement Shift
**Thesis Foundation:** Pentagon's shift from "few and exquisite" to "many and autonomous"
**Document Version:** 1.0 — April 1, 2026
**Derived From:** Multi-model thesis debate (Claude Opus 4.6, Grok 4.20 Beta, Gemini 3.1 Pro, GPT-5.4)
**Foundation:** AI Defense & Autonomous Systems Research Report (February 16, 2026, 10 pages)
**Approved By:** Curtis Biggs (Moderator)

---

## 1. Investment Thesis

### 1.1 Core Philosophy

The Pentagon is undergoing a generational procurement shift from "few and exquisite" weapons platforms to "many and autonomous." Ukraine proved that cheap, AI-enabled autonomous systems are the future of warfare. The U.S. defense budget is approaching ~$1 trillion for FY2026, with a significant and growing share directed toward autonomous systems, AI-powered command and control, and unmanned platforms across all domains.

This portfolio targets companies capturing outsized growth from five specific Pentagon programs:

| Program | Description | Investment Implication |
|---------|-------------|----------------------|
| **Replicator Initiative** | Thousands of autonomous systems across all domains within 18-24 months | Small autonomous drone manufacturers, AI software |
| **JADC2** | AI-powered networking of sensors, shooters, and decision-makers | C2 software, sensor fusion, networking |
| **CCA (Collaborative Combat Aircraft)** | Autonomous wingman drones alongside F-35/NGAD | Autonomous aviation platforms |
| **FLRAA (V-280 Valor)** | Bell's replacement for Black Hawk fleet with autonomous capabilities | Textron/Bell, autonomous flight systems |
| **Counter-UAS** | Defeating enemy drones from $500 hobby drones to sophisticated ISR | Electronic warfare, directed energy, kinetic interceptors |

The portfolio has a unique edge: input from Curtis Biggs and retired Bell Helicopter executives who understand defense procurement, supply chain dynamics, and program execution from the inside. ExpertOverride is weighted at the maximum (2.0).

### 1.2 Tier System

| Tier | Definition | Examples | Allocation |
|------|-----------|---------|-----------|
| **Tier 1: Genuine AI/Autonomous** | AI/autonomy is core revenue | PLTR, KTOS, AVAV, LDOS | High conviction |
| **Tier 2: Strong AI Pivot** | Traditional primes genuinely transforming | NOC, LHX, RTX, BAH | Core holdings |
| **Tier 3: Traditional + AI Upside** | AI is additive, not transformational | LMT, GD, TXT | Steady allocation |
| **Tier 4: Speculative** | Pre-profit, high short interest | RCAT | Minimal allocation |

### 1.3 Risk Philosophy

**Defensive Beta as Feature:** The portfolio is designed to have a weighted beta of ~0.65 — defensive by nature. Defense stocks historically exhibit lower market correlation, providing portfolio-level diversification for BigClaw's overall allocation.

**Revenue Growth is the Thesis Signal:** If the Pentagon procurement shift is real, companies positioned for it will show accelerating revenue growth. Declining revenue is the primary signal that the thesis may be breaking for a specific holding.

**FCF Differentiates Survivors:** Cash flow generation separates self-funding defense primes from cash-burning speculative names. Companies like AVAV with deeply negative FCF and 7.4-month cash runway carry existential risk that must be sized accordingly.

**Pre-Profit Concentration Cap:** No more than 25% of the portfolio should be in pre-profit or negative-FCF companies. The asymmetric upside of speculative defense AI companies is real, but concentrated exposure to cash burners can destroy capital if program funding slips.

### 1.4 Behavior Across Market Regimes

| Regime | Expected Behavior | Portfolio Action |
|--------|-------------------|-----------------|
| Bull market + defense spending growth | Excellent — thesis tailwind | Hold, add on dips in Tier 1/2 |
| Bull market + defense budget flat/cut | Underperforms — thesis headwind | Monitor program-specific funding; may need to trim |
| Bear market / recession | Defensive — low beta helps | Core defense primes hold up; speculative names hit hard |
| Rising rates | Mixed — defense primes unaffected; speculative names hurt by higher discount rates | Monitor cash-burn names |
| Political shift (defense-skeptical administration) | Medium risk — programs have bipartisan support but funding levels could change | Increase cash, favor primes over speculative |
| Budget sequestration | Severe — across-the-board cuts hit all defense | Defensive posture; favor companies with international revenue |
| Major defense incident / war escalation | Generally positive for defense stocks | Thesis acceleration; monitor for overvaluation |

### 1.5 Known Weaknesses

1. **Single-Narrative Exposure:** All positions are tied to "Pentagon buys autonomous/AI." If Congress cuts autonomous programs specifically, or if AI defense spending disappoints, all positions are correlated.

2. **Valuation Stretch on Pure-Play AI Names:** PLTR at P/E 208x and KTOS at P/E 685x (thesis data) are priced for perfection. The thesis can be right but the price can still be wrong.

3. **Pre-Profit Risk:** RCAT and potentially KTOS/AVAV are burning cash. Program delays or funding lapses could force dilutive capital raises.

4. **Backlog and Contract Visibility Not Measurable:** Defense company fundamentals are driven by backlog, book-to-bill ratios, and contract type (cost-plus vs fixed-price). None of this is available via yfinance. The portfolio relies on ExpertOverride for these qualitative assessments.

5. **Concentrated in U.S. Defense:** No international defense companies. This is intentional (Pentagon focus) but limits diversification within the theme.

---

## 2. Gate Rules (Hard Buy Filters)

A candidate is **BLOCKED** if any gate fails.

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| G1 | Defense Sector Whitelist | Ticker must be on manually maintained defense/AI whitelist | Manual list | Thesis: "100% Defense/Aerospace." yfinance sector/industry is unreliable (PLTR shows as "Technology"). | Unanimous |
| G2 | U.S. Domicile | country == "United States" | `info['country']` | Pentagon procurement focuses on US companies. ITAR restrictions. | Claude proposed, unanimous |
| G3 | Market Cap Floor | marketCap >= $3B | `info['marketCap']` | Moderator override. Ensures institutional tradability. [Moderator decision — consistent with Nuclear portfolio.] | Moderator |
| G4 | Liquidity Floor | avgVolume * currentPrice >= $5M daily | `info['averageVolume']`, `info['currentPrice']` | Practical tradability for position sizing. [Threshold estimated.] | Claude/GPT |
| G5 | Revenue Existence | totalRevenue > 0 (any amount) | `info['totalRevenue']` | Thesis retains only companies with revenue. Even Tier 4 RCAT has some revenue. | Claude/Grok |
| G6 | Data Sufficiency | Key fields (revenue, sector, price) not None/NaN | Multiple | Implementation requirement. | Unanimous |

### Gate Calibration Notes

**G1 (Defense Whitelist):** Like Nuclear, yfinance cannot reliably identify defense companies. PLTR shows as "Technology," BAH as "Information Technology Services," KTOS as "Aerospace & Defense." A manually curated whitelist is the only reliable approach.

**G3 (Market Cap $3B):** Consistent with Nuclear portfolio. Ensures all current thesis holdings qualify (smallest is RCAT — need to verify) while excluding concept-stage micro-caps.

---

## 3. Reject Rules (Hard Sell Triggers)

A holding **MUST be sold** if any reject rule triggers.

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| R1 | Removed from Whitelist | Ticker removed by ExpertOverride | Manual | Thesis sector constraint. | Unanimous |
| R2 | Revenue Collapse | revenueGrowth < -20% YoY | `info['revenueGrowth']` | [Calibrated from thesis — BAH retained at -10.2%, so reject must be below that. -20% = clearly broken.] | Claude/Grok (Gemini/GPT wanted -5%, overruled — would force-sell BAH against thesis) |
| R3 | Short Interest Extreme | shortPercentOfFloat > 30% | `info['shortPercentOfFloat']` | Thesis flags RCAT short interest as risk. [Threshold estimated — 30% as danger level for defense names.] | Claude/Grok |
| R4 | Leveraged Cash Burner | D/E > 200 AND revenueGrowth <= 0 | `info['debtToEquity']`, `info['revenueGrowth']` | Combined signal: high debt + shrinking revenue = thesis broken. | Claude/Grok |

### Reject Calibration Notes

**R2 (Revenue -20%):** This was the most contested rule. Gemini and GPT wanted -5%, which would have forced a sell of BAH — directly contradicting the thesis author's decision to retain it at -10.2%. Claude's graduated approach (audit at any negative, escalation at -10% sustained, hard reject at -20%) respects the thesis while catching severe deterioration. Grok conceded to Claude's magnitude-based approach.

---

## 4. Audit Rules (Weekly Compliance Checks)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| A1 | Revenue Declining | revenueGrowth < 0 | `info['revenueGrowth']` | Thesis: revenue growth is the primary thesis confirmation signal. | Unanimous |
| A2 | Revenue Decline Escalation | revenueGrowth < -10% for two consecutive checks | `info['revenueGrowth']` + state tracking | Escalation toward R2 reject. | Claude proposed |
| A3 | Short Interest Elevated | shortPercentOfFloat > 20% | `info['shortPercentOfFloat']` | Thesis flags RCAT at high short interest. | Unanimous |
| A4 | Negative FCF | freeCashflow < 0 | `info['freeCashflow']` | Thesis flags KTOS and AVAV cash burn. | Unanimous |
| A5 | Pre-Profit Concentration | Pre-profit holdings > 25% of portfolio | Portfolio state | Risk management — cap exposure to cash-burning names. | Claude/Grok |
| A6 | P/E Extreme | trailingPE > 100 for non-speculative holdings | `info['trailingPE']` | Thesis flags PLTR at 208x, KTOS at 685x as risk. Valuation stretch warning. | Claude/Grok (audit, not gate) |
| A7 | Debt Elevated | debtToEquity > 150 | `info['debtToEquity']` | Risk monitoring. Defense companies can carry leverage but extremes warrant review. | Unanimous |
| A8 | Gross Margin Low | grossMargins < 15% | `info['grossMargins']` | Business quality check. Defense primes typically 15-30%+. Below 15% = cost pressure. | Claude proposed |
| A9 | Insider Ownership Decline | heldPercentInsiders declining | `info['heldPercentInsiders']` | Insider selling in defense = may know about program cancellations. [Static snapshot only.] | Claude/Grok |
| A10 | Share Dilution | sharesOutstanding increasing >10% YoY | `info['sharesOutstanding']` + state tracking | Speculative names may dilute to fund operations. | Unanimous |
| A11 | Relative Underperformance vs ITA | 63-day return trails ITA (iShares Defense ETF) | yfinance price history | Holding lagging its own sector. | Claude/GPT |

---

## 5. Signal Weight Matrix

| Signal | Weight | Justification |
|--------|--------|---------------|
| **ExpertOverride** | **2.0** | Curtis + Bell Helicopter executive insight on programs, supply chain, procurement. Unanimous. |
| **Revenue** | **2.0** | Revenue growth IS thesis confirmation. If Pentagon is buying autonomous, revenue grows. Unanimous. |
| **FCF** | **2.0** | Separates self-funding primes from cash-burning speculative names. Thesis explicitly flags FCF for every holding. Claude/Grok. |
| **Earnings** | **1.5** | Profitability matters for primes. Less meaningful for Tier 4 speculative pre-profit. |
| **PE** | **1.5** | Thesis tracks P/E for every holding and flags PLTR/KTOS as valuation risk. Claude maintains over others' 1.0. |
| **Debt** | **1.0** | Defense is not capital-intensive like nuclear. Moderate weight — flag extremes. |
| **RelativeStrength** | **1.0** | Sector momentum matters for thematic portfolios. Performance vs ITA. |
| **GrossMargin** | **1.0** | Business quality. Defense primes should maintain healthy margins. |
| **ROE** | **1.0** | Business quality indicator. |
| **ShortInterest** | **1.0** | Important for speculative Tier 4 names. Thesis explicitly monitors. |
| **InsiderFlow** | **1.0** | Defense insiders know about program funding. [Static yfinance snapshot only.] |
| **PayoutSafety** | **0.5** | Some primes pay dividends. Not primary for growth-oriented defense thesis. |
| **PEG** | **0.5** | Limited utility — many defense names don't have clean PEG data. |
| **DividendYield** | **0.0** | Not a dividend portfolio. Unanimous (Claude, Gemini, GPT; Grok conceded). |
| **BondYield** | **0.0** | Defense spending is not rate-sensitive. Budgets set by Congress, not Fed. |
| **RSI** | **0.0** | Thesis is fundamentals-driven, not technical. |
| **MACD** | **0.0** | Not applicable. |
| **SMA50/200** | **0.0** | Not applicable. |
| **GoldenCross** | **0.0** | Not applicable. |

### Weight Hierarchy
1. **Tier 1 (2.0):** ExpertOverride, Revenue, FCF — domain expertise, thesis confirmation, cash generation
2. **Tier 2 (1.5):** Earnings, PE — profitability and valuation discipline
3. **Tier 3 (1.0):** Debt, RelativeStrength, GrossMargin, ROE, ShortInterest, InsiderFlow — risk monitoring
4. **Tier 4 (0.5):** PayoutSafety, PEG — minor
5. **Tier 5 (0.0):** DividendYield, BondYield, RSI, MACD, SMA, GoldenCross — not applicable

---

## 6. yFinance Field Map

| Field | Accessor | Usage | Reliability |
|-------|---------|-------|-------------|
| Country | `info['country']` | G2 | High |
| Market Cap | `info['marketCap']` | G3 | High |
| Average Volume | `info['averageVolume']` | G4 | High |
| Current Price | `info['currentPrice']` | G4, A11 | High |
| Total Revenue | `info['totalRevenue']` | G5 | High |
| Revenue Growth | `info['revenueGrowth']` | R2, A1, A2 | Moderate — TTM, can lag |
| Short % of Float | `info['shortPercentOfFloat']` | R3, A3 | Moderate — can be stale |
| Debt to Equity | `info['debtToEquity']` | R4, A7 | High |
| Free Cash Flow | `info['freeCashflow']` | A4 | High |
| Trailing P/E | `info['trailingPE']` | A6 | High (None for pre-profit) |
| Gross Margins | `info['grossMargins']` | A8 | High |
| Held % Insiders | `info['heldPercentInsiders']` | A9 | High — static snapshot |
| Shares Outstanding | `info['sharesOutstanding']` | A10 | High |
| Sector/Industry | `info['sector']`, `info['industry']` | NOT USED as gate — whitelist instead | Unreliable for defense AI |
| ITA ETF Price | `yf.Ticker('ITA').history()` | A11 | High |

---

## 7. Style Differentiation

| Other Portfolio | Key Differentiator |
|----------------|-------------------|
| **Value Picks (Buffett/Graham)** | Defense is sector-constrained; Value is sector-agnostic. Defense tolerates high P/E for thesis names; Value demands P/E < 25. |
| **Innovation Fund (Cathie Wood)** | Both include AI but different sectors. Defense = military AI; Innovation = commercial disruptive tech. PLTR could overlap. |
| **Growth Value (Lynch)** | Lynch uses PEG and ignores macro; Defense uses revenue growth and sector expertise. Zero overlap in methodology. |
| **Income Dividends** | Defense is not an income portfolio. DividendYield weighted at 0.0. |
| **Momentum Growth (O'Neil)** | O'Neil uses technical signals (RS, new highs); Defense uses fundamentals + domain expertise. |
| **Nuclear Renaissance** | Both are thematic/sector-constrained but completely different sectors. Nuclear = energy generation; Defense = military procurement. |

The **hard sector whitelist + ExpertOverride at 2.0 + revenue as primary signal** is the unique combination. No other BigClaw portfolio uses this structure.

---

## 8. Data Gaps and Limitations

| Item | Measurability | Workaround |
|------|-------------|-----------|
| Defense contract backlog | [Not measurable via yfinance] | Monitor 10-K filings; ExpertOverride |
| Book-to-bill ratio | [Not measurable via yfinance] | Monitor earnings calls |
| Contract type (cost-plus vs fixed-price) | [Not measurable via yfinance] | ExpertOverride assessment |
| Program-specific funding levels | [Not measurable via yfinance] | Monitor DoD budget requests and appropriations bills |
| DoD revenue purity (% of revenue from defense) | [Not measurable via yfinance] | Manual classification via ExpertOverride |
| Insider transaction flow (Form 4) | [Not measurable — static snapshot only] | `heldPercentInsiders` as proxy |
| Quarterly revenue/balance sheet changes | Requires `quarterly_financials` parsing | TTM from `info` as approximation |
| ITA ETF | Available via `yf.Ticker('ITA')` | Primary sector benchmark for relative performance |

---

## 9. Defense Sector Whitelist

Like the Nuclear portfolio, a manually curated whitelist is required. Current thesis holdings form the core:

**Tier 1 — Genuine AI/Autonomous:**
- PLTR (Palantir) — AI software, DoD analytics, Maven/Gotham
- KTOS (Kratos Defense) — Tactical drones, CCA, target drones
- AVAV (AeroVironment) — Small UAS, Switchblade loitering munitions
- LDOS (Leidos) — IT services, JADC2, intel community

**Tier 2 — Strong AI Pivot:**
- NOC (Northrop Grumman) — B-21, autonomous systems, space
- LHX (L3Harris) — Sensors, C2, electronic warfare
- RTX (RTX Corp) — Missiles, engines, radar
- BAH (Booz Allen Hamilton) — AI/analytics for DoD

**Tier 3 — Traditional + AI Upside:**
- LMT (Lockheed Martin) — F-35, JADC2, space
- GD (General Dynamics) — Land systems, IT, Gulfstream
- TXT (Textron) — Bell V-280 Valor (FLRAA), Shadow UAS

**Tier 4 — Speculative:**
- RCAT (Red Cat Holdings) — Small drones, Teal drones for DoD

**ETF Benchmark:**
- ITA (iShares U.S. Aerospace & Defense ETF) — sector benchmark for relative performance

**Review:** Quarterly, or when new defense AI companies IPO/SPAC. ExpertOverride authority to add/remove.

---

## 10. Implementation Checklist

- [ ] Create and deploy defense sector whitelist to Pi (`~/.openclaw/workspace/config/defense_whitelist.json`)
- [ ] Integrate whitelist into `candidate_screener.py` for AI Defense portfolio
- [ ] Update `PORTFOLIO_STYLES.md` with these rules
- [ ] Update `style_compliance.py` gate checks to match G1-G6
- [ ] Update `style_compliance.py` reject rules to match R1-R4
- [ ] Update `style_compliance.py` audit rules to match A1-A11
- [ ] Update `decision_engine.py` signal weights to match weight matrix
- [ ] Add U.S. domicile gate (G2)
- [ ] Add graduated revenue decline handling (A1 → A2 → R2)
- [ ] Add pre-profit concentration tracking (A5)
- [ ] Add ITA relative performance tracking (A11)
- [ ] Run compliance audit against current AI Defense holdings with new rules
- [ ] Update website sources.html with thesis reference
- [ ] Update DBD Section 5 portfolio definitions
- [ ] Deploy to Pi and test with next trading cycle

---

*This document was developed through a structured multi-model AI debate. Four frontier AI models independently reviewed the AI Defense & Autonomous Systems thesis, then cross-examined each other through three rounds of structured debate (47% convergence — highest of all portfolios debated). Tiebreaker: Claude/Grok agreement prevails. Market cap floor of $3B set by moderator override. Revenue decline reject at -20% per Claude/Grok — the -5% threshold proposed by Gemini/GPT was overruled because it would force-sell BAH, contradicting the thesis author's explicit retention decision.*
