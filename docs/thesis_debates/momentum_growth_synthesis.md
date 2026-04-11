# Momentum Growth Portfolio — Investment Policy Statement

**Portfolio #5: Momentum Growth**
**Investment Style:** CANSLIM Momentum
**Modeled After:** William O'Neil (*How to Make Money in Stocks*, 4th Edition)
**Document Version:** 1.0 — April 1, 2026
**Derived From:** Multi-model thesis debate (Claude Opus 4.6, Grok 4.20 Beta, Gemini 3.1 Pro, GPT-5.4)
**Approved By:** Curtis Biggs (Moderator)

---

## 1. Investment Thesis

### 1.1 Core Philosophy

William O'Neil's CANSLIM methodology combines fundamental strength with technical momentum. Unlike every other BigClaw portfolio, Momentum Growth buys stocks that are **already winning** — near 52-week highs with accelerating earnings — and sells them quickly when they stop. O'Neil's system is sector-agnostic, technically driven, and has a hard market direction gate that stops all buying in bear markets.

O'Neil averaged 40% annual returns and founded Investor's Business Daily on these principles. His methodology is documented in *How to Make Money in Stocks* (HMMIS), now in its 4th edition, with more precision than perhaps any other investment approach.

### 1.2 The CANSLIM Acronym

| Letter | Criterion | BigClaw Implementation |
|--------|-----------|----------------------|
| **C** | Current Quarterly Earnings >= 25% YoY | Gate: `earningsQuarterlyGrowth` >= 0.25 |
| **A** | Annual Earnings Growth + ROE >= 17% | Gate: `returnOnEquity` >= 0.17, positive annual growth |
| **N** | New Products, New Highs | Gate: Price within 15% of 52-week high |
| **S** | Supply and Demand | Audit: Watch for share dilution > 10% YoY |
| **L** | Leader | Gate: 3-month relative strength vs S&P 500 positive |
| **I** | Institutional Sponsorship | Gate: 20% <= institutional ownership <= 95% |
| **M** | Market Direction | Gate: S&P 500 above 200-day SMA |

**Source:** *HMMIS* 4th Ed., Chapters 1-9

### 1.3 What Makes This Portfolio Unique

This is the **only BigClaw portfolio that stops buying in bear markets** (M gate). It's the only one that requires price near 52-week highs (buys strength, not weakness). It's the only one where technical signals carry maximum weight. And it has the strictest sell discipline: 7-8% stop-loss and 20-25% profit-taking are hardcoded from O'Neil.

| Feature | Momentum Growth | Every Other Portfolio |
|---------|----------------|---------------------|
| Buys near highs | Yes (within 15%) | No — most buy dips |
| Market direction gate | Yes (SPY > SMA200) | No |
| Technical signal weights | Maximum (2.0) | Zero (0.0) |
| P/E weight | 0.0 | 1.0-2.0 |
| Dividend weight | 0.0 | 0.5-2.0 |
| Stop-loss | 7-8% hard | None (most hold through drawdowns) |

### 1.4 Risk Philosophy

**Cut Losses Short, Let Winners Run.** O'Neil's #1 rule. The 7-8% stop-loss is non-negotiable — it prevents small losses from becoming catastrophic. The 20-25% profit-taking rule for average stocks ensures gains are captured. Exceptional winners (3x earnings acceleration) can be held longer.

> "The whole secret to winning big in the stock market is not to be right all the time, but to lose the least amount possible when you're wrong."
> — *HMMIS* 4th Ed., Ch. 10, p. 229

**Market Direction is the Master Switch.** When the S&P 500 drops below its 200-day SMA, this portfolio stops buying entirely. Three of four winning stocks decline in bear markets regardless of their fundamentals. This is the single most important risk control.

> "You can be right on every other factor, but if you're wrong on the direction of the general market, three out of four of your stocks will plummet along with the market averages."
> — *HMMIS* 4th Ed., Ch. 9

### 1.5 Behavior Across Market Regimes

| Regime | Expected Behavior | Strategy |
|--------|-------------------|----------|
| Bull market | Excellent — core regime for CANSLIM | Fully invested; buy breakouts near new highs |
| Bear market | **Cash.** M gate stops all buying. | Hold cash. Wait for market to reclaim SMA200. |
| Correction (-10-20%) | Partial cash if SPY near/below SMA200 | Tighten stops; stop new buys if M gate fails |
| Recovery / early bull | Best period — fresh breakouts with accelerating earnings | Aggressive buying as market clears SMA200 |
| Sideways / choppy | Difficult — breakouts fail, whipsaws | Smaller position sizes; tighter stops |

### 1.6 Known Weaknesses

1. **Whipsaw Risk.** When SPY oscillates around SMA200, the M gate flips on/off rapidly. O'Neil addressed this by using multiple market indicators beyond just the SMA, but BigClaw's automated implementation uses the SMA200 as the primary proxy.

2. **Quarterly EPS Data Quality.** `info['earningsQuarterlyGrowth']` is not universally available in yfinance. Implementation must handle missing data gracefully. Claude argued it works for 90%+ of the CANSLIM-relevant universe (mid/large cap US equities).

3. **Earnings Acceleration Detection is Hard.** O'Neil wants *accelerating* earnings (25% → 30% → 40%), not just positive growth. True acceleration requires multi-quarter sequential comparison, which is partially available via `quarterly_income_stmt`.

4. **Relative Strength Computation.** yfinance doesn't provide IBD-style RS Ratings. BigClaw computes a proxy from 3-month price return vs SPY. This is directionally correct but not identical to O'Neil's proprietary RS Rating.

---

## 2. Gate Rules (Hard Buy Filters)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| G1 | Quarterly EPS Growth | earningsQuarterlyGrowth >= 25% | `info['earningsQuarterlyGrowth']` or computed from `quarterly_income_stmt` | *HMMIS* 4th Ed., Ch. 1, p. 17: "minimum should be in the 25% to 50% range" | Unanimous (threshold settled R2) |
| G2 | Annual Earnings Growth | Positive annual EPS growth | `info['earningsGrowth']` | *HMMIS* 4th Ed., Ch. 2 | Unanimous |
| G3 | ROE Floor | returnOnEquity >= 17% | `info['returnOnEquity']` | *HMMIS* 4th Ed., Ch. 2, p. 41 | Unanimous |
| G4 | Near 52-Week High | Price within 15% of 52-week high | `info['fiftyTwoWeekHigh']`, `info['currentPrice']` | *HMMIS* 4th Ed., Ch. 3, p. 59 | Unanimous |
| G5 | Positive Relative Strength | 3-month return > SPY 3-month return | Computed from price history | *HMMIS* 4th Ed., Ch. 5: leaders outperform the market | Claude/Grok |
| G6 | Market Direction | S&P 500 above 200-day SMA | Computed from SPY `history()` | *HMMIS* 4th Ed., Ch. 9 [SMA200 as proxy for O'Neil's market direction signals] | Unanimous |
| G7 | Institutional Ownership | 20% <= heldPercentInstitutions <= 95% | `info['heldPercentInstitutions']` | *HMMIS* 4th Ed., Ch. 7: "look for at least a few institutional sponsors" but avoid over-owned | Claude/Grok |
| G8 | Positive Earnings | trailingEps > 0 | `info['trailingEps']` | *HMMIS* 4th Ed., Ch. 1-2: earnings are non-negotiable | Unanimous |
| G9 | Minimum Price | currentPrice >= $15 | `info['currentPrice']` | *HMMIS* 4th Ed., Ch. 12, p. 285: avoid cheap stocks | Claude/Grok |
| G10 | Market Cap Floor | marketCap >= $3B | `info['marketCap']` | Moderator override. | Moderator |
| G11 | Data Sufficiency | earningsQuarterlyGrowth, fiftyTwoWeekHigh not None/NaN | Multiple | Implementation requirement | Unanimous |

### Gate Calibration Notes

**G1 (Quarterly EPS >= 25%):** The most debated measurability question. GPT-5.4 argued it's [Not measurable]. Claude defended: it works for 90%+ of CANSLIM-relevant mid/large caps, and omitting the C criterion would gut the entire methodology. Claude/Grok prevail.

**G6 (Market Direction):** O'Neil's market direction analysis uses multiple signals (distribution days, follow-through days, market leadership). SMA200 is a simplified but effective proxy. All 4 models agreed on this implementation.

**G7 (Institutional Ownership 20-95%):** O'Neil wants "some but not too much" institutional sponsorship. Below 20% = not enough institutional validation. Above 95% = over-owned, limited upside. Claude/Grok set the range.

---

## 3. Reject Rules (Hard Sell Triggers)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| R1 | Stop-Loss | Price drops 7-8% below purchase price | Portfolio state + `info['currentPrice']` | *HMMIS* 4th Ed., Ch. 10, p. 229: "cut every single loss at 7% or 8%" | Unanimous |
| R2 | Two Consecutive EPS Declines | earningsQuarterlyGrowth < 0 for 2 quarters | `info['earningsQuarterlyGrowth']` + state | *HMMIS* 4th Ed., Ch. 10, p. 243 | Unanimous |
| R3 | Relative Strength Collapse | 3-month return trails SPY by >15% for 60+ days | Computed from price history | *HMMIS* 4th Ed., Ch. 5: leaders must lead | Claude/Grok |
| R4 | Share Dilution | sharesOutstanding increase > 10% YoY | `info['sharesOutstanding']` + state | *HMMIS* 4th Ed., Ch. 6: supply dilution | Claude/Grok |

### Reject Calibration Notes

**R1 (7-8% Stop-Loss):** This is O'Neil's most famous rule and the single most directly sourced threshold in any BigClaw portfolio. No ambiguity, no debate. Requires portfolio-level purchase price tracking (available in `portfolios.db`).

---

## 4. Audit Rules (Weekly Compliance Checks)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| A1 | Profit-Taking Target | Unrealized gain >= 20-25% | Portfolio state | *HMMIS* 4th Ed., Ch. 10, p. 237 | Unanimous |
| A2 | Market Direction Warning | SPY within 2% of SMA200 | Computed | Approaching M gate failure | Claude |
| A3 | Earnings Deceleration | Current quarterly growth < prior quarter | Computed from `quarterly_income_stmt` | Deceleration precedes decline | Claude/Gemini |
| A4 | Institutional Ownership Shift | heldPercentInstitutions declining >5% | `info['heldPercentInstitutions']` + state | Smart money exiting | Claude/Grok |
| A5 | Volume Dry-Up | averageVolume declining >30% from 50-day average | `info['averageVolume']` | *HMMIS*: volume confirms price action | Claude |
| A6 | RS Fading | 3-month return positive but declining vs prior month | Computed | Leader losing momentum | Claude/Grok |

---

## 5. Signal Weight Matrix

| Signal | Weight | Justification |
|--------|--------|---------------|
| **RelativeStrength** | **2.0** | The L criterion. Leaders must outperform. *HMMIS* Ch. 5. Unanimous. |
| **Earnings** | **2.0** | The C and A criteria. "Earnings, earnings, earnings." *HMMIS* Ch. 1-2. Unanimous. |
| **Revenue** | **1.5** | O'Neil: "Look for sales growth of at least 25%." *HMMIS* Ch. 1. Scoring signal, not gate. Claude. |
| **ROE** | **1.5** | Annual earnings quality. *HMMIS* Ch. 2. Unanimous high weight. |
| **GoldenCross** | **1.5** | Price crossing above SMA50/200 = breakout confirmation. O'Neil buys breakouts. Claude/Grok. |
| **SMA50/200** | **1.0** | Trend confirmation. O'Neil requires uptrend. |
| **RSI** | **1.0** | Momentum confirmation. O'Neil buys strong stocks. |
| **MACD** | **0.5** | Supporting momentum indicator. Minor. |
| **InsiderFlow** | **0.5** | Institutional sponsorship proxy. Minor. |
| **FCF** | **0.5** | Not O'Neil's focus but supports earnings quality. |
| **GrossMargin** | **0.5** | Business quality. Not O'Neil's primary concern. |
| **ShortInterest** | **0.5** | Short squeeze potential on momentum names. |
| **Debt** | **0.5** | Balance sheet. O'Neil: "lower debt is better." Minor weight. |
| **ExpertOverride** | **0.5** | Some human judgment useful. |
| **PE** | **0.0** | O'Neil explicitly dismisses P/E: "P/E ratios were not a relevant factor in stock selection." *HMMIS* Ch. 2. Unanimous. |
| **PEG** | **0.0** | Not O'Neil methodology. Unanimous. |
| **DividendYield** | **0.0** | O'Neil doesn't care about dividends. Unanimous. |
| **PayoutSafety** | **0.0** | Not applicable. |
| **BondYield** | **0.0** | O'Neil is bottom-up, not macro. |

### Weight Hierarchy — The CANSLIM Inversion
This is the mirror image of Value Picks:
1. **Tier 1 (2.0):** RelativeStrength, Earnings — momentum + fundamentals combined
2. **Tier 2 (1.5):** Revenue, ROE, GoldenCross — growth confirmation + breakout
3. **Tier 3 (0.5-1.0):** SMA, RSI, MACD, InsiderFlow, FCF, others — supporting signals
4. **Tier 4 (0.0):** PE, PEG, DividendYield, PayoutSafety, BondYield — explicitly rejected by O'Neil

---

## 6. Style Differentiation

| Other Portfolio | Key Differentiator |
|----------------|-------------------|
| **Value Picks** | Value buys cheap (P/E <= 25); Momentum buys expensive near highs. Value weights PE at 2.0; Momentum at 0.0. Complete opposites. |
| **Growth Value (Lynch)** | Lynch uses PEG (2.0 weight); Momentum uses PEG at 0.0. Lynch uses zero technicals; Momentum is technical-first. |
| **Income Dividends** | Income requires dividends (2.0 weight); Momentum doesn't care (0.0). |
| **Innovation Fund** | Both tolerate high valuations but Innovation is thematic; Momentum is sector-agnostic and requires near-highs. |
| **Nuclear/Defense** | Sector-constrained vs sector-agnostic. Thematic vs momentum. |

The **M gate (market direction)** is the single most powerful differentiator. When SPY drops below SMA200, this portfolio goes to cash while every other portfolio keeps operating.

---

## 7. Implementation Checklist

- [ ] Update `PORTFOLIO_STYLES.md` with these rules
- [ ] Implement SPY SMA200 market direction gate (G6)
- [ ] Implement 52-week high proximity check (G4)
- [ ] Implement relative strength vs SPY computation (G5, R3)
- [ ] Implement quarterly EPS growth from `quarterly_income_stmt` with fallback (G1)
- [ ] Implement 7-8% stop-loss using portfolio purchase price data (R1)
- [ ] Implement 20-25% profit-taking alert (A1)
- [ ] Update `style_compliance.py` gates, rejects, audits
- [ ] Update `decision_engine.py` signal weights — technicals at max
- [ ] Run compliance audit against current Momentum Growth holdings
- [ ] Deploy to Pi and test

---

*Tiebreaker: Claude/Grok prevails. CANSLIM is the most precisely documented methodology — O'Neil provides page numbers for nearly every threshold. The main debates were about yfinance measurability (quarterly EPS), not interpretation. Revenue growth kept as scoring signal (1.5) rather than hard gate per Claude. Market direction gate (SPY > SMA200) is unanimous and unique to this portfolio.*
