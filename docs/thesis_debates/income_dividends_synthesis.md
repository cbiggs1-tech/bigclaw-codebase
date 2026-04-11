# Income Dividends Portfolio — Investment Policy Statement

**Portfolio #4: Income Dividends**
**Investment Style:** Income / Dividend Growth Investing (DGI)
**Modeled After:** Dividend Aristocrats / David Fish CCC Methodology
**Document Version:** 1.0 — April 1, 2026
**Derived From:** Multi-model thesis debate (Claude Opus 4.6, Grok 4.20 Beta, Gemini 3.1 Pro, GPT-5.4)
**Approved By:** Curtis Biggs (Moderator)

---

## 1. Investment Thesis

### 1.1 Core Philosophy

This portfolio generates reliable, growing income through dividend-paying companies with long track records of consecutive dividend increases. The approach is modeled after the S&P 500 Dividend Aristocrats methodology (25+ years of consecutive increases) but adapted for practical implementation: BigClaw uses a 10-year minimum streak as the gate, applies quality overlays (payout ratio, FCF, Chowder Rule), and includes yield trap defenses that the raw Aristocrats index does not.

The intellectual foundation rests on three proven principles:

1. **Dividend growth signals business quality.** A company that has increased its dividend for 10+ consecutive years has demonstrated the earnings consistency, management discipline, and competitive moat required to sustain payouts through recessions.

2. **Compounding income is the primary return driver.** Capital appreciation is welcome but secondary. The goal is a growing income stream that compounds over time through reinvestment and organic dividend growth.

3. **Yield traps are the primary risk.** A high yield can signal distress, not generosity. Payout ratio, FCF coverage, and the Chowder Rule (yield + growth rate) separate sustainable dividends from traps about to be cut.

### 1.2 Key Sources

- **S&P Dow Jones Indices**: *S&P 500 Dividend Aristocrats Index Methodology* — defines the 25-year consecutive increase standard
- **David Fish**: *CCC List* (Champions/Contenders/Challengers) — the most comprehensive dividend streak database, distinguishing 25+, 10-24, and 5-9 year streaks
- **Lowell Miller**: *The Single Best Investment* (2006) — intellectual foundation for dividend growth investing
- **Charles Carlson**: *The Little Book of Big Dividends* — Chowder Rule and practical DGI methodology

### 1.3 Why Not Pure Index Replication

GPT-5.4 argued for strict Aristocrats replication (25-year streak, S&P 500 membership). This was overruled (3-to-1) because:
- 4 of GPT's 7 proposed gates are [Not measurable via yfinance] (S&P 500 membership, float-adjusted market cap, official liquidity, reconstitution schedule)
- BigClaw's portfolio is named "Income Dividends (Dividend Aristocrats / DGI)" — the slash and "DGI" indicate a hybrid
- Even institutional Aristocrats investors apply supplementary quality screens
- Pure index replication is not portfolio management — it's ETF behavior

### 1.4 Risk Philosophy

**Dividend Cut is the Cardinal Sin.** A dividend cut or elimination triggers immediate sell — no exceptions. This is the single hardest rule in the portfolio. Source: S&P methodology removes any company that fails to increase.

**Payout Ratio is the Early Warning System.** A company paying out >80% of earnings or >90% of FCF is stretching. It may sustain the dividend temporarily but is one bad quarter away from a cut.

**The Chowder Rule Prevents Yield Traps.** Yield + 5-year dividend growth rate must exceed a threshold (12% for normal stocks, 8% for utilities). A 6% yield with 0% growth is a trap waiting to spring. A 2% yield with 12% growth is a compounder.

### 1.5 Behavior Across Market Regimes

| Regime | Expected Behavior | Strategy |
|--------|-------------------|----------|
| Bull market | Lags growth — dividend stocks rarely lead rallies | Steady compounding; reinvest dividends |
| Bear market / recession | Outperforms — dividend payers decline less and recover with income floor | Best regime for this portfolio; quality dividends provide real returns |
| Rising rates | Challenged — bond yields compete with dividend yields; prices compress | Chowder Rule defends: high-growth dividend stocks less rate-sensitive than pure yield |
| Falling rates | Excellent — yield becomes scarce; dividend stocks re-rate upward | Tailwind for income portfolio |
| Inflation | Mixed — companies with pricing power can grow dividends through inflation | Gross margin and FCF gates select for pricing power |

### 1.6 Known Weaknesses

1. **Backward-Looking Streak Requirement.** A company with 10 years of increases may cut tomorrow. The streak tells you about the past, not the future. Payout ratio and FCF coverage partially mitigate this.

2. **Sector Concentration.** Dividend Aristocrats cluster in consumer staples, utilities, healthcare, and industrials. Technology and growth sectors are underrepresented. This is by design but limits diversification.

3. **Yield Trap Detection is Imperfect.** Even with Chowder Rule and payout ratio checks, a sudden earnings collapse can turn a healthy dividend into an unsustainable one before the audit catches it.

4. **yFinance Dividend History Limitations.** `Ticker.dividends` provides payment history but can have gaps, stock split adjustments, and inconsistent date coverage. Computing exact consecutive increase streaks requires careful implementation.

---

## 2. Gate Rules (Hard Buy Filters)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| G1 | Current Dividend Payer | dividendYield > 0 and dividendRate > 0 | `info['dividendYield']`, `info['dividendRate']` | S&P Aristocrats methodology; DGI fundamental requirement | Unanimous |
| G2 | Minimum Yield | dividendYield >= 1.5% | `info['dividendYield']` | [Threshold estimated — practical income floor. Below 1.5% is growth masquerading as income.] | Claude/Grok |
| G3 | Consecutive Dividend Increases | >= 10 years of consecutive annual increases | `Ticker.dividends` (computed) | David Fish CCC: Contender level (10-24 years). Claude maintained 10 over Grok/Gemini's 5 and GPT's 25. | Claude (moderator tiebreak) |
| G4 | Positive Earnings | trailingEps > 0 | `info['trailingEps']` | Earnings fund dividends. Unanimous. | Unanimous |
| G5 | Positive FCF | freeCashflow > 0 | `info['freeCashflow']` | Lowell Miller, *The Single Best Investment*; FCF funds sustainable dividends | Claude/Grok/Gemini |
| G6 | Payout Ratio Sustainable | payoutRatio <= 75% (non-REIT, non-utility) | `info['payoutRatio']` | [Threshold estimated — 75% leaves 25% margin for earnings dips without forcing a cut.] Utilities/REITs exempt. | Claude/Grok |
| G7 | Common Equity | quoteType == 'EQUITY' | `info['quoteType']` | S&P methodology; excludes MLPs, ETFs, preferreds | Unanimous |
| G8 | Market Cap Floor | marketCap >= $3B | `info['marketCap']` | Moderator override. Consistent across portfolios. | Moderator |
| G9 | Data Sufficiency | dividendYield, trailingEps, payoutRatio not None/NaN | Multiple | Implementation requirement | Unanimous |

### Gate Calibration Notes

**G2 (Yield >= 1.5%):** This is the defining gate that separates Income from other portfolios. A stock yielding 0.5% with great dividend growth belongs in Growth Value, not Income. The 1.5% floor ensures every holding contributes meaningful current income. Utilities typically yield 3-4%, consumer staples 2-3%.

**G3 (10-Year Streak):** The central debate. GPT wanted 25 years (pure Aristocrat). Grok/Gemini wanted 5 years (Challenger level). Claude argued 10 years — long enough to prove the company survived at least one full economic cycle (2008 GFC), short enough to include strong dividend growers that haven't yet reached Aristocrat status. Moderator agrees with Claude's 10-year minimum.

**G6 (Payout <= 75%):** Higher payout ratios mean less cushion. A company paying 90% of earnings is one bad quarter from a cut. Utilities and REITs are exempt because they operate under regulatory frameworks that support high payout ratios.

---

## 3. Reject Rules (Hard Sell Triggers)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| R1 | Dividend Cut or Elimination | Any reduction in per-share dividend | `Ticker.dividends` (computed) | S&P Aristocrats methodology: removed upon failure to increase. Non-negotiable. | Unanimous |
| R2 | Dividend Freeze | No increase for 2 consecutive years | `Ticker.dividends` (computed) | S&P methodology requires annual increases. Two-year freeze = pattern broken. | Unanimous |
| R3 | Negative Earnings Sustained | trailingEps < 0 for 2 consecutive periods | `info['trailingEps']` + state | Earnings fund dividends. Sustained losses = cut is likely. | Claude/Grok |
| R4 | Payout Ratio Extreme | payoutRatio > 100% sustained | `info['payoutRatio']` | Paying more than you earn is unsustainable. [Threshold estimated — 100% is mathematical limit.] | Unanimous |

---

## 4. Audit Rules (Weekly Compliance Checks)

| # | Rule | Threshold | yfinance Field | Source | Confidence |
|---|------|-----------|---------------|--------|------------|
| A1 | Payout Ratio Elevated | payoutRatio > 60% (non-utility, non-REIT) | `info['payoutRatio']` | Early warning before 75% gate would block re-entry | Claude |
| A2 | FCF Negative | freeCashflow < 0 | `info['freeCashflow']` | Cash not covering dividend | Unanimous |
| A3 | Yield Spike | dividendYield > 6% | `info['dividendYield']` | May signal price collapse (yield trap). [Threshold estimated.] | Claude/Grok |
| A4 | Chowder Rule Fail | Yield + 5yr DGR < 12% (or < 8% for utilities) | `info['dividendYield']` + computed growth | Charles Carlson methodology. Screens for yield traps. | Claude/Grok |
| A5 | Earnings Declining | earningsGrowth < 0 | `info['earningsGrowth']` | Earnings fund dividends | Unanimous |
| A6 | Dividend Streak Pacing | Current year approaching annual increase date with no increase | `Ticker.dividends` | Proactive — catch freeze before it becomes R2 | Claude/GPT |
| A7 | Portfolio Yield | Average portfolio yield < 2.5% | Portfolio calculation | Income portfolio should maintain meaningful aggregate yield | Claude |
| A8 | Debt Elevated | debtToEquity > 200 (non-financial) | `info['debtToEquity']` | Leverage risk to dividend sustainability | Claude/Grok |

---

## 5. Signal Weight Matrix

| Signal | Weight | Justification |
|--------|--------|---------------|
| **DividendYield** | **2.0** | Central metric for income portfolio. This is what makes this portfolio unique. |
| **PayoutSafety** | **2.0** | Dividend sustainability. Payout ratio + FCF coverage. |
| **Earnings** | **2.0** | Earnings fund dividends. |
| **FCF** | **2.0** | Cash flow funds sustainable dividends. Lowell Miller. |
| **Debt** | **1.5** | Leverage threatens dividend safety. |
| **Revenue** | **1.0** | Business health context. |
| **ROE** | **1.0** | Business quality. |
| **GrossMargin** | **1.0** | Pricing power supports dividend growth through inflation. |
| **PE** | **1.0** | Valuation context — overpaying reduces yield. |
| **ExpertOverride** | **0.5** | Some qualitative judgment needed but less than other portfolios. |
| **BondYield** | **0.5** | Bond yields compete with dividend yields. Rate sensitivity. |
| **InsiderFlow** | **0.5** | Minor signal. |
| **PEG** | **0.0** | Not relevant for income-focused investing. |
| **ShortInterest** | **0.0** | Not primary concern for blue-chip dividend payers. |
| **RSI** | **0.0** | Income investors don't time entries technically. |
| **MACD** | **0.0** | Not applicable. |
| **SMA50/200** | **0.0** | Not applicable. |
| **GoldenCross** | **0.0** | Not applicable. |
| **RelativeStrength** | **0.0** | Not applicable. |

### Weight Hierarchy
1. **Tier 1 (2.0):** DividendYield, PayoutSafety, Earnings, FCF — the four pillars of sustainable income
2. **Tier 2 (1.5):** Debt — leverage directly threatens dividend safety
3. **Tier 3 (1.0):** Revenue, ROE, GrossMargin, PE — business quality and valuation
4. **Tier 4 (0.5):** ExpertOverride, BondYield, InsiderFlow — supporting
5. **Tier 5 (0.0):** PEG, ShortInterest, all technicals — not applicable

---

## 6. Style Differentiation

| Other Portfolio | Key Differentiator |
|----------------|-------------------|
| **Value Picks (Buffett)** | Income requires yield >= 1.5% and 10-year streak; Value doesn't require dividends. DividendYield at 2.0 vs 1.0. |
| **Growth Value (Lynch)** | Income optimizes for yield + safety; Growth optimizes for PEG. Completely different metrics. |
| **Innovation Fund (Wood)** | Income requires dividends; Innovation tolerates pre-profit with no dividends. Zero overlap. |
| **Momentum Growth (O'Neil)** | Income uses zero technicals; Momentum is technical-first. Income buys for yield; Momentum buys for price momentum. |
| **Nuclear/Defense** | Income is sector-agnostic; Nuclear/Defense are sector-constrained. |

The **hard dividend requirement** (yield >= 1.5%, 10-year streak, payout sustainability) is the definitive differentiator. No other BigClaw portfolio requires dividends.

---

## 7. Yield Trap Defense

The Chowder Rule is this portfolio's primary defense against yield traps:

**Chowder Rule:** Dividend Yield + 5-Year Dividend Growth Rate > threshold

| Category | Threshold | Rationale |
|----------|-----------|-----------|
| Normal stocks | > 12% | Balanced yield + growth |
| Utilities | > 8% | Lower growth expectations acceptable for regulated businesses |

**Example:** Stock A yields 5% with 2% growth = 7% Chowder → FAIL (yield trap)
**Example:** Stock B yields 2% with 12% growth = 14% Chowder → PASS (compounder)

The Chowder Rule catches the most dangerous trap: a high-yield stock with zero growth that's about to cut.

---

## 8. Implementation Checklist

- [ ] Update `PORTFOLIO_STYLES.md` with these rules
- [ ] Implement consecutive dividend increase streak computation from `Ticker.dividends`
- [ ] Implement Chowder Rule computation (yield + 5yr DGR)
- [ ] Add payout ratio gating with REIT/utility exemptions
- [ ] Add dividend freeze detection (R2)
- [ ] Update `style_compliance.py` gates, rejects, audits
- [ ] Update `decision_engine.py` signal weights
- [ ] Run compliance audit against current Income Dividends holdings
- [ ] Deploy to Pi and test

---

*Tiebreaker: Claude/Grok agreement prevails. Central debate (pure Aristocrats index vs practical DGI hybrid) resolved 3-to-1 in favor of hybrid approach. Minimum streak set at 10 years (Claude) over 5 (Grok/Gemini) and 25 (GPT). Yield floor at 1.5% and Chowder Rule as yield trap defense per Claude/Grok.*
