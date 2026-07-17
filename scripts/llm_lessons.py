# -*- coding: utf-8 -*-
"""Durable, curated lessons distilled from analyzing BigClaw's OWN real trades. Injected into the
Bull/Bear/Judge data feed of BOTH LLM portfolios (Comando + ETF Focus) every cycle.

These are LENSES, NOT RULES — the LLM still decides everything. This is the "benefit of what we've
learned" seed for the recursive learning loop: the journal accumulates each portfolio's OWN outcomes
over time; this seeds the worldview they reason from. Add distilled, evidence-backed findings here as
they are proven — keep it a TIGHT worldview, not a dumping ground."""


def render_lessons():
    return (
        "## LESSONS LEARNED — durable principles from our OWN track record (lenses, not rules; you still decide)\n"
        "Distilled from analyzing BigClaw's real trades. Not gates — hard-won context to reason with.\n"
        "\n"
        "1. EXTENSION IS RISK, NOT CONFIRMATION. Across 415 of our real buys, the SINGLE STRONGEST predictor\n"
        "   of POOR forward return was how far a stock had already run at entry. Names bought far above their\n"
        "   200-day moving average, or while overbought (RSI>70), tended to MEAN-REVERT — the most-extended\n"
        "   quintile returned about -8% vs SPY. A stock that has already sprinted is a WORSE entry, not a\n"
        "   better one. Where the compete view flags a name as extended, that is a reason for skepticism, not FOMO.\n"
        "2. BUYING STRENGTH IS NOT AN EDGE. Entry momentum (a 5-day pop, a large 60-day run, high volatility at\n"
        "   entry) all correlated NEGATIVELY with forward alpha. Prefer names near or reclaiming their mean and\n"
        "   turning up over names making fresh highs on a spike.\n"
        "3. OPPORTUNITY COST IS THE EXIT. Absolute stops and price targets added nothing once entries were\n"
        "   disciplined. The real exit question is: does a MATERIALLY BETTER name exist to own instead? Rotate\n"
        "   the weakest holding to fund the better one — that is a thesis_changed rotation (adaptation), not a\n"
        "   failure. Do not hold a played-out name while a stronger one is available.\n"
        "4. A LIVE CATALYST IS THE EDGE; PRICE ALONE IS A BANDWAGON. A name moving on price with no news behind\n"
        "   it is a crowd, not a thesis. (Already your doctrine — the data reinforces it.)\n"
    )
