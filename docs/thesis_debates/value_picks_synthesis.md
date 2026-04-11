# Value Picks Portfolio — Investment Policy Statement

**Portfolio #1: Value Picks**
**Investment Style:** Quality Value Investing
**Modeled After:** Warren Buffett / Benjamin Graham (Graham-Buffett Synthesis)
**Document Version:** 1.0 — April 1, 2026
**Derived From:** Multi-model thesis debate (Claude Opus 4.6, Grok 4.20 Beta, Gemini 3.1 Pro, GPT-5.4)
**Approved By:** Curtis Biggs (Moderator)

---

## 1. Investment Thesis

### 1.1 Core Philosophy — The Graham-Buffett Synthesis

This portfolio operates at the intersection of two complementary investment philosophies: Benjamin Graham's margin of safety and quantitative discipline, and Warren Buffett's evolution toward "wonderful companies at fair prices."

Graham, the father of value investing, established the quantitative framework in *Security Analysis* (1934) and *The Intelligent Investor* (1949): buy below intrinsic value with a margin of safety, demand earnings stability, insist on balance sheet strength, and never speculate. His criteria are the most precisely documented quantitative rules in investment history.

Buffett, Graham's most successful student, evolved the framework:

> "It's far better to buy a wonderful company at a fair price than a fair company at a wonderful price."
> — Berkshire 1989 Letter

> "I evolved... Ben would have been proud of the evolution."
> — Warren Buffett, Berkshire 2014 Annual Meeting

The evolution means this portfolio is NOT a pure Graham defensive screen (which would exclude Apple, Coca-Cola, and virtually every Buffett holding). It is a synthesis: Graham's quantitative discipline provides the floor (margin of safety, earnings stability, P/E x P/B test), while Buffett's quality overlay provides the ceiling (ROE, gross margins, FCF generation, competitive moats).

### 1.2 What Each Investor Contributes

| Element | Graham's Contribution | Buffett's Evolution |
|---------|----------------------|---------------------|
| Valuation | P/E <= 15, P/E x P/B <= 22.5 | P/E <= 25 for quality compounders |
| Balance Sheet | Current ratio >= 2.0, LTD <= NCA | D/E <= 1.5 (practical, yfinance-reliable) |
| Earnings | Positive, stable (10-year history) | Stable + high ROE (>= 15%) |
| Quality | Not specified | Gross margin >= 30% (moat proxy) |
| Cash Flow | Not explicitly used | FCF > 0 (owner earnings concept) |
| Dividends | 20+ years continuous | Preferred but not required for all |
| Sell Discipline | Formulaic (P/E ceiling) | "Our favorite holding period is forever" — but BigClaw needs automated guardrails |
| Interest Rates | Not central | "Most important item in valuation" |

### 1.3 Risk Philosophy

**Margin of Safety is Non-Negotiable.** Every purchase must offer downside protection through valuation discipline. The P/E <= 25 gate and P/E x P/B <= 22.5 Graham combined test ensure BigClaw never overpays, even for quality.

**Quality is the Primary Risk Control.** High ROE (>= 15%), positive FCF, and strong gross margins (>= 30%) ensure BigClaw owns businesses that can self-fund through downturns. Buffett's insight: the best downside protection is owning a business so good it recovers.

**No Technical Signals.** Both Graham and Buffett explicitly rejected technical analysis. All five technical signals weighted at 0.0. Graham called chart reading "the most respected form of superstition" and Buffett famously ignores market movements.

### 1.4 Behavior Across Market Regimes

| Regime | Expected Behavior | Strategy |
|--------|-------------------|----------|
| Bull market | Moderate — quality compounders participate but P/E gate limits buying overvalued names | Hold winners, hard to find new entries at P/E <= 25 |
| Bear market / recession | Outperforms — quality companies with strong balance sheets decline less and recover faster | Best buying opportunity; margin of safety widens |
| Rising rates | Mixed — intrinsic values decline (higher discount rate), but quality business earnings may be resilient | BondYield signal at 1.0 adjusts scoring; tighter valuation required |
| Crisis (2008, 2020) | Painful short-term but fundamentals intact for quality holdings | Hold if earnings and FCF stable; Graham combined test prevents adding at bubble prices |
| Bubble / momentum market | Significantly underperforms — P/E gate blocks buying overvalued growth names | By design — this is the portfolio that refuses to chase |

### 1.5 Known Weaknesses

1. **P/E Gate Limits Universe.** At P/E <= 25, many quality companies are excluded during bull markets. This is intentional but means the portfolio may have difficulty deploying cash when markets are elevated.

2. **"Wonderful Company" Cannot Be Automated.** Buffett's moat assessment is qualitative. Gross margin >= 30% is the best available proxy but misses capital-light businesses with low margins but strong competitive positions.

3. **Graham's Balance Sheet Tests Are Unreliable in yfinance.** Current ratio >= 2.0 and LTD <= NCA are precisely documented Graham criteria but cannot be reliably computed from yfinance for universal screening. D/E <= 1.5 is the practical substitute.

4. **Slow Grower Bias.** The P/E ceiling naturally tilts toward mature, slower-growing companies. This is appropriate for a value portfolio but means missing high-quality compounders during their growth phase.

---

## 2. Gate Rules (Hard Buy Filters)

A candidate is **BLOCKED** if any gate fails.

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| G1 | Positive Earnings | trailingEps > 0 | `info['trailingEps']` | *Intelligent Investor*, Ch. 14 | Unanimous |
| G2 | Earnings Stability | Positive net income in all available annual periods (~4 years) | `stock.financials['Net Income']` | *Intelligent Investor*, Ch. 14 (proxy for 10-year rule) | Claude/Grok |
| G3 | ROE Floor | returnOnEquity >= 15% | `info['returnOnEquity']` | Berkshire 1979 Letter: "primary test of managerial economic performance." [Threshold estimated] | Claude/Grok/Gemini (GPT wanted audit only) |
| G4 | Positive FCF | freeCashflow > 0 | `info['freeCashflow']` | Berkshire 1986 Letter: owner earnings concept. [Threshold estimated] | Unanimous |
| G5 | P/E Ceiling | trailingPE <= 25 | `info['trailingPE']` | Berkshire 1989, 1992 Letters: "wonderful company at fair price." [Threshold estimated — accommodates Buffett quality approach] | Claude/Grok/Gemini (GPT wanted <= 15 per pure Graham) |
| G6 | Debt-to-Equity | debtToEquity <= 1.5 (non-financial, non-utility) | `info['debtToEquity']` / 100 | [Threshold estimated — calibrated to Buffett holdings: AAPL ~1.5, KO ~1.7] | Claude/Grok |
| G7 | Gross Margin | grossMargins >= 30% (exempt Energy, Financials, Utilities) | `info['grossMargins']` | Buffett 2011 FCIC testimony on pricing power. [Threshold estimated] | Claude/Grok/Gemini (GPT wanted audit only) |
| G8 | No Recent IPO | Public >= 3 years | `info['firstTradeDateEpochUtc']` or `len(history('5y')) > 750` | *Security Analysis*, Ch. 31; Berkshire 1993 Letter. [Threshold estimated] | Claude/Grok |
| G9 | Graham Combined Valuation | P/E x P/B <= 22.5 | `info['trailingPE']` x `info['priceToBook']` | *Intelligent Investor*, Ch. 14, criterion #7 | Unanimous |
| G10 | Market Cap Floor | marketCap >= $3B | `info['marketCap']` | [Moderator override — consistent with other portfolios] | Moderator |
| G11 | Data Sufficiency | trailingEps, trailingPE, returnOnEquity not None/NaN | Multiple | Implementation requirement | Unanimous |

### Gate Calibration Notes

**G5 (P/E <= 25):** The central debate was pure Graham (P/E <= 15) vs Buffett synthesis (P/E <= 25). GPT-5.4 maintained pure Graham with impeccable sourcing. But a P/E <= 15 gate would exclude every non-financial Buffett holding. Since BigClaw's portfolio is explicitly Buffett/Graham, the synthesis approach (Claude/Grok) prevails. The P/E x P/B <= 22.5 test (G9) provides the Graham anchor.

**G6 (D/E <= 1.5):** Graham specified current ratio >= 2.0 and LTD <= NCA. These are too restrictive (would exclude all Buffett holdings) and unreliable in yfinance. D/E is the most widely available leverage metric. 1.5 accommodates Apple (~1.5-1.8) and Coca-Cola (~1.5-1.8) while excluding highly leveraged companies.

**G7 (Gross Margin >= 30%):** The best available automated proxy for Buffett's moat requirement. Without it, the screen admits commodity producers and low-margin businesses Buffett explicitly avoids. Sector exemptions for Energy (CVX), Financials (BAC, AXP), and Utilities prevent false exclusions.

**G9 (P/E x P/B <= 22.5):** When P/B is unavailable or negative (from buybacks), this gate is skipped — the P/E <= 25 standalone gate still applies. This prevents penalizing companies for Buffett-endorsed buyback programs.

---

## 3. Reject Rules (Hard Sell Triggers)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| R1 | Negative Earnings | trailingEps < 0 | `info['trailingEps']` | *Intelligent Investor*, Ch. 14 | Unanimous |
| R2 | Extreme Overvaluation | trailingPE > 50 | `info['trailingPE']` | [Threshold estimated — automated guardrail. P/E 50 = 2% earnings yield = zero margin of safety.] | Claude/Grok (GPT/Gemini wanted removal) |
| R3 | Dividend Elimination | Dividend cut to $0 (if was a dividend payer) | `ticker.dividends` history | *Intelligent Investor*, Ch. 14: 20+ years continuous dividends. [Implementation requires historical tracking.] | Claude/Grok |
| R4 | Persistent Negative FCF | FCF < 0 for 2 consecutive annual periods | `stock.cashflow` | Berkshire 1986 Letter. [Threshold estimated — "2 years" not directly sourced.] | Unanimous |

### Reject Calibration Notes

**R2 (P/E > 50):** GPT-5.4 argued Buffett doesn't use formulaic sells. True — but BigClaw is an automated system, not Buffett. An algorithm without any valuation ceiling could hold through a bubble to P/E 100+. P/E 50 implies 2% earnings yield, which provides zero margin of safety in any normal rate environment.

---

## 4. Audit Rules (Weekly Compliance Checks)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| A1 | P/E Drift | trailingPE > 30 | `info['trailingPE']` | Margin of safety erosion warning | Unanimous |
| A2 | ROE Decline | returnOnEquity < 12% | `info['returnOnEquity']` | Below Buffett quality threshold | Claude |
| A3 | FCF Negative | freeCashflow < 0 | `info['freeCashflow']` | Cash generation concern | Unanimous |
| A4 | No Dividend | dividendYield == 0 | `info['dividendYield']` | Graham Ch. 14 dividend preference. Audit, not gate. | Claude (defended against Grok's removal) |
| A5 | Portfolio Avg Yield | Portfolio average yield < 1% | Portfolio calculation | Berkshire 13F analysis | Claude |
| A6 | Gross Margin Drop | grossMargins < 25% | `info['grossMargins']` | Moat deterioration warning | Claude |
| A7 | Debt Escalation | debtToEquity > 200 (non-fin, non-util) | `info['debtToEquity']` | Leverage warning | Claude |
| A8 | Earnings Decline | 2+ years declining EPS | `stock.financials` | *Intelligent Investor*, Ch. 14 | Claude |
| A9 | Graham Combined Drift | P/E x P/B > 22.5 | Computed | *Intelligent Investor*, Ch. 14 | Unanimous |
| A10 | Current Ratio Low | currentRatio < 1.5 (non-fin, non-util) | `info['currentRatio']` | *Intelligent Investor*, Ch. 14 [adjusted from 2.0 — audit, not gate] | Claude (defended as audit over GPT's gate) |

---

## 5. Signal Weight Matrix

| Signal | Weight | Justification |
|--------|--------|---------------|
| **Earnings** | **2.0** | Graham and Buffett both center on earnings power. Unanimous. |
| **ROE** | **2.0** | Berkshire 1979: "primary test of managerial economic performance." Unanimous. |
| **FCF** | **2.0** | Berkshire 1986 owner earnings. Cash generation is non-negotiable. Unanimous. |
| **PE** | **2.0** | Central valuation metric for both Graham and Buffett. Unanimous. |
| **GrossMargin** | **1.5** | Buffett's moat proxy — pricing power. Claude/Grok. |
| **Debt** | **1.5** | Graham's balance sheet emphasis. Claude/Grok. |
| **DividendYield** | **1.0** | Graham's dividend preference. Conceded from 1.5 in debate. |
| **PayoutSafety** | **1.0** | Dividend sustainability. |
| **BondYield** | **1.0** | Buffett: "most important item over time in valuation is obviously interest rates." Claude defended with multiple primary quotes. |
| **ExpertOverride** | **1.0** | Buffett's approach depends on qualitative moat assessment. Only channel for human judgment. Claude defended against Gemini's 0. |
| **Revenue** | **1.0** | Business health context. |
| **PEG** | **0.5** | Limited utility for value — more relevant for GARP. |
| **InsiderFlow** | **0.5** | Buffett occasionally notes insider activity. Minor. |
| **ShortInterest** | **0.0** | Neither Graham nor Buffett discussed short interest. |
| **RSI** | **0.0** | Both rejected technical analysis. Unanimous. |
| **MACD** | **0.0** | Both rejected technical analysis. Unanimous. |
| **SMA50/200** | **0.0** | Both rejected technical analysis. Unanimous. |
| **GoldenCross** | **0.0** | Both rejected technical analysis. Unanimous. |
| **RelativeStrength** | **0.0** | Both rejected technical analysis. Unanimous. |

### Weight Hierarchy
1. **Tier 1 (2.0):** Earnings, ROE, FCF, PE — the four pillars of Graham-Buffett value
2. **Tier 2 (1.5):** GrossMargin, Debt — quality and safety
3. **Tier 3 (1.0):** DividendYield, PayoutSafety, BondYield, ExpertOverride, Revenue — supporting signals
4. **Tier 4 (0.5):** PEG, InsiderFlow — minor
5. **Tier 5 (0.0):** All technicals, ShortInterest — explicitly rejected

---

## 6. Style Differentiation

| Other Portfolio | Key Differentiator |
|----------------|-------------------|
| **Growth Value (Lynch)** | Value demands P/E <= 25; Lynch allows P/E <= 40. Value demands ROE >= 15%; Lynch doesn't gate on ROE. Value uses Graham P/E x P/B test; Lynch uses PEG. |
| **Innovation Fund (Wood)** | Value demands positive earnings and FCF; Innovation tolerates pre-profit. Value caps P/E at 25; Innovation has no P/E ceiling. |
| **Income Dividends** | Value doesn't require dividends (audit only); Income requires yield >= 1.5%. Different emphasis. |
| **Momentum Growth (O'Neil)** | Value uses zero technical signals; Momentum is technical-first. Value buys cheap; Momentum buys at 52-week highs. |
| **Nuclear/Defense** | Value is sector-agnostic; Nuclear/Defense are sector-constrained. |

---

## 7. Documents and References

### Primary Sources
- **Graham, Benjamin.** *The Intelligent Investor* (1973 revised edition). Chapters 14, 15, 20.
- **Graham, Benjamin & Dodd, David.** *Security Analysis* (1934/1940). Chapters 31, 43.
- **Buffett, Warren.** Berkshire Hathaway Annual Letters: 1979 (ROE), 1986 (owner earnings), 1989 ("wonderful company at fair price"), 1992 (growth and value joined at hip), 2014 (evolution from Graham).
- **Buffett, Warren.** 2011 FCIC Testimony (pricing power / gross margins).
- **Buffett, Warren.** Various CNBC interviews and annual meeting transcripts (interest rates and valuation).

---

## 8. Implementation Checklist

- [ ] Update `PORTFOLIO_STYLES.md` with these rules
- [ ] Update `style_compliance.py` gate checks G1-G11
- [ ] Update `style_compliance.py` reject rules R1-R4
- [ ] Update `style_compliance.py` audit rules A1-A10
- [ ] Update `decision_engine.py` signal weights
- [ ] Add Graham P/E x P/B combined test (G9) with graceful P/B handling
- [ ] Add sector exemptions for G6 (D/E), G7 (gross margin), A10 (current ratio)
- [ ] Add earnings stability check from `stock.financials` (G2)
- [ ] Add IPO age check (G8) with fallback implementation
- [ ] Run compliance audit against current Value Picks holdings
- [ ] Deploy to Pi and test

---

*Tiebreaker: Claude/Grok agreement prevails. The central debate — pure Graham vs Graham-Buffett synthesis — was resolved in favor of synthesis (Claude/Grok/Gemini vs GPT-5.4). This means P/E <= 25 (not 15), D/E <= 1.5 (not current ratio >= 2.0), and ROE/gross margin as gates (not audit only). GPT-5.4's pure Graham framework was the most rigorously sourced but does not match BigClaw's stated Buffett/Graham methodology.*
