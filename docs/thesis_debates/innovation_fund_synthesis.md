# Innovation Fund Portfolio — Investment Policy Statement

**Portfolio #2: Innovation Fund**
**Investment Style:** Disruptive Innovation / Thematic Growth
**Modeled After:** Cathie Wood / ARK Invest
**Document Version:** 1.0 — April 1, 2026
**Derived From:** Multi-model thesis debate (Claude Opus 4.6, Grok 4.20 Beta, Gemini 3.1 Pro, GPT-5.4)
**Approved By:** Curtis Biggs (Moderator)

---

## 1. Investment Thesis

### 1.1 Core Philosophy

Cathie Wood's ARK Invest methodology targets companies enabling or benefiting from technologically-enabled disruption across five converging innovation platforms. The approach deliberately tolerates extreme valuations, pre-profit companies, and high volatility in exchange for transformative long-term growth potential on a 7+ year horizon.

This is the anti-Value portfolio. Where Buffett demands P/E <= 25, Wood has no P/E ceiling. Where Graham demands earnings stability, Wood invests in pre-revenue companies. Where O'Neil demands near-highs, Wood buys deep drawdowns in high-conviction names. The defining characteristic is willingness to endure 50-70% drawdowns for the potential of 10-50x returns.

> "We are investing in innovation that we believe will change the way the world works."
> — Cathie Wood, ARK Invest (repeated across multiple interviews, 2020-2024)

### 1.2 The Five Innovation Platforms

Every holding must connect to at least one of these five converging technology platforms:

| Platform | Examples | yfinance Measurability |
|----------|---------|----------------------|
| 1. AI / Machine Learning / Compute | NVDA, PLTR, TSLA (FSD) | [Not directly measurable — requires manual classification] |
| 2. Robotics / Autonomous Systems | TSLA (robotaxi), autonomous vehicles | [Not directly measurable] |
| 3. Energy Storage / Clean Energy | Battery tech, solar, grid storage | [Not directly measurable] |
| 4. Genomics / Multiomics / Precision Medicine | CRSP, gene editing, diagnostics | [Not directly measurable] |
| 5. Blockchain / Fintech / Crypto / Next-Gen Internet | COIN, HOOD, digital wallets | [Not directly measurable] |

**Source:** ARK Big Ideas reports (2017-2025); ARKK Prospectus; Cathie Wood conference presentations.

**Critical Note:** Innovation platform alignment is the defining filter but is **[Not measurable via yfinance]**. Implementation requires a manually curated innovation whitelist (similar to Nuclear and Defense portfolios), with ExpertOverride authority to add/remove tickers.

**Multi-Platform Convergence = Highest Conviction:** TSLA spans 3 platforms (AI, autonomous, energy storage). Companies touching multiple platforms represent convergence opportunities — ARK's core thesis.

### 1.3 What Makes This Portfolio Unique

| Feature | Innovation Fund | Other Portfolios |
|---------|----------------|-----------------|
| P/E gate | None (0.0 weight) | 1.0-2.0 weight everywhere else |
| Earnings requirement | None — pre-profit tolerated | Every other portfolio requires positive EPS |
| Dividend requirement | Anti-dividend (yield > 3% = reject) | Income requires yield >= 1.5% |
| Revenue growth gate | >= 15% YoY | Most portfolios don't gate on revenue |
| Valuation ceiling | None | Value: P/E <= 25, Growth: PEG < 1.0 |
| Drawdown tolerance | 50-70% acceptable if thesis intact | Most have 7-8% to 20% stop-losses |
| Time horizon | 7+ years | Most are 1-3 years |

### 1.4 Risk Philosophy

**Concentration by Conviction.** ARK runs concentrated portfolios (ARKK top 10 = ~50% of fund). BigClaw's 10-max-holdings constraint aligns with this. Each slot is highest conviction across the five platforms.

**Revenue is the Fundamental Signal.** Since earnings, P/E, PEG, and ROE are all zeroed out, revenue growth is the primary measurable fundamental. If a company is disrupting its market, revenue grows. If revenue stalls, the disruption thesis may be failing.

**Cash Burn is the Existential Risk.** Pre-profit companies can disrupt markets for years before monetizing. But they need cash to survive. Cash runway (totalCash / quarterly burn rate) is the critical risk metric. A company with <4 quarters of cash runway needs a capital raise — and dilution may destroy returns.

### 1.5 Behavior Across Market Regimes

| Regime | Expected Behavior | Strategy |
|--------|-------------------|----------|
| Bull market + innovation narrative | Exceptional — ARKK returned 153% in 2020 | Fully invested, add on breakouts |
| Bull market + value rotation | Severe underperformance — 2022 saw ARKK -67% | Hold if theses intact; this is the drawdown you tolerate |
| Bear market | Worst portfolio in BigClaw | Cash runway audits become critical; weakest names may need trimming |
| Rising rates | Devastating — high-duration growth names compress first | Accept pain; 7+ year horizon means short-term rate cycles matter less |
| Recovery after crash | Best buying opportunity | Add aggressively at depressed prices if revenue growth continues |

### 1.6 Known Weaknesses

1. **Extreme Drawdown Risk.** ARKK fell 67% in 2022. This portfolio will have the highest volatility and largest drawdowns in BigClaw. By design.
2. **Innovation Platform Classification is Subjective.** Is Deere a farm equipment company or a robotics/AI company? The line is blurry. Manual classification required.
3. **Revenue Growth Data Lag.** `info['revenueGrowth']` is trailing twelve months. A company's disruption thesis could fail a quarter before the TTM metric catches it.
4. **Cash Runway is Fragile to Compute.** `totalCash / (abs(freeCashflow) / 4)` is an approximation. Actual runway depends on burn rate trajectory, which may accelerate.
5. **No Valuation Floor.** Without any P/E, PEG, or P/S gate, this portfolio can hold stocks at any valuation. The risk of "right thesis, wrong price" is real.

---

## 2. Gate Rules (Hard Buy Filters)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| G1 | Innovation Platform Alignment | Must connect to at least one of 5 platforms | Manual whitelist (ExpertOverride) | ARK Big Ideas reports; ARKK Prospectus | Unanimous — [Not measurable via yfinance] |
| G2 | Revenue Growth | revenueGrowth >= 15% | `info['revenueGrowth']` | ARK Big Ideas 2021 p.17: models 15-50%+ CAGRs. [Threshold estimated — calibrated from ARK holdings analysis] | Claude/Grok/Gemini (GPT wanted >0%, overruled) |
| G3 | Dividend Yield Cap | dividendYield < 3% | `info['dividendYield']` | No ARKK holding has ever yielded above ~2%. High yield signals maturity, antithetical to ARK. [Threshold estimated — 1% buffer above observed max] | Claude/Gemini (GPT/Grok wanted warning only, overruled) |
| G4 | Common Equity | quoteType == 'EQUITY' | `info['quoteType']` | Excludes ETFs, preferreds | Unanimous |
| G5 | Market Cap Floor | marketCap >= $3B | `info['marketCap']` | Moderator override. | Moderator |
| G6 | Data Sufficiency | revenueGrowth not None/NaN | Multiple | Implementation requirement | Unanimous |

### Gate Calibration Notes

**G1 (Innovation Whitelist):** The most important gate and the one that cannot be automated. A stock must be manually classified as connected to at least one of the 5 innovation platforms. This classification is the portfolio's defining characteristic.

**G2 (Revenue >= 15%):** GPT-5.4 wanted >0% (too weak — admits AT&T and IBM). Claude/Grok/Gemini argued 15% based on ARK's modeled CAGRs and empirical analysis of ARKK holdings at initial purchase. 15% is the minimum observed growth rate for ARK-style companies.

**G3 (Dividend < 3%):** This is the inverse of Income Dividends' gate. High yield signals a mature, slow-growth business — the opposite of what this portfolio seeks. No ARKK holding has ever yielded above ~2%.

**What's NOT a gate:** P/E, PEG, ROE, earnings positivity, debt-to-equity, gross margin. All intentionally absent. This portfolio buys pre-profit disruptors that would fail every other BigClaw portfolio's gates.

---

## 3. Reject Rules (Hard Sell Triggers)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| R1 | Revenue Decline (Sustained) | revenueGrowth < 0 for 2 consecutive periods | `info['revenueGrowth']` + state | If revenue is declining, the disruption thesis is failing. | Claude/Grok |
| R2 | Innovation Platform Removed | Ticker removed from innovation whitelist by ExpertOverride | Manual | Company no longer qualifies as disruptive. | Unanimous |
| R3 | Dividend Yield Breach | dividendYield >= 5% | `info['dividendYield']` | Company has pivoted to mature income strategy. [Threshold estimated] | Claude |
| R4 | Cash Runway Critical | totalCash / (abs(freeCashflow) / 4) < 4 quarters AND no recent capital raise | `info['totalCash']`, `info['freeCashflow']` | Existential risk for pre-profit companies. [Approximate computation] | Claude/Grok |

### Reject Calibration Notes

**R1 (Revenue Decline Sustained):** Revenue is the only fundamental signal that matters for this portfolio. Two consecutive negative periods means the market isn't adopting the company's innovation. One bad quarter can be explained; two is a pattern.

**R4 (Cash Runway):** Only applies to pre-profit companies (positive FCF companies are self-funding). This is the Innovation Fund's equivalent of the stop-loss — it catches companies about to run out of money.

---

## 4. Audit Rules (Weekly Compliance Checks)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| A1 | Revenue Deceleration | revenueGrowth declining vs prior period | `info['revenueGrowth']` + state | Early warning for R1 | Claude |
| A2 | Dividend Yield Rising | dividendYield > 1% | `info['dividendYield']` | Approaching maturity signal — unusual for innovation companies | Claude |
| A3 | Cash Burn Acceleration | freeCashflow negative and worsening | `info['freeCashflow']` + state | Pre-profit companies burning faster | Claude/Grok |
| A4 | Share Dilution | sharesOutstanding increasing >15% YoY | `info['sharesOutstanding']` + state | Capital raises diluting existing holders | Claude/Grok |
| A5 | Short Interest High | shortPercentOfFloat > 20% | `info['shortPercentOfFloat']` | Market skepticism on innovation thesis | Unanimous |
| A6 | Concentration Risk | Single holding > 15% of portfolio | Portfolio state | ARKK top holding typically ~10%. BigClaw 10-max constraint. | Claude |

---

## 5. Signal Weight Matrix

| Signal | Weight | Justification |
|--------|--------|---------------|
| **Revenue** | **2.0** | The only fundamental signal. Revenue growth = disruption happening. Unanimous. |
| **ExpertOverride** | **2.0** | Innovation platform classification is manual. Maximum weight. Unanimous. |
| **RelativeStrength** | **1.0** | Momentum within innovation space. Moderate. |
| **FCF** | **1.0** | Cash generation matters for survival. Not primary but important for risk. |
| **ShortInterest** | **1.0** | High shorts on innovation names = either smart bears or squeeze potential. |
| **InsiderFlow** | **0.5** | Insider activity. Minor. |
| **GrossMargin** | **0.5** | Business model quality. Some relevance for software companies. |
| **Debt** | **0.5** | Leverage risk for pre-profit companies. |
| **SMA50/200** | **0.0** | Wood buys drawdowns, not breakouts. |
| **RSI** | **0.0** | Not relevant to thesis-driven investing. |
| **MACD** | **0.0** | Not relevant. |
| **GoldenCross** | **0.0** | Not relevant. |
| **PE** | **0.0** | Explicitly rejected. Wood ignores P/E. Unanimous. |
| **PEG** | **0.0** | Not applicable to pre-profit companies. Unanimous. |
| **ROE** | **0.0** | Not applicable to pre-profit. Unanimous. |
| **Earnings** | **0.0** | Pre-profit tolerated. Earnings not required. Unanimous. |
| **DividendYield** | **0.0** | Anti-dividend portfolio. Unanimous. |
| **PayoutSafety** | **0.0** | Not applicable. Unanimous. |
| **BondYield** | **0.0** | Wood ignores macro. |

### Weight Hierarchy — The Disruptor Profile
1. **Tier 1 (2.0):** Revenue, ExpertOverride — growth + platform classification
2. **Tier 2 (1.0):** RelativeStrength, FCF, ShortInterest — momentum, survival, market sentiment
3. **Tier 3 (0.5):** InsiderFlow, GrossMargin, Debt — minor
4. **Tier 4 (0.0):** Everything else — 11 signals at zero. This portfolio ignores more signals than any other.

---

## 6. Style Differentiation

This portfolio is defined by what it DOESN'T require:

| What Other Portfolios Require | Innovation Fund |
|-------------------------------|----------------|
| Positive earnings | Not required |
| P/E ceiling | None |
| Positive FCF | Not required (gate) |
| Dividends | Anti-dividend (yield > 3% = blocked) |
| Low debt | Not required |
| Near 52-week high | Buys drawdowns |
| Market direction gate | None |

The **innovation platform whitelist + revenue growth gate + anti-dividend gate** is the unique combination. No other BigClaw portfolio accepts pre-profit companies, ignores P/E entirely, and actively blocks dividend payers.

---

## 7. Implementation Checklist

- [ ] Create and maintain innovation platform whitelist (manual, ExpertOverride)
- [ ] Map each whitelisted ticker to 1-5 innovation platforms
- [ ] Update `PORTFOLIO_STYLES.md` with these rules
- [ ] Update `style_compliance.py` — minimal gates, revenue-focused
- [ ] Update `decision_engine.py` — 11 signals at 0.0, revenue + ExpertOverride at 2.0
- [ ] Implement cash runway computation for pre-profit reject (R4)
- [ ] Implement dividend yield cap as gate (G3)
- [ ] Run compliance audit against current Innovation Fund holdings
- [ ] Deploy to Pi and test

---

*Tiebreaker: Claude/Grok prevails. Revenue gate at 15% (not GPT's 0%). Dividend cap at 3% as hard gate (not GPT/Grok's warning-only). This is the most permissive portfolio in BigClaw by design — 11 of 20 signals at zero weight. The thesis is that transformative innovation is worth tolerating extreme volatility, pre-profit companies, and valuations that would horrify every other portfolio's rules.*
