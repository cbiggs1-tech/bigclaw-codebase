#!/usr/bin/env python3
"""Macro/Market Scanner — provides a broad market overview with optional sector/ticker context."""

import argparse
import json
import sys
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd

# ── Constants ──────────────────────────────────────────────────────────────────

FED_FUNDS_RATE = "4.25–4.50%"

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communications",
}

SECTOR_NAME_TO_ETF = {v: k for k, v in SECTOR_ETFS.items()}

RATE_SENSITIVE_SECTORS = {
    "Real Estate", "Utilities", "Financials", "Consumer Discretionary", "Technology",
    "Consumer Cyclical",  # yfinance name for Consumer Discretionary
}

# Map yfinance sector names to our ETF sector names
YFINANCE_SECTOR_MAP = {
    "Consumer Cyclical": "Consumer Discretionary",
    "Financial Services": "Financials",
    "Basic Materials": "Materials",
    "Communication Services": "Communications",
}

INDEX_TICKERS = {
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Dow Jones": "^DJI",
    "Russell 2000": "^RUT",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def safe_download(ticker, period="1y", interval="1d"):
    """Download with error handling."""
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return pd.DataFrame()


def pct_change_over(df, days):
    """Return % change over last N calendar days from most recent close."""
    if df.empty or len(df) < 2:
        return None
    cutoff = df.index[-1] - timedelta(days=days)
    prior = df[df.index <= cutoff]
    if prior.empty:
        return None
    return (df["Close"].iloc[-1] / prior["Close"].iloc[-1] - 1) * 100


def ytd_change(df):
    """YTD % change."""
    if df.empty:
        return None
    year_start = pd.Timestamp(datetime(df.index[-1].year, 1, 1), tz=df.index.tz)
    prior = df[df.index <= year_start]
    if prior.empty:
        prior = df.head(1)
    return (df["Close"].iloc[-1] / prior["Close"].iloc[-1] - 1) * 100


def sma(df, window):
    if df.empty or len(df) < window:
        return None
    return df["Close"].rolling(window).mean().iloc[-1]


def fmt(val, suffix="%", decimals=2):
    if val is None:
        return "N/A"
    return f"{val:+.{decimals}f}{suffix}" if suffix == "%" else f"{val:,.{decimals}f}{suffix}"


def classify_vix(level):
    if level is None:
        return "Unknown"
    if level < 15:
        return "Low"
    if level < 20:
        return "Moderate"
    if level < 30:
        return "Elevated"
    return "High"


# ── Data Collection ────────────────────────────────────────────────────────────

def get_rates():
    """Step 1: Interest rates & yield curve."""
    data = {}
    # 10-Year
    tnx = safe_download("^TNX", period="3mo")
    ten_yr = tnx["Close"].iloc[-1] if not tnx.empty else None

    # 2-Year — ^IRX is 13-week T-bill; try ^TWO as proxy, fall back
    two_yr = None
    for t in ["2YY=F", "^IRX"]:
        df = safe_download(t, period="3mo")
        if not df.empty:
            two_yr = df["Close"].iloc[-1]
            if t == "^IRX":
                # ^IRX is 13-week, not 2-year, but best available proxy
                pass
            break

    data["fed_funds"] = FED_FUNDS_RATE
    data["ten_year"] = round(float(ten_yr), 3) if ten_yr is not None else None
    data["two_year"] = round(float(two_yr), 3) if two_yr is not None else None

    if ten_yr is not None and two_yr is not None:
        spread = float(ten_yr - two_yr)
        data["yield_spread"] = round(spread, 3)
        data["inverted"] = spread < 0
    else:
        data["yield_spread"] = None
        data["inverted"] = None

    return data


def get_market_overview():
    """Step 2: Major indices."""
    results = {}
    for name, ticker in INDEX_TICKERS.items():
        df = safe_download(ticker, period="1y")
        if df.empty:
            results[name] = {"price": None, "ytd": None, "1mo": None, "3mo": None}
            continue
        results[name] = {
            "ticker": ticker,
            "price": round(float(df["Close"].iloc[-1]), 2),
            "ytd": round(float(ytd_change(df)), 2) if ytd_change(df) is not None else None,
            "1mo": round(float(pct_change_over(df, 30)), 2) if pct_change_over(df, 30) is not None else None,
            "3mo": round(float(pct_change_over(df, 90)), 2) if pct_change_over(df, 90) is not None else None,
        }

    # VIX
    vix_df = safe_download("^VIX", period="3mo")
    vix_level = round(float(vix_df["Close"].iloc[-1]), 2) if not vix_df.empty else None
    vix_1mo = round(float(pct_change_over(vix_df, 30)), 2) if not vix_df.empty and pct_change_over(vix_df, 30) is not None else None
    results["VIX"] = {"level": vix_level, "classification": classify_vix(vix_level), "1mo_change": vix_1mo}

    return results


def get_sector_performance():
    """Step 3: Sector ETF performance."""
    sectors = []
    for etf, name in SECTOR_ETFS.items():
        df = safe_download(etf, period="1y")
        if df.empty:
            sectors.append({"etf": etf, "sector": name, "1mo": None, "3mo": None, "above_50sma": None, "above_200sma": None})
            continue
        mo1 = pct_change_over(df, 30)
        mo3 = pct_change_over(df, 90)
        sma50 = sma(df, 50)
        sma200 = sma(df, 200)
        price = float(df["Close"].iloc[-1])
        sectors.append({
            "etf": etf,
            "sector": name,
            "price": round(price, 2),
            "1mo": round(float(mo1), 2) if mo1 is not None else None,
            "3mo": round(float(mo3), 2) if mo3 is not None else None,
            "above_50sma": price > sma50 if sma50 else None,
            "above_200sma": price > sma200 if sma200 else None,
        })
    sectors.sort(key=lambda x: x["1mo"] if x["1mo"] is not None else -999, reverse=True)
    return sectors


def get_risk_indicators(rates, market):
    """Step 5: Risk indicators."""
    indicators = {}
    indicators["vix"] = market.get("VIX", {})

    for label, ticker in [("Gold (GLD)", "GLD"), ("US Dollar (UUP)", "UUP"), ("Bitcoin", "BTC-USD")]:
        df = safe_download(ticker, period="3mo")
        if df.empty:
            indicators[label] = {"price": None, "1mo": None}
            continue
        indicators[label] = {
            "price": round(float(df["Close"].iloc[-1]), 2),
            "1mo": round(float(pct_change_over(df, 30)), 2) if pct_change_over(df, 30) is not None else None,
        }

    indicators["yield_curve"] = {
        "spread": rates.get("yield_spread"),
        "inverted": rates.get("inverted"),
    }
    return indicators


def get_consumer_sentiment():
    """Step 6: Consumer & Market Sentiment indicators."""
    import requests
    data = {}

    # 1. University of Michigan Consumer Sentiment (FRED, no API key)
    try:
        url = ("https://fred.stlouisfed.org/graph/fredgraph.csv"
               "?id=UMCSENT&cosd=2024-01-01&coed=2026-12-31")
        r = requests.get(url, headers={"User-Agent": "BigClawBot/1.0"}, timeout=10)
        if r.status_code == 200:
            lines = [l for l in r.text.strip().split('\n')[1:] if '.' in l.split(',')[-1]]
            if lines:
                vals = [(l.split(',')[0], float(l.split(',')[1])) for l in lines if l.split(',')[1].replace('.','').replace('-','').isdigit()]
                if vals:
                    current = vals[-1]
                    prev = vals[-2] if len(vals) > 1 else None
                    yr_ago = None
                    for d, v in vals:
                        if d.startswith(str(int(current[0][:4]) - 1)):
                            yr_ago = v  # keep last one from prior year
                    # Historical context (long-run avg ~85, pre-COVID ~100, COVID low ~50)
                    level = current[1]
                    if level >= 90:
                        assessment = "Healthy"
                    elif level >= 70:
                        assessment = "Below average"
                    elif level >= 55:
                        assessment = "Depressed"
                    else:
                        assessment = "Crisis-level"
                    # Percentile approximation (range roughly 50-110 since 1960s)
                    pctile = max(0, min(100, (level - 50) / 60 * 100))
                    data["michigan"] = {
                        "current": level,
                        "date": current[0],
                        "previous": prev[1] if prev else None,
                        "prev_date": prev[0] if prev else None,
                        "year_ago": yr_ago,
                        "assessment": assessment,
                        "percentile": round(pctile),
                        "mom_change": round(level - prev[1], 1) if prev else None,
                    }
    except Exception as e:
        data["michigan_error"] = str(e)

    # 2. CNN Fear & Greed Index
    try:
        r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                         headers={"User-Agent": "BigClawBot/1.0"}, timeout=10)
        if r.status_code == 200:
            fg = r.json().get("fear_and_greed", {})
            score = fg.get("score")
            if score is not None:
                data["fear_greed"] = {
                    "score": round(score, 1),
                    "rating": fg.get("rating", "N/A"),
                    "previous": round(fg.get("previous_close", 0), 1) if fg.get("previous_close") else None,
                    "1w_ago": round(fg.get("previous_1_week", 0), 1) if fg.get("previous_1_week") else None,
                    "1m_ago": round(fg.get("previous_1_month", 0), 1) if fg.get("previous_1_month") else None,
                }
    except Exception as e:
        data["fear_greed_error"] = str(e)

    # 3. Personal Saving Rate (FRED: PSAVERT)
    try:
        url = ("https://fred.stlouisfed.org/graph/fredgraph.csv"
               "?id=PSAVERT&cosd=2024-01-01&coed=2026-12-31")
        r = requests.get(url, headers={"User-Agent": "BigClawBot/1.0"}, timeout=10)
        if r.status_code == 200:
            lines = [l for l in r.text.strip().split('\n')[1:] if '.' in l.split(',')[-1]]
            if lines:
                vals = [(l.split(',')[0], float(l.split(',')[1])) for l in lines if l.split(',')[1].replace('.','').replace('-','').isdigit()]
                if vals:
                    current = vals[-1]
                    data["saving_rate"] = {
                        "current": current[1],
                        "date": current[0],
                        "assessment": "Healthy" if current[1] >= 6 else "Low" if current[1] >= 3 else "Critical",
                    }
    except Exception as e:
        data["saving_rate_error"] = str(e)

    # 4. S&P 500 / Gold ratio (regime indicator — Cathie Wood highlight)
    try:
        sp = safe_download("^GSPC", period="1y")
        gold = safe_download("GLD", period="1y")
        oil = safe_download("USO", period="1y")
        if not sp.empty and not gold.empty:
            # Current ratio
            sp_gold = float(sp["Close"].iloc[-1] / gold["Close"].iloc[-1])
            # 1mo ago
            sp_1mo = sp[sp.index <= sp.index[-1] - timedelta(days=30)]
            gold_1mo = gold[gold.index <= gold.index[-1] - timedelta(days=30)]
            sp_gold_1mo = None
            if not sp_1mo.empty and not gold_1mo.empty:
                sp_gold_1mo = float(sp_1mo["Close"].iloc[-1] / gold_1mo["Close"].iloc[-1])
            data["sp_gold_ratio"] = {
                "current": round(sp_gold, 2),
                "1mo_ago": round(sp_gold_1mo, 2) if sp_gold_1mo else None,
                "trend": "declining" if sp_gold_1mo and sp_gold < sp_gold_1mo else "rising" if sp_gold_1mo and sp_gold > sp_gold_1mo else "flat",
            }
        if not sp.empty and not oil.empty:
            sp_oil = float(sp["Close"].iloc[-1] / oil["Close"].iloc[-1])
            sp_1mo = sp[sp.index <= sp.index[-1] - timedelta(days=30)]
            oil_1mo = oil[oil.index <= oil.index[-1] - timedelta(days=30)]
            sp_oil_1mo = None
            if not sp_1mo.empty and not oil_1mo.empty:
                sp_oil_1mo = float(sp_1mo["Close"].iloc[-1] / oil_1mo["Close"].iloc[-1])
            data["sp_oil_ratio"] = {
                "current": round(sp_oil, 2),
                "1mo_ago": round(sp_oil_1mo, 2) if sp_oil_1mo else None,
                "trend": "rising" if sp_oil_1mo and sp_oil > sp_oil_1mo else "declining" if sp_oil_1mo and sp_oil < sp_oil_1mo else "flat",
            }
    except Exception as e:
        data["ratio_error"] = str(e)

    # Contrarian signal: extreme readings
    contrarian = None
    michigan = data.get("michigan", {})
    fg = data.get("fear_greed", {})
    if michigan.get("current") and fg.get("score"):
        mich_low = michigan["current"] < 60
        fg_fear = fg["score"] < 30
        mich_high = michigan["current"] > 95
        fg_greed = fg["score"] > 75
        if mich_low and fg_fear:
            contrarian = "🟢 CONTRARIAN BUY SIGNAL — Both consumer sentiment and market fear at depressed levels. Historically bullish."
        elif mich_high and fg_greed:
            contrarian = "🔴 CONTRARIAN SELL SIGNAL — Both consumer confidence and market greed elevated. Historically bearish."
        elif mich_low or fg_fear:
            contrarian = "🟡 Partial contrarian signal — one sentiment indicator depressed. Watch for confirmation."
    data["contrarian_signal"] = contrarian

    return data


def get_bond_signals():
    """Section 7: Bond Market Signals — yield curve, credit spreads, 10Y level."""
    import requests
    data = {"yield_curve": {}, "credit_spreads": {}, "ten_year": {}, "scores": {}, "combined_score": 0}

    def fetch_fred_csv(series_id, days_back=90):
        """Fetch FRED series via CSV download."""
        from datetime import datetime, timedelta
        start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
        try:
            r = requests.get(url, headers={"User-Agent": "BigClawBot/1.0"}, timeout=10)
            if r.status_code == 200:
                lines = r.text.strip().split('\n')[1:]  # skip header
                vals = []
                for l in lines:
                    parts = l.split(',')
                    if len(parts) == 2 and parts[1].strip() not in ('', '.'):
                        try:
                            vals.append((parts[0], float(parts[1])))
                        except ValueError:
                            pass
                return vals
        except Exception:
            pass
        return []

    # 1. Yield Curve (2Y-10Y spread)
    dgs2 = fetch_fred_csv("DGS2", 90)
    dgs10 = fetch_fred_csv("DGS10", 90)
    if dgs2 and dgs10:
        # Align on common dates
        d2 = dict(dgs2)
        d10 = dict(dgs10)
        common = sorted(set(d2.keys()) & set(d10.keys()))
        if common:
            current_spread = d10[common[-1]] - d2[common[-1]]
            # 1-month ago spread for trend
            month_ago_idx = max(0, len(common) - 22)
            prev_spread = d10[common[month_ago_idx]] - d2[common[month_ago_idx]]
            spread_change = current_spread - prev_spread

            data["yield_curve"] = {
                "two_year": d2[common[-1]],
                "ten_year": d10[common[-1]],
                "spread": round(current_spread, 3),
                "spread_1mo_ago": round(prev_spread, 3),
                "spread_change": round(spread_change, 3),
                "date": common[-1],
            }

            # Score: >0.5% and steepening = bullish, <-0.2% = bearish
            if current_spread > 0.5:
                data["scores"]["yield_curve"] = 1
                data["yield_curve"]["assessment"] = "Normal & steepening — bullish"
            elif current_spread < -0.2:
                data["scores"]["yield_curve"] = -1
                data["yield_curve"]["assessment"] = "Inverted — bearish"
            else:
                data["scores"]["yield_curve"] = 0
                data["yield_curve"]["assessment"] = "Flat — neutral"

    # 2. Credit Spreads (HY OAS)
    hy_oas = fetch_fred_csv("BAMLH0A0HYM2", 90)
    if hy_oas:
        current_oas = hy_oas[-1][1]
        month_ago_idx = max(0, len(hy_oas) - 22)
        prev_oas = hy_oas[month_ago_idx][1]
        oas_change = current_oas - prev_oas

        data["credit_spreads"] = {
            "current_bps": round(current_oas * 100, 0),  # FRED reports in %, convert to bps
            "raw_value": current_oas,
            "prev_value": prev_oas,
            "change": round(oas_change, 2),
            "date": hy_oas[-1][0],
        }

        # FRED HY OAS is in percentage points (e.g., 3.50 = 350bps)
        bps = current_oas * 100
        if bps < 350:
            data["scores"]["credit_spreads"] = 1
            data["credit_spreads"]["assessment"] = f"Tight ({bps:.0f}bps) — bullish"
        elif bps > 450:
            data["scores"]["credit_spreads"] = -1
            data["credit_spreads"]["assessment"] = f"Wide ({bps:.0f}bps) — bearish"
        else:
            data["scores"]["credit_spreads"] = 0
            data["credit_spreads"]["assessment"] = f"Stable ({bps:.0f}bps) — neutral"

    # 3. 10Y Treasury Level
    if dgs10:
        current_10y = dgs10[-1][1]
        month_ago_idx = max(0, len(dgs10) - 22)
        prev_10y = dgs10[month_ago_idx][1]
        change_bps = (current_10y - prev_10y) * 100  # in basis points

        data["ten_year"] = {
            "current": current_10y,
            "prev": prev_10y,
            "change_bps": round(change_bps, 1),
            "date": dgs10[-1][0],
        }

        if current_10y < 4.0 or change_bps < -20:
            data["scores"]["ten_year_level"] = 1
            data["ten_year"]["assessment"] = "Low/falling — bullish"
        elif current_10y > 4.5 or change_bps > 20:
            data["scores"]["ten_year_level"] = -1
            data["ten_year"]["assessment"] = "High/rising — bearish"
        else:
            data["scores"]["ten_year_level"] = 0
            data["ten_year"]["assessment"] = "Stable — neutral"

    # Combined score
    data["combined_score"] = sum(data["scores"].values())
    return data


def get_economic_context():
    """Step 7: Economic data links and recent news."""
    links = {
        "CPI": "https://www.bls.gov/cpi/",
        "Jobs Report": "https://www.bls.gov/news.release/empsit.nr0.htm",
        "GDP": "https://www.bea.gov/data/gdp/gross-domestic-product",
        "FOMC Calendar": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    }

    headlines = []
    try:
        from finvizfinance.news import News
        n = News()
        news = n.get_news()
        if isinstance(news, dict) and "news" in news:
            for item in news["news"][:5]:
                headlines.append({"title": item.get("Title", ""), "link": item.get("Link", ""), "date": str(item.get("Date", ""))})
        elif isinstance(news, pd.DataFrame) and not news.empty:
            for _, row in news.head(5).iterrows():
                headlines.append({"title": str(row.get("Title", "")), "link": str(row.get("Link", "")), "date": str(row.get("Date", ""))})
    except Exception:
        pass

    return {"links": links, "headlines": headlines}


def get_ticker_context(ticker):
    """Get ticker-specific info for contextual commentary."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "name": info.get("shortName", ticker),
            "sector": info.get("sector", "Unknown"),
            "beta": info.get("beta"),
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "market_cap": info.get("marketCap"),
            "pe": info.get("trailingPE"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
        }
    except Exception:
        return {"name": ticker, "sector": "Unknown", "beta": None}


# ── Verdict ────────────────────────────────────────────────────────────────────

def compute_verdict(rates, market, sectors, risk, ticker_ctx=None, sector_filter=None, sentiment=None, bond_signals=None):
    """Step 8: Strategic verdict."""
    signals = {"bullish": 0, "bearish": 0}

    # VIX
    vix = market.get("VIX", {}).get("level")
    if vix is not None:
        if vix < 15:
            signals["bullish"] += 2
        elif vix < 20:
            signals["bullish"] += 1
        elif vix < 30:
            signals["bearish"] += 1
        else:
            signals["bearish"] += 2

    # Yield curve
    if rates.get("inverted"):
        signals["bearish"] += 1
    elif rates.get("yield_spread") is not None:
        signals["bullish"] += 1

    # Market trend (S&P 500 1mo)
    sp = market.get("S&P 500", {}).get("1mo")
    if sp is not None:
        if sp > 2:
            signals["bullish"] += 1
        elif sp < -2:
            signals["bearish"] += 1

    # Breadth
    above50 = sum(1 for s in sectors if s.get("above_50sma"))
    total = sum(1 for s in sectors if s.get("above_50sma") is not None)
    if total:
        breadth = above50 / total
        if breadth > 0.7:
            signals["bullish"] += 1
        elif breadth < 0.3:
            signals["bearish"] += 1

    # Gold rising = risk-off signal
    gold_1mo = risk.get("Gold (GLD)", {}).get("1mo")
    if gold_1mo is not None and gold_1mo > 3:
        signals["bearish"] += 1

    # Consumer/market sentiment (contrarian)
    if sentiment:
        fg = sentiment.get("fear_greed", {})
        michigan = sentiment.get("michigan", {})
        # Extreme fear = contrarian bullish
        if fg.get("score") is not None:
            if fg["score"] < 25:
                signals["bullish"] += 1  # Extreme fear = contrarian buy
            elif fg["score"] > 80:
                signals["bearish"] += 1  # Extreme greed = contrarian sell
        # Very depressed consumer sentiment = contrarian bullish (historically)
        if michigan.get("current") is not None:
            if michigan["current"] < 55:
                signals["bullish"] += 1  # Crisis-level = bottoming signal
            elif michigan["current"] > 100:
                signals["bearish"] += 1  # Euphoria

    # Bond market signals
    if bond_signals:
        bond_score = bond_signals.get("combined_score", 0)
        if bond_score >= 2:
            signals["bullish"] += 1
        elif bond_score <= -2:
            signals["bearish"] += 1

    score = signals["bullish"] - signals["bearish"]
    if score >= 2:
        environment = "Risk-On"
        positioning = "Aggressive"
    elif score <= -2:
        environment = "Risk-Off"
        positioning = "Defensive"
    else:
        environment = "Mixed"
        positioning = "Neutral"

    # Ticker/sector-specific
    specific = None
    if ticker_ctx and ticker_ctx.get("sector"):
        sector_name = YFINANCE_SECTOR_MAP.get(ticker_ctx["sector"], ticker_ctx["sector"])
        beta = ticker_ctx.get("beta")
        rate_sens = sector_name in RATE_SENSITIVE_SECTORS
        # Find sector perf
        sector_perf = next((s for s in sectors if s["sector"] == sector_name), None)
        headwinds = []
        tailwinds = []
        if sector_perf and sector_perf.get("1mo") is not None:
            if sector_perf["1mo"] > 2:
                tailwinds.append(f"{sector_name} sector up {sector_perf['1mo']:.1f}% this month")
            elif sector_perf["1mo"] < -2:
                headwinds.append(f"{sector_name} sector down {sector_perf['1mo']:.1f}% this month")
        if rate_sens and rates.get("ten_year") and rates["ten_year"] > 4.5:
            headwinds.append("High rates pressure rate-sensitive sectors")
        if beta and beta > 1.3 and environment == "Risk-Off":
            headwinds.append(f"High beta ({beta:.2f}) amplifies downside in risk-off")
        if beta and beta > 1.3 and environment == "Risk-On":
            tailwinds.append(f"High beta ({beta:.2f}) amplifies upside in risk-on")
        specific = {"tailwinds": tailwinds, "headwinds": headwinds}
    elif sector_filter:
        sector_perf = next((s for s in sectors if sector_filter.lower() in s["sector"].lower()), None)
        if sector_perf:
            headwinds = []
            tailwinds = []
            if sector_perf.get("1mo") is not None:
                if sector_perf["1mo"] > 2:
                    tailwinds.append(f"Sector up {sector_perf['1mo']:.1f}% (1mo)")
                elif sector_perf["1mo"] < -2:
                    headwinds.append(f"Sector down {sector_perf['1mo']:.1f}% (1mo)")
            if sector_perf.get("above_50sma"):
                tailwinds.append("Trading above 50-day SMA")
            else:
                headwinds.append("Trading below 50-day SMA")
            specific = {"tailwinds": tailwinds, "headwinds": headwinds}

    # Key watch
    watch_items = []
    if rates.get("inverted"):
        watch_items.append("Yield curve inversion — recession risk indicator")
    if vix and vix > 25:
        watch_items.append(f"Elevated VIX at {vix:.1f} — volatility risk")
    watch_items.append("Next FOMC meeting & CPI release")

    return {
        "environment": environment,
        "positioning": positioning,
        "score": score,
        "signals": signals,
        "specific": specific,
        "watch": watch_items[0] if watch_items else "Upcoming FOMC decision",
    }


# ── Formatters ─────────────────────────────────────────────────────────────────

def format_markdown(rates, market, sectors, risk, sentiment, econ, verdict, ticker_ctx=None, sector_filter=None, bond_signals=None):
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# 📊 Macro Market Scanner")
    lines.append(f"*Generated: {now}*\n")

    if ticker_ctx:
        lines.append(f"**Context:** {ticker_ctx.get('name', '')} ({ticker_ctx.get('sector', '')}) | Beta: {ticker_ctx.get('beta', 'N/A')} | P/E: {ticker_ctx.get('pe', 'N/A')}\n")
    if sector_filter:
        lines.append(f"**Sector Focus:** {sector_filter}\n")

    # Step 1 — Rates
    lines.append("## 1. Federal Reserve & Interest Rates")
    lines.append(f"- **Fed Funds Rate:** {rates['fed_funds']}")
    lines.append(f"- **10-Year Treasury:** {fmt(rates['ten_year'], '%') if rates['ten_year'] else 'N/A'}")
    lines.append(f"- **2-Year Treasury:** {fmt(rates['two_year'], '%') if rates['two_year'] else 'N/A'}")
    if rates["yield_spread"] is not None:
        status = "⚠️ INVERTED" if rates["inverted"] else "Normal"
        lines.append(f"- **Yield Curve (10Y-2Y):** {rates['yield_spread']:.3f}% — {status}")
    lines.append("")

    # Step 2 — Market Overview
    lines.append("## 2. Market Overview")
    lines.append("| Index | Price | YTD | 1-Month | 3-Month |")
    lines.append("|-------|------:|----:|--------:|--------:|")
    for name in ["S&P 500", "Nasdaq", "Dow Jones", "Russell 2000"]:
        d = market.get(name, {})
        lines.append(f"| {name} | {d.get('price', 'N/A'):,} | {fmt(d.get('ytd'))} | {fmt(d.get('1mo'))} | {fmt(d.get('3mo'))} |")
    vix = market.get("VIX", {})
    lines.append(f"\n**VIX:** {vix.get('level', 'N/A')} — {vix.get('classification', 'N/A')} (1mo: {fmt(vix.get('1mo_change'))})")
    lines.append("")

    # Step 3 — Sectors
    lines.append("## 3. Sector Performance (ranked by 1-month)")
    lines.append("| # | Sector | ETF | 1-Month | 3-Month |")
    lines.append("|---|--------|-----|--------:|--------:|")
    for i, s in enumerate(sectors, 1):
        marker = ""
        if sector_filter and sector_filter.lower() in s["sector"].lower():
            marker = " 👈"
        if ticker_ctx and ticker_ctx.get("sector") and YFINANCE_SECTOR_MAP.get(ticker_ctx["sector"], ticker_ctx["sector"]) == s["sector"]:
            marker = " 👈"
        lines.append(f"| {i} | {s['sector']}{marker} | {s['etf']} | {fmt(s.get('1mo'))} | {fmt(s.get('3mo'))} |")

    top3 = [s["sector"] for s in sectors[:3] if s.get("1mo") is not None]
    bot3 = [s["sector"] for s in sectors[-3:] if s.get("1mo") is not None]
    lines.append(f"\n🟢 **Leading:** {', '.join(top3)}")
    lines.append(f"🔴 **Lagging:** {', '.join(bot3)}")
    lines.append("")

    # Step 4 — Breadth
    lines.append("## 4. Market Breadth")
    above50 = sum(1 for s in sectors if s.get("above_50sma"))
    above200 = sum(1 for s in sectors if s.get("above_200sma"))
    total = sum(1 for s in sectors if s.get("above_50sma") is not None)
    if total:
        pct50 = above50 / total * 100
        pct200 = above200 / total * 100
        lines.append(f"- **Above 50-day SMA:** {above50}/{total} sectors ({pct50:.0f}%)")
        lines.append(f"- **Above 200-day SMA:** {above200}/{total} sectors ({pct200:.0f}%)")
        if pct50 >= 70:
            lines.append("- **Assessment:** Broad-based rally ✅")
        elif pct50 >= 40:
            lines.append("- **Assessment:** Mixed breadth — selective participation")
        else:
            lines.append("- **Assessment:** Narrow/concentrated rally ⚠️")
    lines.append("")

    # Step 5 — Risk
    lines.append("## 5. Risk Indicators")
    for label in ["Gold (GLD)", "US Dollar (UUP)", "Bitcoin"]:
        d = risk.get(label, {})
        lines.append(f"- **{label}:** ${d.get('price', 'N/A'):,} (1mo: {fmt(d.get('1mo'))})")
    yc = risk.get("yield_curve", {})
    if yc.get("inverted"):
        lines.append("- **Yield Curve:** ⚠️ Inverted — historical recession signal")
    elif yc.get("spread") is not None:
        lines.append(f"- **Yield Curve:** Normal ({yc['spread']:.3f}% spread)")
    lines.append("")

    # Step 6 — Consumer & Market Sentiment
    lines.append("## 6. Consumer & Market Sentiment")
    michigan = sentiment.get("michigan", {})
    if michigan:
        mom = f" (MoM: {michigan['mom_change']:+.1f})" if michigan.get('mom_change') is not None else ""
        yoy = f" | Year ago: {michigan['year_ago']:.1f}" if michigan.get('year_ago') else ""
        lines.append(f"- **Michigan Consumer Sentiment:** {michigan.get('current', 'N/A')} — {michigan.get('assessment', 'N/A')}{mom}")
        lines.append(f"  - Date: {michigan.get('date', 'N/A')} | Percentile: {michigan.get('percentile', 'N/A')}th{yoy}")
    fg = sentiment.get("fear_greed", {})
    if fg:
        hist = ""
        if fg.get("1w_ago"):
            hist += f" | 1W ago: {fg['1w_ago']}"
        if fg.get("1m_ago"):
            hist += f" | 1M ago: {fg['1m_ago']}"
        lines.append(f"- **CNN Fear & Greed:** {fg.get('score', 'N/A')} — {fg.get('rating', 'N/A').upper()}{hist}")
    sr = sentiment.get("saving_rate", {})
    if sr:
        lines.append(f"- **Personal Saving Rate:** {sr.get('current', 'N/A')}% — {sr.get('assessment', 'N/A')} (as of {sr.get('date', 'N/A')})")
    sp_gold = sentiment.get("sp_gold_ratio", {})
    if sp_gold:
        lines.append(f"- **S&P/Gold Ratio:** {sp_gold.get('current', 'N/A')} ({sp_gold.get('trend', 'N/A')} vs 1mo ago: {sp_gold.get('1mo_ago', 'N/A')})")
    sp_oil = sentiment.get("sp_oil_ratio", {})
    if sp_oil:
        lines.append(f"- **S&P/Oil Ratio:** {sp_oil.get('current', 'N/A')} ({sp_oil.get('trend', 'N/A')} vs 1mo ago: {sp_oil.get('1mo_ago', 'N/A')})")
    if sentiment.get("contrarian_signal"):
        lines.append(f"\n**{sentiment['contrarian_signal']}**")
    lines.append("")

    # Step 7 — Bond Market Signals
    lines.append("## 7. Bond Market Signals")
    if bond_signals:
        yc = bond_signals.get("yield_curve", {})
        cs = bond_signals.get("credit_spreads", {})
        ty = bond_signals.get("ten_year", {})
        scores = bond_signals.get("scores", {})
        if yc:
            lines.append(f"- **Yield Curve (10Y-2Y):** {yc.get('spread', 'N/A')}% — {yc.get('assessment', 'N/A')} (1mo Δ: {yc.get('spread_change', 'N/A')}%)")
        if cs:
            lines.append(f"- **HY Credit Spreads:** {cs.get('current_bps', 'N/A')}bps — {cs.get('assessment', 'N/A')} (1mo Δ: {cs.get('change', 'N/A')}%)")
        if ty:
            lines.append(f"- **10Y Treasury:** {ty.get('current', 'N/A')}% — {ty.get('assessment', 'N/A')} (1mo Δ: {ty.get('change_bps', 'N/A')}bps)")
        combined = bond_signals.get("combined_score", 0)
        emoji = "🟢" if combined >= 2 else "🔴" if combined <= -2 else "🟡"
        lines.append(f"\n**{emoji} Combined Bond Score: {combined:+d}** (range: -3 to +3)")
        score_details = ", ".join(f"{k}: {v:+d}" for k, v in scores.items())
        if score_details:
            lines.append(f"  Components: {score_details}")
    else:
        lines.append("- Bond data unavailable")
    lines.append("")

    # Step 8 — Economic
    lines.append("## 8. Economic Data & News")
    for name, url in econ.get("links", {}).items():
        lines.append(f"- [{name}]({url})")
    if econ.get("headlines"):
        lines.append("\n**Recent Headlines:**")
        for h in econ["headlines"]:
            lines.append(f"- {h['title']}")
    lines.append("")

    # Step 9 — Verdict
    lines.append("## 9. Strategic Verdict")
    lines.append(f"| Environment | Positioning | Key Watch |")
    lines.append(f"|-------------|-------------|-----------|")
    lines.append(f"| **{verdict['environment']}** | **{verdict['positioning']}** | {verdict['watch']} |")
    if verdict.get("specific"):
        sp = verdict["specific"]
        if sp.get("tailwinds"):
            lines.append(f"\n🟢 **Tailwinds:** {'; '.join(sp['tailwinds'])}")
        if sp.get("headwinds"):
            lines.append(f"🔴 **Headwinds:** {'; '.join(sp['headwinds'])}")
    lines.append("")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Macro Market Scanner")
    parser.add_argument("--ticker", "-t", help="Stock ticker for context (e.g., TSLA)")
    parser.add_argument("--sector", "-s", help="Sector name for focus (e.g., Technology)")
    parser.add_argument("--json", "-j", action="store_true", dest="json_output", help="Output as JSON")
    args = parser.parse_args()

    ticker_ctx = None
    if args.ticker:
        print(f"Fetching context for {args.ticker}...", file=sys.stderr)
        ticker_ctx = get_ticker_context(args.ticker)

    print("Fetching interest rates...", file=sys.stderr)
    rates = get_rates()

    print("Fetching market overview...", file=sys.stderr)
    market = get_market_overview()

    print("Fetching sector performance...", file=sys.stderr)
    sectors = get_sector_performance()

    print("Fetching risk indicators...", file=sys.stderr)
    risk = get_risk_indicators(rates, market)

    print("Fetching consumer & market sentiment...", file=sys.stderr)
    sentiment = get_consumer_sentiment()

    print("Fetching bond market signals...", file=sys.stderr)
    bond_signals = get_bond_signals()

    print("Fetching economic context...", file=sys.stderr)
    econ = get_economic_context()

    print("Computing verdict...", file=sys.stderr)
    verdict = compute_verdict(rates, market, sectors, risk, ticker_ctx, args.sector, sentiment, bond_signals)

    if args.json_output:
        output = {
            "timestamp": datetime.now().isoformat(),
            "context": {"ticker": args.ticker, "sector": args.sector, "ticker_info": ticker_ctx},
            "rates": rates,
            "market": market,
            "sectors": sectors,
            "risk": risk,
            "sentiment": sentiment,
            "bond_signals": bond_signals,
            "economic": econ,
            "verdict": verdict,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(format_markdown(rates, market, sectors, risk, sentiment, econ, verdict, ticker_ctx, args.sector, bond_signals))


if __name__ == "__main__":
    main()
