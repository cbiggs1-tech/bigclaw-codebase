# Growth Value Portfolio — Investment Policy Statement

**Portfolio #3: Growth Value**
**Investment Style:** Growth At a Reasonable Price (GARP)
**Modeled After:** Peter Lynch (Fidelity Magellan Fund, 1977-1990)
**Document Version:** 1.0 — April 1, 2026
**Derived From:** Multi-model thesis debate (Claude Opus 4.6, Grok 4.20 Beta, Gemini 3.1 Pro, GPT-5.4)
**Approved By:** Curtis Biggs (Moderator)

---

## 1. Investment Thesis

### 1.1 Core Philosophy

Peter Lynch managed the Fidelity Magellan Fund from 1977 to 1990, compounding at 29.2% annually and growing assets from $20 million to $14 billion — the best 13-year track record of any mutual fund in history. His methodology, documented in *One Up on Wall Street* (1989) and *Beating the Street* (1993), rejects the false dichotomy between "value" and "growth." Lynch argued that growth is simply a component of value, and the PEG ratio — Price/Earnings divided by Earnings Growth Rate — is the single best tool for determining whether you're paying a fair price for that growth.

In Lynch's own words:

> "The P/E ratio of any company that's fairly priced will equal its growth rate... A P/E ratio that's half the growth rate is very positive, and one that's twice the growth rate is very negative."
> — *One Up on Wall Street*, Ch. 10

> "Invest in what you know... The best stock ideas come from your own experience as a consumer."
> — *One Up on Wall Street*, Ch. 3

> "Strong balance sheet is the single most important factor in surviving downturns."
> — *One Up on Wall Street*, Ch. 11

> "Earnings, earnings, earnings. Whatever else you might hear about or think about, it's earnings that drive the stock price."
> — *One Up on Wall Street*, Ch. 10

The "invest in what you know" philosophy is frequently misunderstood as a license to buy familiar brands regardless of price. Lynch explicitly warned against this — familiarity is merely the *starting point* for rigorous fundamental research. The true engine of Lynch's methodology is the relationship between a company's earnings growth rate and its valuation multiple.

### 1.2 The Six Stock Categories

Lynch classified every stock into one of six categories, each with its own investment logic and sell discipline. BigClaw's Growth Value portfolio targets **Stalwarts** and **Fast Growers** — the two categories where Lynch made the majority of his returns at Magellan.

| Category | EPS Growth | Lynch's Approach | BigClaw Applicability |
|----------|-----------|-----------------|----------------------|
| Slow Growers | < 10% | Avoid — buy only for dividends | Excluded by gate (growth < 10%) |
| **Stalwarts** | **10-20%** | **Core holdings — rotate at 30-50% gain** | **Primary target** |
| **Fast Growers** | **20-50%** | **Hold for 10-baggers if story intact** | **Primary target** |
| Cyclicals | Variable | Timing-dependent, industry knowledge needed | Excluded (requires qualitative judgment) |
| Turnarounds | Negative→Positive | Special situation, not core strategy | Excluded (requires negative-to-positive EPS detection) |
| Asset Plays | N/A | Hidden assets undervalued by market | Excluded (requires qualitative asset valuation) |

**Source:** *One Up on Wall Street*, Ch. 8

### 1.3 Market Conditions This Style Exploits

Lynch's GARP approach exploits the persistent tendency of the market to overprice "story" stocks and underprice "boring" companies with steady, understandable earnings growth. It works best when:

- Interest rates are moderate to falling (easier to justify paying up for growth)
- Market has a broad range of P/E multiples (not compressed into narrow band)
- Earnings growth is differentiating — some companies growing, others not

Lynch was famously agnostic to macroeconomics:

> "If you spend 13 minutes a year on economics, you've wasted 10 minutes."
> — *Beating the Street*, Ch. 1

This philosophy is reflected in BigClaw's signal weights: all macro indicators (BondYield) and technical signals (RSI, MACD, SMA, GoldenCross, RelativeStrength) are weighted at **0.0** for this portfolio.

### 1.4 Risk Philosophy

Lynch's risk management was fundamentals-based, not technical:

- **Balance sheet is the primary risk control.** Low debt means a company survives recessions where highly leveraged competitors fail. "I'll take the company with the low debt and the high cash every time." (*OUOWS*, Ch. 11)
- **PEG discipline prevents overpaying.** A company growing at 20% with a P/E of 20 (PEG = 1.0) has a margin of safety that a company growing at 20% with a P/E of 50 (PEG = 2.5) does not.
- **Diversification over stop-losses.** Lynch held 1,000+ positions at Magellan's peak. His risk philosophy was that "if you're good, you're right six times out of ten" — wide diversification lets the winners overwhelm the losers without needing to time exits perfectly.
- **No technical hedging.** No stop-losses, no options overlays, no market-timing exits. If the fundamentals are intact, hold through drawdowns.

### 1.5 Behavior Across Market Regimes

| Regime | Expected Behavior | Lynch's Approach |
|--------|-------------------|-----------------|
| Bull market, moderate rates | **Excellent** — core regime, earnings growth drives returns | Hold, let winners run |
| Bear market / recession | Suffers but recovers faster than high-PEG growth due to balance sheet strength | Review fundamentals, don't panic-sell |
| High-interest-rate environment | Challenged — growth multiple compression | PEG discipline limits damage; avoid high-debt names |
| Crisis (2008, 2020) | Painful but strong balance sheet + PEG < 1.0 provides margin of safety | Hold if story intact, buy more at lower PEG |
| Sideways / value-led | Lags pure value but positive if earnings growth materializes | Patience — "big winners need time to compound" |
| Late-stage momentum bubble | Underperforms momentum (won't chase PEG > 2.0) | This is by design — avoiding blow-up risk |

### 1.6 Known Weaknesses and Blind Spots

1. **Value Traps via PEG Distortion:** PEG uses historical or consensus growth estimates. If growth suddenly decelerates, the PEG that looked cheap yesterday becomes expensive today. The earnings deceleration audit rule mitigates this but cannot prevent it entirely.

2. **Macro Blindness:** Ignoring macroeconomics means this portfolio can suffer severe drawdowns during systemic liquidity crises (2008, 2020) when all P/E multiples compress regardless of individual company fundamentals.

3. **Capital Intensity Blindness:** The PEG ratio ignores the capital required to generate growth. A company growing at 20% that requires massive CapEx is less valuable than one doing it with high Free Cash Flow. The FCF gate partially addresses this.

4. **Cyclical Contamination:** A cyclical company at peak earnings can appear to have great growth and a low PEG, exactly when it's most dangerous. Lynch addressed this by separating cyclicals into their own category, but automated PEG screening cannot reliably distinguish cyclicals from genuine growers.

5. **"Invest in What You Know" Cannot Be Automated:** The qualitative edge of Lynch's approach — recognizing great products and businesses from everyday experience — is lost in a purely quantitative implementation.

6. **Inventory Data Quality:** Lynch's inventory-versus-revenue check is one of his most powerful audits, but quarterly inventory data from yfinance is often inconsistent or missing. Implementation must handle graceful failure.

---

## 2. Gate Rules (Hard Buy Filters)

A candidate is **BLOCKED** if any gate fails. These are non-negotiable entry requirements.

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| G1 | Positive Earnings | trailingEps > 0 | `info['trailingEps']` | *OUOWS*, Ch. 10 | Unanimous |
| G2 | PEG Below Fair Value | PEG < 1.0 | `info['pegRatio']` | *OUOWS*, Ch. 10: "fairly priced will equal its growth rate" | Claude/Grok (moderator tiebreak over Gemini/GPT at 1.5) |
| G3 | P/E Operating Range | 5 <= P/E <= 40 | `info['trailingPE']` | *OUOWS*, Ch. 10: "P/E of 40 is dangerous"; lower bound practical filter | Unanimous |
| G4 | EPS Growth Sweet Spot | 10% <= earningsGrowth <= 50% | `info['earningsGrowth']` | *OUOWS*, Ch. 8 (Stalwarts 10-20%, Fast Growers 20-50%) | Unanimous |
| G5 | Balance Sheet Strength | D/E < 0.80 | `info['debtToEquity']` / 100 | *OUOWS*, Ch. 11 (normal = 0.33, 0.80 = permissive ceiling). Financials exempt via `info['sector']`. | Claude/Grok |
| G6 | Positive Free Cash Flow | FCF > 0 | `info['freeCashflow']` | *OUOWS*, Ch. 11 (cash position emphasis). [Consistent with Lynch's approach; not exact terminology] | Claude/Grok (Gemini/GPT wanted scoring only) |
| G7 | Data Sufficiency | PEG, trailingEps, earningsGrowth not None/NaN | Multiple | Implementation requirement — prevents false positives from missing data | Unanimous |

### Gate Calibration Notes

**G2 (PEG < 1.0):** Lynch defined PEG = 1.0 as "fairly priced" — paying exactly one times earnings growth. PEG < 1.0 means getting growth at a discount. Gemini and GPT argued for 1.5 as more practical, but Lynch's own words anchor fair value at 1.0. The scoring engine at weight 2.0 will still strongly prefer PEG < 0.5 ("very positive" per Lynch) while the gate at 1.0 maintains discipline.

**G5 (D/E < 0.80):** Lynch stated a "normal" balance sheet is 75% equity / 25% debt (D/E = 0.33). For fast growers he preferred even lower. The 0.80 gate is already permissive — it's 2.4x Lynch's stated normal. Claude and Grok argued this was the right balance between Lynch's preference and practical market coverage. Note: `info['debtToEquity']` in yfinance is often reported as a percentage (e.g., 80 = 80%), so divide by 100 before comparing.

**G6 (FCF > 0):** Lynch didn't use the modern term "free cash flow" but his two-minute drill (*OUOWS*, Ch. 11) explicitly includes checking the cash position and whether the company is generating or consuming cash. A company with negative FCF is consuming cash — exactly what Lynch checked for.

---

## 3. Reject Rules (Hard Sell Triggers)

A holding **MUST be sold** if any reject rule triggers. These are non-negotiable exit requirements.

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| R1 | PEG Extreme | PEG > 2.0 | `info['pegRatio']` | *OUOWS*, Ch. 10: "P/E ratio twice the growth rate is very negative" | Unanimous — directly sourced |
| R2 | P/E Extreme | P/E > 40 | `info['trailingPE']` | *OUOWS*, Ch. 10 | Unanimous |
| R3 | Earnings Negative | trailingEps <= 0 | `info['trailingEps']` | *OUOWS*, Ch. 10, 17 | Unanimous |
| R4 | Fast Grower Stalls | earningsGrowth < 0 for stocks purchased at >20% growth | `info['earningsGrowth']` | *OUOWS*, Ch. 17: "If the fundamentals change, sell." | Unanimous |
| R5 | Stalwart Stalls | EPS Growth < 5% sustained | `info['earningsQuarterlyGrowth']` | *OUOWS*, Ch. 8, 17 | Claude/Grok |
| R6 | Debt Spike | D/E > 1.5 | `info['debtToEquity']` / 100 | [Extrapolated — 4.5x Lynch's normal of 0.33. Strong anti-debt language supports upper bound.] | Claude maintains |
| R7 | Unsustainable Growth | EPS Growth > 50% | `info['earningsGrowth']` | *OUOWS*, Ch. 8: "I've never seen one that could sustain it." Hard reject. | Claude/Grok (Grok: immediate reject, Claude: escalation — moderator sides with Grok) |

### Reject Calibration Notes

**R1 (PEG > 2.0):** This is Lynch's most quoted sell signal. PEG = 2.0 means you're paying twice the growth rate — Lynch called this "very negative." No ambiguity, no debate.

**R6 (D/E > 1.5):** Lynch never stated "sell at D/E 1.5" in those exact words, but D/E = 1.5 means 50% more debt than equity — 4.5 times Lynch's stated "normal." Without some upper bound reject, a company could pass all other gates while carrying extreme leverage. Marked as [Threshold extrapolated].

**R7 (Growth > 50%):** Lynch's warning was clear and emphatic: "Beware the company that's growing at 50 to 100 percent a year... I've never seen one that could sustain it." Moderator rules this as a hard reject rather than an escalating audit because Lynch's language leaves no room for ongoing tolerance.

---

## 4. Audit Rules (Weekly Compliance Checks)

Audit rules generate **warnings** for human review, not automatic sells. Persistent audit failures may escalate to compliance watchlist per BigClaw's cross-portfolio move policy.

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| A1 | PEG Above Fair Value | PEG > 1.0 | `info['pegRatio']` | *OUOWS*, Ch. 10 (1.0 = fair value) | Adopted from Gemini, Claude concurred |
| A2 | PEG Drift Toward Danger | PEG > 1.5 | `info['pegRatio']` | *OUOWS*, Ch. 10 | Unanimous |
| A3 | EPS Growth Deceleration | earningsGrowth < 10% | `info['earningsGrowth']` | *OUOWS*, Ch. 8 (below Stalwart threshold) | Unanimous |
| A4 | D/E Elevated | D/E > 0.80 | `info['debtToEquity']` / 100 | *OUOWS*, Ch. 11 | Unanimous |
| A5 | Institutional Crowding | heldPercentInstitutions > 80% | `info['heldPercentInstitutions']` | *OUOWS*, Ch. 8: positive trait to have low inst. ownership, not a hard filter. Audit only. | Claude/Grok (Gemini wanted as gate, overruled) |
| A6 | Stalwart Gain Target | Unrealized gain > 30% AND earningsGrowth < 20% | Portfolio state + `info['earningsGrowth']` | *OUOWS*, Ch. 8: "30-50% gain, then sell" for stalwarts. Requires portfolio state tracking. | Unanimous |
| A7 | Revenue/Earnings Divergence | Revenue growth sign != Earnings growth sign | `info['revenueGrowth']`, `info['earningsGrowth']` | Consistent with Lynch's earnings quality emphasis (*OUOWS*, Ch. 10-11) | Adopted from GPT-5.4 |
| A8 | Inventory vs Revenue | Inventory growth > Revenue growth | `balance_sheet['Inventory']` + `financials['Total Revenue']` | *OUOWS*, Ch. 11: "If inventories are growing faster than sales, it's a red flag." [Not fully measurable — annual approximation only] | Unanimous concept |

### Audit Architecture

The audit rules form a layered early-warning system:
- **A1 (PEG > 1.0)** catches stocks drifting above fair value before they reach danger
- **A2 (PEG > 1.5)** is the serious warning — approaching the old gate level
- **R1 (PEG > 2.0)** is the hard sell — beyond this, the position must be exited

This creates a coherent PEG spectrum matching Lynch's own framework: PEG < 0.5 (very attractive) → 1.0 (fair) → 1.5 (getting expensive) → 2.0 (very negative — sell).

---

## 5. Signal Weight Matrix

BigClaw scores stocks on 20 dimensions. Each dimension is weighted 0.0 to 2.0 for this portfolio style.

| Signal | Weight | Justification |
|--------|--------|---------------|
| **PEG** | **2.0** | Central metric. Lynch's core innovation. Unanimous across all 4 analysts. *OUOWS*, Ch. 10 |
| **Earnings** | **2.0** | "Earnings, earnings, earnings." The driver of all stock prices per Lynch. Unanimous. *OUOWS*, Ch. 10 |
| **PE** | **1.5** | Important but already embedded in PEG (PEG = PE/Growth). Weight at 1.5 avoids double-counting while preserving valuation context. Claude/Gemini agreed. |
| **Debt** | **1.5** | "Single most important factor" for surviving downturns. Unanimous high weight; Claude conceded from 1.75 to consensus 1.5. *OUOWS*, Ch. 11 |
| **Revenue** | **1.0** | Earnings quality context — revenue growth validates earnings growth. Unanimous. |
| **FCF** | **1.0** | Cash generation emphasis consistent with Lynch's two-minute drill. Claude/Grok. |
| **ROE** | **1.0** | Business quality indicator. Lynch discussed return on equity occasionally. Gemini proposed. |
| **GrossMargin** | **1.0** | Business quality and competitive advantage indicator. Claude proposed. |
| **InsiderFlow** | **1.0** | "Insiders buy for only one reason: they think the price will go up." Claude/Gemini at 1.0 over Grok's 0.6 and GPT's 0.25. *OUOWS*, Ch. 9 |
| **DividendYield** | **0.5** | PEGY ratio for stalwarts: PEGY = P/E / (Growth% + Yield%). Minor factor for growth portfolio. |
| **PayoutSafety** | **0.5** | Dividend sustainability check for stalwarts. Minor factor. |
| **ShortInterest** | **0.0** | Lynch didn't discuss short interest. Unanimous. |
| **ExpertOverride** | **0.0** | Lynch disdained Wall Street consensus. All 4 analysts conceded to 0.0. |
| **BondYield** | **0.0** | Macro indicator — Lynch explicitly rejected macro analysis. Unanimous. |
| **RSI** | **0.0** | "Charts are great for predicting the past." Lynch explicitly mocked technical analysis. Unanimous. *OUOWS*, Ch. 1 |
| **MACD** | **0.0** | Lynch rejected all technical indicators. Unanimous. |
| **SMA50/200** | **0.0** | Lynch rejected moving averages. Unanimous. (GPT dissented at 0.25, overruled — no Lynch source) |
| **GoldenCross** | **0.0** | Lynch rejected chart patterns. Unanimous. |
| **RelativeStrength** | **0.0** | Lynch rejected relative strength analysis. Unanimous. (GPT dissented at 0.25, overruled) |

### Weight Hierarchy
The weights establish a clear priority order matching Lynch's documented emphasis:
1. **Tier 1 (2.0):** PEG, Earnings — the two metrics Lynch discussed most
2. **Tier 2 (1.5):** PE, Debt — valuation discipline and balance sheet safety
3. **Tier 3 (1.0):** Revenue, FCF, ROE, GrossMargin, InsiderFlow — supporting fundamentals
4. **Tier 4 (0.5):** DividendYield, PayoutSafety — minor for growth portfolio
5. **Tier 5 (0.0):** All technicals, macro, Wall Street consensus — explicitly rejected by Lynch

---

## 6. yFinance Field Map

| Field | Accessor | Usage | Reliability |
|-------|---------|-------|-------------|
| Trailing EPS | `info['trailingEps']` | G1, R3 | High |
| PEG Ratio | `info['pegRatio']` | G2, R1, A1, A2 | Moderate — can be None for some tickers |
| Trailing P/E | `info['trailingPE']` | G3, R2 | High |
| Earnings Growth | `info['earningsGrowth']` | G4, R4, R5, R7, A3, A7 | Moderate — trailing estimate, can be noisy |
| Debt to Equity | `info['debtToEquity']` | G5, R6, A4 | High — divide by 100 (reported as %) |
| Free Cash Flow | `info['freeCashflow']` | G6 | High |
| Held % Institutions | `info['heldPercentInstitutions']` | A5 | High — static snapshot |
| Held % Insiders | `info['heldPercentInsiders']` | InsiderFlow signal | High — static snapshot, not transaction data |
| Revenue Growth | `info['revenueGrowth']` | A7 | Moderate |
| Dividend Yield | `info['dividendYield']` | DividendYield signal, PEGY | High |
| Return on Equity | `info['returnOnEquity']` | ROE signal | High |
| Gross Margins | `info['grossMargins']` | GrossMargin signal | High |
| Sector | `info['sector']` | D/E financial exemption | High |
| Market Cap | `info['marketCap']` | Practical filter | High |
| Average Volume | `info['averageVolume']` | Practical filter | High |
| Current Price | `info['currentPrice']` | A6 stalwart gain calc | High |
| Inventory | `balance_sheet['Inventory']` | A8 | Low — inconsistent coverage |
| Total Revenue | `financials['Total Revenue']` | A8 | Moderate — annual only |

---

## 7. Style Differentiation

### How This Portfolio Avoids Convergence with the Other Six

| Other Portfolio | Key Differentiator |
|----------------|-------------------|
| **Value Picks (Buffett/Graham)** | Growth Value requires 10-50% EPS growth; Value Picks buys slow/no-growth at deep discounts. Growth Value pays up to P/E 40; Value Picks wants P/E < 25. |
| **Innovation Fund (Cathie Wood)** | Growth Value demands PEG < 1.0 and positive earnings; Innovation Fund tolerates negative earnings and infinite PEG for disruptive potential. |
| **Income Dividends** | Growth Value doesn't require dividends; Income requires yield >= 1.5%. Different universes. |
| **Momentum Growth (O'Neil)** | Growth Value uses zero technical signals; Momentum requires price near 52-week high, positive relative strength, and market direction gate. Fundamentally different methodologies. |
| **Nuclear Renaissance** | Sector-constrained (nuclear only); Growth Value is sector-agnostic. |
| **AI Defense & Autonomous** | Sector-constrained (defense only); Growth Value is sector-agnostic. |

The PEG ratio is the single differentiating metric. No other BigClaw portfolio centers on PEG as its primary gate and highest-weighted signal.

---

## 8. Data Gaps and Limitations

| Item | Measurability | Workaround |
|------|-------------|-----------|
| Inventory growth vs revenue growth (quarterly) | [Not measurable via yfinance] for quarterly delta | Annual approximation from `balance_sheet` + `financials` with graceful failure |
| Insider buying clusters (Form 4 transactions) | [Not fully measurable via yfinance] — static snapshot only | Use `heldPercentInsiders` as proxy; consider adding OpenInsider skill to BigClaw |
| Stalwart gain target tracking | Requires portfolio-level purchase price data | Already available in BigClaw's `portfolios.db` — implement as portfolio-level audit |
| 5-year EPS CAGR | [Not directly available] from yfinance as single field | Compute from `ticker.financials` (4 years typical coverage) |
| Lynch's stock category classification (Stalwart vs Fast Grower) | Requires EPS growth bucketing + judgment | Automate via earningsGrowth: 10-20% = Stalwart, 20-50% = Fast Grower |
| "Invest in what you know" qualitative edge | [Not measurable] | Cannot be automated — remains human judgment layer |
| Cyclical vs genuine grower distinction | [Not measurable] without multi-year EPS pattern analysis | Partial: flag if earningsGrowth swings > 30% between periods |

---

## 9. Documents and References

### Primary Sources (Used in This Thesis)
- **Lynch, Peter.** *One Up on Wall Street* (1989, Simon & Schuster). Chapters 1, 3, 8, 9, 10, 11, 17.
- **Lynch, Peter.** *Beating the Street* (1993, Simon & Schuster). Chapters 1, 5-7.
- **AAII Peter Lynch Screen** — codified Lynch's published criteria into a systematic screen that Lynch reviewed and endorsed.
- **Validea Peter Lynch Model** — systematic implementation reference for automated Lynch scoring.

### Recommended Additional Sources
- **Lynch, Peter.** *Learn to Earn* (1995). Educational context for Lynch's investment philosophy.
- [Requires access: "Peter Lynch: A Biography" by Steven W. Sears (out of print, ~$75-150 used)]
- [Requires access: Full archived Fidelity Magellan shareholder reports 1977-1990 (library or subscription)]
- [Requires access: Detailed quarterly 13F holdings from Magellan 1977-1990 for backtesting exact PEG thresholds]

---

## 10. Implementation Checklist

- [ ] Update `PORTFOLIO_STYLES.md` with these rules
- [ ] Update `style_compliance.py` gate checks to match G1-G7
- [ ] Update `style_compliance.py` reject rules to match R1-R7
- [ ] Update `style_compliance.py` audit rules to match A1-A8
- [ ] Update `decision_engine.py` signal weights to match weight matrix
- [ ] Update `autonomous_trader.py` scoring for Growth Value portfolio
- [ ] Add D/E division by 100 handler (yfinance reports as percentage)
- [ ] Add financial sector exemption for D/E gate
- [ ] Add data sufficiency gate (G7) — block if PEG/EPS/growth are None
- [ ] Add stalwart gain target tracking using portfolio state from `portfolios.db`
- [ ] Run compliance audit against current Growth Value holdings with new rules
- [ ] Update website sources.html with thesis reference
- [ ] Update DBD Section 5 portfolio definitions
- [ ] Deploy to Pi and test with next trading cycle

---

*This document was developed through a structured multi-model AI debate. Four frontier AI models independently researched Peter Lynch's published methodology, then cross-examined each other's proposals through three rounds of structured debate. The moderator (Curtis Biggs, assisted by Claude Opus 4.6) synthesized the consensus, applying a tiebreaker rule: when Claude and Grok agreed but Gemini and GPT dissented, Claude/Grok prevailed. All thresholds are grounded in Lynch's published works with source citations. Thresholds marked [Threshold extrapolated] are derived from Lynch's principles but not his exact words.*
