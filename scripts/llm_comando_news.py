#!/usr/bin/env python3
"""Shared news utilities for LLM-Comando (cycles, watcher, radar).

Goals:
  - Cursor-based "what's NEW since last poll" (not only 24h volume dump)
  - Recency-weighted discovery for scheduled cycles
  - Shared daily fire budget for event-driven LLM calls
"""
from __future__ import annotations

import datetime
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path.home() / "bigclaw-ai" / "data"
RADAR_STATE = DATA / "llm_comando_radar_state.json"
FIRE_BUDGET = DATA / "llm_comando_event_fires.json"

# Keep in sync with llm_comando.ETF_BLACKLIST intent (single-stock experiment)
ETF_BLACKLIST = {
    "SPY", "QQQ", "DIA", "VOO", "VTI", "VEA", "VWO",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "XLB", "XLU", "XLRE", "XLC",
    "SOXX", "SMH", "KRE", "IGV", "XHB", "ITB", "XME", "XOP", "XBI", "IBB",
    "ARKK", "ARKW", "ARKQ", "ARKG", "ARKF", "ARKX", "VNQ", "VYM", "VTV", "VUG",
    "IWM", "IWN", "IWO", "IWP", "IWB", "IWS", "IWD", "IWF",
    "MTUM", "QUAL", "USMV", "VLUE", "SIZE", "SPLV",
    "TLT", "IEF", "SHY", "BND", "AGG", "LQD", "HYG", "JNK",
    "UUP", "GLD", "SLV", "USO", "BNO", "UNG",
    "SH", "PSQ", "DOG", "RWM", "ITA", "PPA", "EWC",
}

MAX_EVENT_FIRES_PER_DAY = 10  # radar + watcher focused LLM calls combined


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_iso(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return default


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n")
    tmp.replace(path)


def is_stock_symbol(sym: str) -> bool:
    if not sym or not isinstance(sym, str):
        return False
    s = sym.upper().strip()
    if s in ETF_BLACKLIST:
        return False
    if not (1 < len(s) <= 5 and s.isalpha()):
        return False
    return True


def fetch_alpaca_news(secrets, start: datetime.datetime, limit_pages=4, symbols=None):
    """Return list of dicts: {time, headline, summary, symbols, source, id}."""
    from alpaca.data.historical.news import NewsClient
    from alpaca.data.requests import NewsRequest

    client = NewsClient(
        api_key=secrets["ALPACA_API_KEY"],
        secret_key=secrets["ALPACA_SECRET_KEY"],
    )
    items = []
    next_token = None
    for _ in range(limit_pages):
        kwargs = {"start": start, "limit": 50}
        if symbols:
            kwargs["symbols"] = ",".join(symbols[:50])
        req = NewsRequest(**kwargs)
        if next_token:
            req.page_token = next_token
        r = client.get_news(req)
        batch = []
        if hasattr(r, "data") and isinstance(r.data, dict):
            for v in r.data.values():
                batch.extend(v if isinstance(v, list) else [v])
        for item in batch:
            created = getattr(item, "created_at", None)
            iso = created.isoformat() if created is not None else ""
            items.append(
                {
                    "time": iso[:19] if iso else "",
                    "headline": getattr(item, "headline", "") or "",
                    "summary": (getattr(item, "summary", None) or "")[:500],
                    "symbols": [
                        s.upper()
                        for s in (getattr(item, "symbols", None) or [])
                        if is_stock_symbol(s)
                    ],
                    "source": getattr(item, "source", None) or "alpaca",
                    "id": str(getattr(item, "id", "") or iso + (getattr(item, "headline", "") or "")[:40]),
                }
            )
        next_token = getattr(r, "next_page_token", None)
        if not next_token:
            break
    return items


def fetch_rss_headlines(max_per_feed=12):
    """CNBC + Reuters-via-Google — lightweight, no cursor (dedupe by headline)."""
    import feedparser
    import urllib.parse

    out = []
    feeds = [
        ("CNBC Top", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("CNBC Markets", "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ]
    for name, url in feeds:
        try:
            f = feedparser.parse(url)
            for e in f.entries[:max_per_feed]:
                out.append(
                    {
                        "time": "",
                        "headline": e.get("title", ""),
                        "summary": (e.get("summary", "") or "")[:300],
                        "symbols": [],
                        "source": name,
                        "id": f"rss:{name}:{e.get('title', '')[:60]}",
                    }
                )
        except Exception:
            pass
    for q in ["site:reuters.com markets", "site:reuters.com business"]:
        try:
            url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=en-US&gl=US"
            f = feedparser.parse(url)
            for e in f.entries[:8]:
                out.append(
                    {
                        "time": "",
                        "headline": e.get("title", ""),
                        "summary": "",
                        "symbols": [],
                        "source": "Reuters/GN",
                        "id": f"rss:reu:{e.get('title', '')[:60]}",
                    }
                )
        except Exception:
            pass
    return out


def recency_weight(item_time_iso: str, now=None) -> float:
    """Higher weight for fresher headlines. Full weight <1h, half by ~6h, low by 24h."""
    now = now or _now_utc()
    dt = _parse_iso(item_time_iso)
    if not dt:
        return 0.35  # unknown age (RSS) — modest weight
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    hours = max(0.0, (now - dt).total_seconds() / 3600.0)
    # exponential decay: half-life ~4 hours
    return math.exp(-0.693 * hours / 4.0)


def rank_tickers_by_news(items, top_n=30, now=None):
    """Recency-weighted ticker ranking from news items with symbols."""
    now = now or _now_utc()
    scores = Counter()
    raw_counts = Counter()
    latest = {}
    headlines = defaultdict(list)
    for it in items:
        w = recency_weight(it.get("time") or "", now=now)
        for sym in it.get("symbols") or []:
            if not is_stock_symbol(sym):
                continue
            scores[sym] += w
            raw_counts[sym] += 1
            t = it.get("time") or ""
            if sym not in latest or t > latest[sym]:
                latest[sym] = t
            if len(headlines[sym]) < 3:
                headlines[sym].append(
                    {
                        "time": t,
                        "headline": it.get("headline", ""),
                        "source": it.get("source", ""),
                    }
                )
    ranked = scores.most_common(top_n)
    detail = []
    for sym, sc in ranked:
        detail.append(
            {
                "ticker": sym,
                "score": round(sc, 3),
                "mentions": raw_counts[sym],
                "latest": latest.get(sym, ""),
                "headlines": headlines.get(sym, []),
            }
        )
    return detail


def discover_news_makers_weighted(secrets, top_n=30, hours_back=24):
    """Drop-in upgrade for cycle discovery: recency-weighted, not raw 24h counts."""
    start = _now_utc() - datetime.timedelta(hours=hours_back)
    try:
        items = fetch_alpaca_news(secrets, start=start, limit_pages=5)
    except Exception as e:
        return [], str(e)
    detail = rank_tickers_by_news(items, top_n=top_n)
    # Compatible shape: dict ticker -> approx count (use mentions for logs)
    counts = {d["ticker"]: d["mentions"] for d in detail}
    return counts, detail, len(items)


def load_radar_state():
    return load_json(
        RADAR_STATE,
        {
            "cursor_iso": None,
            "seen_ids": [],
            "last_run": None,
        },
    )


def save_radar_state(state):
    # cap seen_ids
    ids = state.get("seen_ids") or []
    if len(ids) > 2000:
        state["seen_ids"] = ids[-1500:]
    save_json(RADAR_STATE, state)


def filter_new_items(items, state):
    seen = set(state.get("seen_ids") or [])
    fresh = []
    for it in items:
        iid = it.get("id") or (it.get("time", "") + it.get("headline", "")[:80])
        if iid in seen:
            continue
        seen.add(iid)
        it = dict(it)
        it["id"] = iid
        fresh.append(it)
    state["seen_ids"] = list(seen)[-2000:]
    return fresh, state


def event_fire_budget(max_fires=MAX_EVENT_FIRES_PER_DAY):
    """Return (remaining, state_dict). Resets each calendar day UTC."""
    today = _now_utc().strftime("%Y-%m-%d")
    st = load_json(FIRE_BUDGET, {"date": today, "fires": 0, "events": []})
    if st.get("date") != today:
        st = {"date": today, "fires": 0, "events": []}
    used = int(st.get("fires") or 0)
    return max(0, max_fires - used), st


def record_event_fire(st, kind, detail=""):
    st["fires"] = int(st.get("fires") or 0) + 1
    st.setdefault("events", []).append(
        {
            "ts": _now_utc().isoformat(),
            "kind": kind,
            "detail": detail[:200],
        }
    )
    st["events"] = st["events"][-50:]
    save_json(FIRE_BUDGET, st)


def upcoming_events_block(held_tickers, watch_tickers=None, days_ahead=5):
    """Lightweight earnings + known FOMC window for context."""
    lines = ["## EVENT CALENDAR (next days — study before print when possible)"]
    tickers = list(dict.fromkeys((held_tickers or []) + (watch_tickers or [])))[:25]
    try:
        import yfinance as yf

        today = datetime.date.today()
        end = today + datetime.timedelta(days=days_ahead)
        found = 0
        for t in tickers:
            try:
                cal = yf.Ticker(t).calendar
                ed = None
                if isinstance(cal, dict):
                    raw = cal.get("Earnings Date")
                    if isinstance(raw, list) and raw:
                        ed = raw[0]
                    elif raw:
                        ed = raw
                if ed is None:
                    continue
                if hasattr(ed, "date"):
                    d = ed.date() if callable(getattr(ed, "date", None)) else ed
                    if hasattr(d, "year"):
                        pass
                    else:
                        d = ed
                else:
                    d = datetime.date.fromisoformat(str(ed)[:10])
                if isinstance(d, datetime.datetime):
                    d = d.date()
                if today <= d <= end:
                    lines.append(f"  - {t}: earnings ~ {d.isoformat()}")
                    found += 1
            except Exception:
                continue
        if found == 0:
            lines.append("  - No holdings/watch earnings in next {}d (or calendar unavailable)".format(days_ahead))
    except Exception as e:
        lines.append(f"  - earnings calendar unavailable: {e}")

    # FOMC proximity (hardcoded 2026 dates from economic_calendar.py)
    fomc = [
        "2026-07-28",
        "2026-07-29",
        "2026-09-15",
        "2026-09-16",
        "2026-11-03",
        "2026-11-04",
        "2026-12-15",
        "2026-12-16",
    ]
    today_s = datetime.date.today().isoformat()
    near = [d for d in fomc if today_s <= d <= (datetime.date.today() + datetime.timedelta(days=days_ahead)).isoformat()]
    if near:
        lines.append("  - FOMC window approaching: " + ", ".join(near))
    return "\n".join(lines)


def group_fresh_by_ticker(fresh_items):
    """ticker -> list of news dicts (newest first)."""
    by = defaultdict(list)
    for it in fresh_items:
        for sym in it.get("symbols") or []:
            if is_stock_symbol(sym):
                by[sym].append(it)
    for sym in by:
        by[sym].sort(key=lambda x: x.get("time") or "", reverse=True)
    return by
