#!/usr/bin/env python3
"""Earnings Analyzer — Analyzes the most recent earnings report for stock tickers."""

import argparse
import json
import sys
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf


def safe(fn, default=None):
    """Run fn, return default on any exception."""
    try:
        return fn()
    except Exception:
        return default


def analyze_ticker(ticker_symbol: str) -> dict:
    """Analyze most recent earnings for a ticker. Returns structured dict."""
    t = yf.Ticker(ticker_symbol)
    result = {
        "ticker": ticker_symbol.upper(),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "step1_numbers": {},
        "step2_guidance": {},
        "step3_segments": {},
        "step4_commentary": {},
        "step5_reaction": {},
        "step6_verdict": {},
        "errors": [],
    }

    # ── Step 1: The Numbers ──
    try:
        # EPS from earnings_dates
        ed = safe(lambda: t.earnings_dates)
        eps_actual = eps_estimate = eps_surprise = eps_surprise_pct = None
        earnings_date = None
        if ed is not None and len(ed) > 0:
            # Filter to past dates with actual EPS reported
            now = pd.Timestamp.now(tz="America/New_York")
            if ed.index.tz is None:
                now = now.tz_localize(None)
            past = ed[ed.index <= now]
            if "Reported EPS" in past.columns:
                past = past.dropna(subset=["Reported EPS"])
            if len(past) > 0:
                row = past.iloc[0]
                earnings_date = past.index[0]
                eps_actual = safe(lambda: float(row.get("Reported EPS", float("nan"))))
                eps_estimate = safe(lambda: float(row.get("EPS Estimate", float("nan"))))
                if eps_actual is not None and eps_estimate is not None:
                    eps_surprise = round(eps_actual - eps_estimate, 4)
                    if eps_estimate != 0:
                        eps_surprise_pct = round(eps_surprise / abs(eps_estimate) * 100, 2)

        result["step1_numbers"]["earnings_date"] = str(earnings_date)[:10] if earnings_date else None
        result["step1_numbers"]["eps_actual"] = eps_actual
        result["step1_numbers"]["eps_estimate"] = eps_estimate
        result["step1_numbers"]["eps_surprise"] = eps_surprise
        result["step1_numbers"]["eps_surprise_pct"] = eps_surprise_pct

        # Revenue from quarterly financials
        qf = safe(lambda: t.quarterly_financials)
        rev_actual = rev_estimate = rev_surprise = rev_surprise_pct = None
        if qf is not None and "Total Revenue" in qf.index:
            rev_actual = float(qf.loc["Total Revenue"].iloc[0])

        # Revenue estimate from revenue_estimate
        re = safe(lambda: t.revenue_estimate)
        if re is not None and len(re) > 0:
            try:
                val = re.iloc[:, 0].get("avg")
                if val is not None and not pd.isna(val):
                    rev_estimate = float(val)
            except Exception:
                pass

        if rev_actual and rev_estimate and rev_estimate != 0:
            rev_surprise = rev_actual - rev_estimate
            rev_surprise_pct = round(rev_surprise / abs(rev_estimate) * 100, 2)

        result["step1_numbers"]["revenue_actual"] = rev_actual
        result["step1_numbers"]["revenue_estimate"] = rev_estimate
        result["step1_numbers"]["revenue_surprise"] = rev_surprise
        result["step1_numbers"]["revenue_surprise_pct"] = rev_surprise_pct

        # One-time items flag
        gaap_ni = operating_income = None
        if qf is not None:
            for label in ["Net Income", "Net Income Common Stockholders"]:
                if label in qf.index:
                    gaap_ni = float(qf.loc[label].iloc[0])
                    break
            if "Operating Income" in qf.index:
                operating_income = float(qf.loc["Operating Income"].iloc[0])
        one_time_flag = False
        if gaap_ni is not None and operating_income is not None and operating_income != 0:
            gap_pct = abs(gaap_ni - operating_income) / abs(operating_income) * 100
            one_time_flag = gap_pct > 15
            result["step1_numbers"]["gaap_net_income"] = gaap_ni
            result["step1_numbers"]["operating_income"] = operating_income
            result["step1_numbers"]["gaap_vs_operating_gap_pct"] = round(gap_pct, 1)
        result["step1_numbers"]["one_time_items_flag"] = one_time_flag

    except Exception as e:
        result["errors"].append(f"Step 1 error: {e}")

    # ── Step 2: Forward Guidance ──
    try:
        ee = safe(lambda: t.earnings_estimate)
        re = safe(lambda: t.revenue_estimate)
        guidance = {}
        def _safe_float(series, key):
            v = safe(lambda: series[key] if key in series.index else series.get(key))
            if v is not None and not pd.isna(v):
                return float(v)
            return None

        def _safe_int(series, key):
            v = safe(lambda: series[key] if key in series.index else series.get(key))
            if v is not None and not pd.isna(v):
                return int(v)
            return 0

        # ee/re are indexed by period (0q, +1q, 0y, +1y), columns are metrics
        if ee is not None and len(ee) >= 2:
            guidance["eps_current_q"] = _safe_float(ee["avg"], ee.index[0])
            guidance["eps_next_q"] = _safe_float(ee["avg"], ee.index[1])
            for col_name in ["numberOfAnalystsUp"]:
                if col_name in ee.columns:
                    guidance["eps_revisions_up_current"] = _safe_int(ee[col_name], ee.index[0])
                    guidance["eps_revisions_up_next"] = _safe_int(ee[col_name], ee.index[1])
            for col_name in ["numberOfAnalystsDown"]:
                if col_name in ee.columns:
                    guidance["eps_revisions_down_current"] = _safe_int(ee[col_name], ee.index[0])
                    guidance["eps_revisions_down_next"] = _safe_int(ee[col_name], ee.index[1])
        if re is not None and len(re) >= 2:
            guidance["rev_current_q"] = _safe_float(re["avg"], re.index[0])
            guidance["rev_next_q"] = _safe_float(re["avg"], re.index[1])

        # Determine guidance direction from revisions
        up = (guidance.get("eps_revisions_up_current") or 0)
        down = (guidance.get("eps_revisions_down_current") or 0)
        if up > down:
            guidance["direction"] = "Raised"
        elif down > up:
            guidance["direction"] = "Lowered"
        else:
            guidance["direction"] = "Maintained"

        result["step2_guidance"] = guidance
    except Exception as e:
        result["errors"].append(f"Step 2 error: {e}")

    # ── Step 3: Business Segment Breakdown ──
    try:
        qf = safe(lambda: t.quarterly_financials)
        seg = {"quarters": [], "note": "Segment breakdown requires earnings call transcript"}
        if qf is not None and "Total Revenue" in qf.index:
            rev_row = qf.loc["Total Revenue"]
            cols = rev_row.index[:4]  # last 4 quarters
            for i, col in enumerate(cols):
                q = {"period": str(col)[:10], "revenue": float(rev_row[col])}
                # YoY: need same quarter last year — approximate with index+4 if available
                if i + 4 < len(rev_row):
                    yoy_rev = float(rev_row.iloc[i + 4])
                    if yoy_rev != 0:
                        q["yoy_growth_pct"] = round((q["revenue"] - yoy_rev) / abs(yoy_rev) * 100, 2)
                seg["quarters"].append(q)

            # Margins
            for i, col in enumerate(cols):
                rev = float(rev_row[col])
                if rev == 0:
                    continue
                q = seg["quarters"][i] if i < len(seg["quarters"]) else {}
                gp = safe(lambda c=col: float(qf.loc["Gross Profit"][c]) if "Gross Profit" in qf.index else None)
                oi = safe(lambda c=col: float(qf.loc["Operating Income"][c]) if "Operating Income" in qf.index else None)
                ni = None
                for label in ["Net Income", "Net Income Common Stockholders"]:
                    if label in qf.index:
                        ni = safe(lambda c=col, l=label: float(qf.loc[l][c]))
                        break
                if gp is not None:
                    q["gross_margin_pct"] = round(gp / rev * 100, 2)
                if oi is not None:
                    q["operating_margin_pct"] = round(oi / rev * 100, 2)
                if ni is not None:
                    q["net_margin_pct"] = round(ni / rev * 100, 2)

        result["step3_segments"] = seg
    except Exception as e:
        result["errors"].append(f"Step 3 error: {e}")

    # ── Step 4: Management Commentary ──
    try:
        news = safe(lambda: t.news, [])
        keywords = ["earning", "quarter", "revenue", "profit", "guidance", "eps", "beat", "miss", "results", "outlook", "forecast"]
        relevant = []
        for item in (news or []):
            # Handle both old and new yfinance news formats
            title = item.get("title", "") or ""
            if not title and "content" in item:
                title = item["content"].get("title", "")
            link = item.get("link", "") or item.get("url", "")
            if not link and "content" in item:
                link = item["content"].get("canonicalUrl", {}).get("url", "")
            publisher = item.get("publisher", "")
            if not publisher and "content" in item:
                publisher = item["content"].get("provider", {}).get("displayName", "")
            if any(kw in title.lower() for kw in keywords):
                relevant.append({"title": title, "link": link, "publisher": publisher})
            if len(relevant) >= 5:
                break
        result["step4_commentary"] = {
            "note": "Earnings call transcript not available via free APIs",
            "earnings_headlines": relevant,
        }
    except Exception as e:
        result["errors"].append(f"Step 4 error: {e}")

    # ── Step 5: Market & Analyst Reaction ──
    try:
        reaction = {}
        # Price reaction around earnings
        ed_date = result["step1_numbers"].get("earnings_date")
        if ed_date and ed_date != "None":
            dt = pd.Timestamp(ed_date)
            start = (dt - timedelta(days=5)).strftime("%Y-%m-%d")
            end = (dt + timedelta(days=5)).strftime("%Y-%m-%d")
            hist = safe(lambda: t.history(start=start, end=end))
            if hist is not None and len(hist) >= 2:
                idx = hist.index
                if idx.tz is not None:
                    dt = dt.tz_localize(idx.tz)
                before = hist[idx < dt]
                after = hist[idx >= dt]
                if len(before) > 0 and len(after) > 0:
                    close_before = float(before["Close"].iloc[-1])
                    close_after = float(after["Close"].iloc[0])
                    reaction["close_before_earnings"] = round(close_before, 2)
                    reaction["close_after_earnings"] = round(close_after, 2)
                    reaction["price_change_pct"] = round((close_after - close_before) / close_before * 100, 2)

        # Analyst data from finvizfinance
        try:
            from finvizfinance.quote import finvizfinance as fvf
            stock_fv = fvf(ticker_symbol)
            fundament = stock_fv.ticker_fundament()
            reaction["analyst_target_price"] = fundament.get("Target Price", "N/A")
            reaction["analyst_recommendation"] = fundament.get("Recom", "N/A")

            # Outer ratings
            try:
                ratings = stock_fv.ticker_outer_ratings()
                if ratings is not None and len(ratings) > 0:
                    for col in ratings.columns:
                        ratings[col] = ratings[col].astype(str)
                    recent = ratings.head(5).to_dict("records")
                    reaction["recent_ratings"] = recent
            except Exception:
                pass
        except Exception as e:
            result["errors"].append(f"finvizfinance error: {e}")

        result["step5_reaction"] = reaction
    except Exception as e:
        result["errors"].append(f"Step 5 error: {e}")

    # ── Step 6: The Verdict ──
    try:
        verdict = {}
        eps_s = result["step1_numbers"].get("eps_surprise_pct")
        rev_s = result["step1_numbers"].get("revenue_surprise_pct")

        if eps_s is not None:
            if eps_s > 10:
                verdict["eps_assessment"] = "Strong Beat"
            elif eps_s > 0:
                verdict["eps_assessment"] = "Beat"
            elif eps_s > -2:
                verdict["eps_assessment"] = "In-Line"
            elif eps_s > -10:
                verdict["eps_assessment"] = "Miss"
            else:
                verdict["eps_assessment"] = "Strong Miss"
        else:
            verdict["eps_assessment"] = "N/A"

        if rev_s is not None:
            if rev_s > 5:
                verdict["revenue_assessment"] = "Strong Beat"
            elif rev_s > 0:
                verdict["revenue_assessment"] = "Beat"
            elif rev_s > -2:
                verdict["revenue_assessment"] = "In-Line"
            elif rev_s > -5:
                verdict["revenue_assessment"] = "Miss"
            else:
                verdict["revenue_assessment"] = "Strong Miss"
        else:
            verdict["revenue_assessment"] = "N/A"

        verdict["guidance_direction"] = result["step2_guidance"].get("direction", "N/A")

        # Overall
        scores = {"Strong Beat": 2, "Beat": 1, "In-Line": 0, "Miss": -1, "Strong Miss": -2, "N/A": 0}
        total = scores.get(verdict["eps_assessment"], 0) + scores.get(verdict["revenue_assessment"], 0)
        gd = verdict["guidance_direction"]
        if gd == "Raised":
            total += 1
        elif gd == "Lowered":
            total -= 1
        if total >= 3:
            verdict["overall"] = "Strong Beat"
        elif total >= 1:
            verdict["overall"] = "Beat"
        elif total >= -1:
            verdict["overall"] = "In-Line"
        elif total >= -3:
            verdict["overall"] = "Miss"
        else:
            verdict["overall"] = "Strong Miss"

        # Key metric
        if result["step1_numbers"].get("one_time_items_flag"):
            verdict["key_metric_next_q"] = "Watch GAAP vs operating income gap — significant one-time items detected"
        elif gd == "Lowered":
            verdict["key_metric_next_q"] = "Watch for further estimate revisions — guidance was lowered"
        else:
            verdict["key_metric_next_q"] = "Revenue growth trajectory and margin expansion"

        result["step6_verdict"] = verdict
    except Exception as e:
        result["errors"].append(f"Step 6 error: {e}")

    return result


def fmt_num(n, prefix="$", billions=True):
    """Format a number nicely."""
    if n is None:
        return "N/A"
    if billions and abs(n) >= 1e9:
        return f"{prefix}{n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"{prefix}{n/1e6:.1f}M"
    return f"{prefix}{n:,.2f}"


def render_markdown(data: dict) -> str:
    """Render analysis dict as markdown."""
    lines = []
    s1 = data["step1_numbers"]
    s2 = data["step2_guidance"]
    s3 = data["step3_segments"]
    s4 = data["step4_commentary"]
    s5 = data["step5_reaction"]
    s6 = data["step6_verdict"]

    lines.append(f"# 📊 Earnings Analysis: {data['ticker']}")
    lines.append(f"*Generated {data['generated']}*\n")

    # Step 1
    lines.append("## 1. The Numbers")
    lines.append(f"- **Earnings Date:** {s1.get('earnings_date', 'N/A')} *(yfinance)*")
    lines.append(f"- **EPS Actual:** {s1.get('eps_actual', 'N/A')}  |  **Estimate:** {s1.get('eps_estimate', 'N/A')} *(yfinance)*")
    if s1.get("eps_surprise") is not None:
        lines.append(f"  - Surprise: {'+' if s1['eps_surprise']>=0 else ''}{s1['eps_surprise']} ({'+' if s1['eps_surprise_pct']>=0 else ''}{s1['eps_surprise_pct']}%)")
    lines.append(f"- **Revenue Actual:** {fmt_num(s1.get('revenue_actual'))}  |  **Estimate:** {fmt_num(s1.get('revenue_estimate'))} *(yfinance)*")
    if s1.get("revenue_surprise") is not None and s1.get("revenue_surprise_pct") is not None:
        lines.append(f"  - Surprise: {fmt_num(s1['revenue_surprise'])} ({'+' if s1['revenue_surprise_pct']>=0 else ''}{s1['revenue_surprise_pct']}%)")
    if s1.get("one_time_items_flag"):
        lines.append(f"- ⚠️ **One-Time Items Flag:** GAAP NI {fmt_num(s1.get('gaap_net_income'))} vs Operating Income {fmt_num(s1.get('operating_income'))} (gap: {s1.get('gaap_vs_operating_gap_pct')}%)")
    lines.append("")

    # Step 2
    lines.append("## 2. Forward Guidance")
    if s2:
        lines.append(f"- **Direction:** {s2.get('direction', 'N/A')} *(based on analyst revisions, yfinance)*")
        lines.append(f"- **EPS Est Current Q:** {s2.get('eps_current_q') or 'N/A'}  |  **Next Q:** {s2.get('eps_next_q') or 'N/A'}")
        lines.append(f"- **Rev Est Current Q:** {fmt_num(s2.get('rev_current_q'))}  |  **Next Q:** {fmt_num(s2.get('rev_next_q'))}")
        lines.append(f"- Revisions (Current Q): ↑{s2.get('eps_revisions_up_current', 0)} / ↓{s2.get('eps_revisions_down_current', 0)}")
        lines.append(f"- Revisions (Next Q): ↑{s2.get('eps_revisions_up_next', 0)} / ↓{s2.get('eps_revisions_down_next', 0)}")
    else:
        lines.append("- *No forward guidance data available*")
    lines.append("")

    # Step 3
    lines.append("## 3. Quarterly Revenue & Margins")
    if s3.get("quarters"):
        lines.append("| Quarter | Revenue | YoY Growth | Gross Margin | Op Margin | Net Margin |")
        lines.append("|---------|---------|-----------|-------------|----------|-----------|")
        for q in s3["quarters"]:
            yoy = f"{q['yoy_growth_pct']:+.1f}%" if "yoy_growth_pct" in q else "—"
            gm = f"{q['gross_margin_pct']:.1f}%" if "gross_margin_pct" in q else "—"
            om = f"{q['operating_margin_pct']:.1f}%" if "operating_margin_pct" in q else "—"
            nm = f"{q['net_margin_pct']:.1f}%" if "net_margin_pct" in q else "—"
            lines.append(f"| {q['period']} | {fmt_num(q['revenue'])} | {yoy} | {gm} | {om} | {nm} |")
    lines.append(f"\n*{s3.get('note', '')}* *(yfinance quarterly_financials)*\n")

    # Step 4
    lines.append("## 4. Management Commentary")
    lines.append(f"*{s4.get('note', '')}*\n")
    headlines = s4.get("earnings_headlines", [])
    if headlines:
        for h in headlines:
            link = h.get("link", "")
            pub = f" ({h['publisher']})" if h.get("publisher") else ""
            lines.append(f"- [{h['title']}]({link}){pub}")
    else:
        lines.append("- *No earnings-related headlines found*")
    lines.append("")

    # Step 5
    lines.append("## 5. Market & Analyst Reaction")
    if s5.get("close_before_earnings"):
        lines.append(f"- **Pre-Earnings Close:** ${s5['close_before_earnings']}  →  **Post-Earnings Close:** ${s5['close_after_earnings']}  ({'+' if s5['price_change_pct']>=0 else ''}{s5['price_change_pct']}%) *(yfinance)*")
    lines.append(f"- **Analyst Target Price:** {s5.get('analyst_target_price', 'N/A')} *(finvizfinance)*")
    lines.append(f"- **Recommendation:** {s5.get('analyst_recommendation', 'N/A')} *(finvizfinance)*")
    if s5.get("recent_ratings"):
        lines.append("- **Recent Ratings:**")
        for r in s5["recent_ratings"][:5]:
            lines.append(f"  - {str(r.get('Date', ''))[:10]} | {r.get('Status', '')} | {r.get('Outer', '')} | {r.get('Rating', '')} | {r.get('Price', '')}")
    lines.append("")

    # Step 6
    lines.append("## 6. The Verdict")
    lines.append(f"- **Revenue:** {s6.get('revenue_assessment', 'N/A')}")
    lines.append(f"- **EPS:** {s6.get('eps_assessment', 'N/A')}")
    lines.append(f"- **Guidance:** {s6.get('guidance_direction', 'N/A')}")
    lines.append(f"- **Overall: {s6.get('overall', 'N/A')}**")
    lines.append(f"- 🔭 *Key metric next Q:* {s6.get('key_metric_next_q', 'N/A')}")
    lines.append("")

    if data.get("errors"):
        lines.append("---\n*Errors encountered:*")
        for e in data["errors"]:
            lines.append(f"- {e}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze most recent earnings for stock tickers")
    parser.add_argument("tickers", nargs="+", help="Stock ticker(s) to analyze")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output as JSON")
    args = parser.parse_args()

    results = []
    for ticker in args.tickers:
        data = analyze_ticker(ticker)
        results.append(data)

    if args.json_output:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2, default=str))
    else:
        for data in results:
            print(render_markdown(data))
            if len(results) > 1:
                print("\n---\n")


if __name__ == "__main__":
    main()
