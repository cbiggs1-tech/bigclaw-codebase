#!/usr/bin/env python3
"""
LLM-Commando event-driven radar.

Poll frequently during RTH. When NEW news arrives on holdings or strong
single-stock names, run a focused Judge-style decision WITHOUT waiting for
09:00 / 11:30 / 14:30 sessions.

Also: multi-day loss with NO news is itself the news ("price_is_news").
If a holding is weak while the broad market and its sector are NOT down,
wake research and default to selling HALF the position. Market/sector
weakness alone is not a sell reason. Residual half keeps normal trailing stops.

Usage:
  source ~/.env_secrets
  python3 llm_comando_radar.py --dry-run
  python3 llm_comando_radar.py
  python3 llm_comando_radar.py --max-events 3
  python3 llm_comando_radar.py --force-fade-scan   # ignore 15m fade throttle

Cron (suggested): */2 8-15 * * 1-5  (CT market hours)
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

import warnings

warnings.filterwarnings("ignore")

import anthropic
import yfinance as yf

try:
    from slack_sdk import WebClient
except ImportError:
    WebClient = None

sys.path.insert(0, str(Path.home() / "bigclaw-ai" / "scripts"))
import llm_comando_news as newsutil

PORTFOLIO_NAME = "LLM-Commando"
DEFAULT_CHANNEL = "D0ADHLUJ400"
MODEL = "claude-sonnet-4-6"  # fast path; full dialectic stays on scheduled cycles
MAX_TOKENS = 4000
LLM_TIMEOUT = 90.0
LOCK_FILE = Path("/tmp/llm_comando.lock")  # shared with deliberative cycle
RADAR_LOCK = Path("/tmp/llm_comando_radar.lock")
DB_PATH = Path.home() / "bigclaw-ai" / "src" / "portfolios.db"
JOURNAL = Path.home() / "bigclaw-ai" / "data" / "llm_comando_journal.jsonl"
LOG_DIR = Path.home() / "bigclaw-ai" / "logs"
LLM_LOG = LOG_DIR / "llm_calls.jsonl"
RADAR_LOG = LOG_DIR / "llm_comando_radar.log"

# --- price_is_news (holdings fade) thresholds ---
# Multi-day stock loss + market/sector NOT down (session) → research → sell HALF.
# Market or sector weakness alone is never a sell reason (trailing stops handle beta).
FADE_MIN_LOWER_CLOSES = 2          # consecutive lower daily closes
FADE_MIN_STOCK_RET_3D = -0.8       # or 3d return at/under this (%)
FADE_MARKET_DOWN_1D = -0.5         # SPY session ret below this = market down → no trip
FADE_SECTOR_DOWN_1D = -0.5         # sector ETF session ret below this → no trip for that name
FADE_RELATIVE_LAG_3D = 0.5         # stock must lag sector by >= this many pp over 3d when both known
FADE_SCAN_INTERVAL_MIN = 15        # don't hammer yfinance every 2m poll
FADE_COOLDOWN_HOURS = 20           # one price_is_news fire per name per ~day
SECTOR_CACHE_DAYS = 30

SECTOR_TO_ETF = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Financials": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP",
    "Consumer Cyclical": "XLY",
    "Consumer Discretionary": "XLY",
    "Basic Materials": "XLB",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

GO_SYSTEM = """You are the LLM-Commando decision agent on an EVENT-DRIVEN path.
New market information just arrived. You must decide NOW — do not wait for a scheduled session.

NORTH STAR:
- Figure out how to win THIS session from today's narrative.
- Study the stock(s) below; weigh bull and bear angles briefly; decide.
- Day-trader speed with investor sense: real thesis + falsifiers, or stand down.
- SELL when a holding's buy thesis is breaking on this news.
- Multi-day loss with no news IS news (event kind price_is_news). That path default is SELL HALF.
- Journal history is analogy only — yesterday's failure may win today.
- Individual stocks only — never ETFs.
- REAL > THEATER: earnings / formal guidance / signed deals beat threatened tariffs. Only ENACTED
  (in-force) policy can veto a real print — not "threatens/considering/could impose" headlines.
- NO CHASE: stand_down if the catalyst is a rehash of a prior-session event and the stock already
  ran hard over 1–3 days with no NEW incremental fact. Prefer early action on the real print;
  do not buy day-2 continuation after the run-up.
- COLD EDGE (not passivity): constraints kill FOMO/threat-fear, not aggression. Humans chase late
  and freeze on real prints next to scary headlines — act early on REAL facts; stand down when late/crowded.

ANTI-CHEATING: Training cutoff Jan 2026. Cite ONLY the data provided. No invented events.

OUTPUT — STRICT JSON ONLY:
{
  "market_narrative": "1-2 sentences: what is the tape story right now",
  "decisions": [
    {
      "ticker": "XYZ",
      "action": "buy" | "sell" | "stand_down",
      "shares": 0,
      "rationale": "data-cited thesis or why stand down",
      "thesis_fit_today": "how this fits or fades today's narrative",
      "falsifiers": "what would break this thesis",
      "exit_thesis": "for buys: when thesis is done",
      "exit_conditions": {"target_pct": 3.0, "stop_pct": 2.0, "time_exit_date": "YYYY-MM-DD"},
      "confidence": 0.0,
      "exit_classification": null
    }
  ],
  "patterns_noted": "optional short note"
}

Rules:
- For sells: shares must not exceed held shares shown.
- For buys: size modestly (prefer <=12% of portfolio); cash limit is hard.
- Prefer stand_down over chasing a name already extended on this headline if the move looks spent.
- If the packet shows large 1d/3d gains and the headline is only restating yesterday's earnings
  (no new PT cluster, no new guidance increment), action must be stand_down — that is a chase.
- Tariff/political lines: if wording is threat/theater, ignore for veto; if enacted/in-force with
  evidence, it may justify stand_down even on a beat.
- If news only affects a holding's thesis, sell/hold that name; do not force a new buy.
- exit_classification for sells: thesis_wrong | thesis_changed | thesis_played_out

price_is_news (CRITICAL):
- Trigger means: multi-day stock weakness WHILE SPY and sector ETF are NOT down on the session
  (and stock is lagging its sector over multi-day). Market/sector weakness alone is never a
  sell reason and would not have fired this event.
- Research the WHY_BOUGHT thesis vs multi-day price action in the packet.
- Default action: SELL with shares = half_shares shown (50% cut). Residual keeps trailing stops.
- stand_down only if the packet gives a concrete non-tape reason the thesis still holds
  (e.g. explicit long-horizon catalyst still intact with confirming data present). "No news"
  is NOT a reason to stand down — that is why you were woken.
- Do not invent a market/sector crash excuse. Do not full-exit on this path (system clamps to half).
"""


def log(msg, level="INFO"):
    line = f"[{datetime.datetime.now(datetime.timezone.utc).isoformat()}] {level} {msg}"
    print(line, flush=True)
    try:
        RADAR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(RADAR_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_secrets():
    s = {}
    for line in (Path.home() / ".env_secrets").read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            s[k.strip()] = v.strip().strip('"').strip("'")
    return s


def acquire_lock(path: Path, stale_sec=900):
    if path.exists():
        try:
            age = time.time() - path.stat().st_mtime
            pid = int(path.read_text().strip())
            try:
                os.kill(pid, 0)
                if age < stale_sec:
                    return False
            except ProcessLookupError:
                pass
        except Exception:
            pass
    path.write_text(str(os.getpid()))
    return True


def release_lock(path: Path):
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def get_portfolio():
    import sqlite3

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    p = conn.execute(
        "SELECT id, name, current_cash, starting_cash FROM portfolios WHERE name=? AND is_active=1",
        (PORTFOLIO_NAME,),
    ).fetchone()
    if not p:
        conn.close()
        raise RuntimeError("Commando portfolio not found/active")
    holdings = [
        dict(r)
        for r in conn.execute(
            "SELECT ticker, shares, avg_cost, rationale, target_price FROM holdings WHERE portfolio_id=? AND shares>0",
            (p["id"],),
        )
    ]
    conn.close()
    return dict(p), holdings


def journal_tail(n=5):
    if not JOURNAL.exists():
        return []
    lines = JOURNAL.read_text().splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def _series_close(hist, t):
    """Extract a 1-d close series for ticker t from a yf download frame."""
    if hist is None or len(hist) == 0:
        return None
    try:
        if hasattr(hist, "columns"):
            # MultiIndex (field, ticker) or flat columns
            if isinstance(hist.columns, type(hist.columns)) and hasattr(hist.columns, "levels"):
                pass
            if t in hist.columns:
                s = hist[t].dropna()
            else:
                # single-ticker download flattens
                s = hist.dropna()
                if hasattr(s, "columns"):
                    return None
        else:
            s = hist.dropna()
        if hasattr(s, "empty") and s.empty:
            return None
        return s
    except Exception:
        return None


def consecutive_lower_closes(s) -> int:
    if s is None or len(s) < 2:
        return 0
    n = 0
    for i in range(len(s) - 1, 0, -1):
        try:
            if float(s.iloc[i]) < float(s.iloc[i - 1]):
                n += 1
            else:
                break
        except Exception:
            break
    return n


def load_price_stats(tickers, period="10d"):
    """Close stats: price, ret_1d, ret_3d, ret_5d, lower_closes streak."""
    out = {}
    tickers = list(dict.fromkeys([t.upper() for t in tickers if t]))
    if not tickers:
        return out
    try:
        raw = yf.download(tickers, period=period, progress=False, threads=True, auto_adjust=True)
        if raw is None or raw.empty:
            return out
        close = raw["Close"] if "Close" in raw.columns or (
            hasattr(raw.columns, "levels") and "Close" in getattr(raw.columns, "levels", [[]])[0]
        ) else raw
        # MultiIndex columns: (Price, Ticker)
        if hasattr(close, "columns") and getattr(close.columns, "nlevels", 1) > 1:
            try:
                close = raw["Close"]
            except Exception:
                pass
        for t in tickers:
            try:
                if hasattr(close, "columns") and t in close.columns:
                    s = close[t].dropna()
                elif hasattr(close, "columns") and len(tickers) == 1:
                    s = close.iloc[:, 0].dropna() if close.shape[1] >= 1 else close.dropna()
                else:
                    # single series
                    s = close.dropna() if len(tickers) == 1 else None
                if s is None or len(s) < 1:
                    continue
                px = float(s.iloc[-1])
                def ret_n(n):
                    if len(s) <= n:
                        return None
                    base = float(s.iloc[-(n + 1)])
                    if base == 0:
                        return None
                    return (px / base - 1.0) * 100.0
                out[t] = {
                    "price": px,
                    "ret_1d": ret_n(1) if len(s) >= 2 else 0.0,
                    "ret_3d": ret_n(3),
                    "ret_5d": ret_n(5),
                    "lower_closes": consecutive_lower_closes(s),
                    "n_bars": int(len(s)),
                }
            except Exception:
                pass
    except Exception as e:
        log(f"price stats fetch: {e}", "WARN")
    return out


def quick_prices(tickers):
    """Backward-compatible thin wrapper (1d + price)."""
    stats = load_price_stats(tickers, period="5d")
    return {t: {"price": v["price"], "ret_1d": v.get("ret_1d")} for t, v in stats.items()}


def resolve_sectors(tickers, rstate, now):
    """Map tickers → sector ETF; cache on radar state."""
    cache = dict(rstate.get("sector_cache") or {})
    out = {}
    need = []
    for t in tickers:
        t = t.upper()
        c = cache.get(t) or {}
        etf = c.get("etf")
        ts = newsutil._parse_iso(c.get("ts"))
        fresh = ts and (now - ts).days < SECTOR_CACHE_DAYS
        if etf and fresh:
            out[t] = etf
        else:
            need.append(t)
    for t in need:
        etf, sec = "SPY", "unknown"
        try:
            info = yf.Ticker(t).info or {}
            sec = info.get("sector") or info.get("category") or "unknown"
            etf = SECTOR_TO_ETF.get(sec, "SPY")
            log(f"  sector map {t} -> {sec} / {etf}")
        except Exception as e:
            log(f"  sector map {t} failed: {e}", "WARN")
        cache[t] = {"etf": etf, "sector": sec, "ts": now.isoformat()}
        out[t] = etf
    rstate["sector_cache"] = cache
    return out


def detect_holdings_fade(holdings, prices, sector_map, rstate, now):
    """
    price_is_news trip:
      multi-day stock loss (lower closes / 3d) while market and sector are NOT
      down on the session (1d). Optional: stock must lag sector over 3d.
    Market or sector weakness alone is never a sell reason (stops handle beta).
    """
    events = []
    spy = prices.get("SPY") or {}
    spy_1d = spy.get("ret_1d")
    spy_3d = spy.get("ret_3d")
    if spy_1d is None and spy_3d is None:
        log("  fade scan: no SPY rets — skip", "WARN")
        return events

    # Session market down → do not hunt thesis fades (beta day)
    if spy_1d is not None and spy_1d < FADE_MARKET_DOWN_1D:
        log(f"  fade scan: SPY 1d {spy_1d:+.2f}% market down — no price_is_news trips")
        return events

    last_fire = dict(rstate.get("fade_last_fire") or {})

    for h in holdings:
        t = (h.get("ticker") or "").upper()
        if not t:
            continue
        held_sh = int(float(h.get("shares") or 0))
        if held_sh < 2:
            # half of 1 is awkward; leave to trailing stop / full session
            continue

        prev = newsutil._parse_iso(last_fire.get(t))
        if prev and (now - prev).total_seconds() < FADE_COOLDOWN_HOURS * 3600:
            continue

        p = prices.get(t) or {}
        stock_ret = p.get("ret_3d")
        stock_1d = p.get("ret_1d")
        lower = int(p.get("lower_closes") or 0)
        multi_day_loss = (lower >= FADE_MIN_LOWER_CLOSES) or (
            stock_ret is not None and stock_ret <= FADE_MIN_STOCK_RET_3D
        )
        if not multi_day_loss:
            continue
        # Must actually be red over the window we care about
        if stock_ret is not None and stock_ret >= 0 and lower < FADE_MIN_LOWER_CLOSES:
            continue

        sec_etf = (sector_map.get(t) or "SPY").upper()
        sec = prices.get(sec_etf) or {}
        sec_1d = sec.get("ret_1d")
        sec_3d = sec.get("ret_3d")

        # Sector down today → not a sell reason for this name
        if sec_1d is not None and sec_1d < FADE_SECTOR_DOWN_1D:
            sr_s = f"{stock_ret:+.2f}%" if stock_ret is not None else "?"
            log(
                f"  fade skip {t}: sector {sec_etf} 1d {sec_1d:+.2f}% down "
                f"(stock 3d {sr_s} — sector weakness not a sell reason)"
            )
            continue

        # Relative: stock lagging its sector over multi-day (when both known)
        if stock_ret is not None and sec_3d is not None:
            lag = sec_3d - stock_ret  # positive = stock lagging sector
            if lag < FADE_RELATIVE_LAG_3D:
                log(
                    f"  fade skip {t}: not lagging sector enough "
                    f"(stock 3d {stock_ret:+.2f}% vs {sec_etf} 3d {sec_3d:+.2f}%, lag={lag:.2f}pp)"
                )
                continue

        half = max(1, held_sh // 2)
        thesis = (h.get("rationale") or "")[:220]
        sr = f"{stock_ret:+.2f}%" if stock_ret is not None else "?"
        s1 = f"{stock_1d:+.2f}%" if stock_1d is not None else "?"
        secr1 = f"{sec_1d:+.2f}%" if sec_1d is not None else "?"
        secr3 = f"{sec_3d:+.2f}%" if sec_3d is not None else "?"
        spy1 = f"{spy_1d:+.2f}%" if spy_1d is not None else "?"
        spy3 = f"{spy_3d:+.2f}%" if spy_3d is not None else "?"
        summary = (
            f"price_is_news: {t} multi-day weakness while market/sector session NOT down. "
            f"lower_closes={lower} stock 1d={s1} 3d={sr}; SPY 1d={spy1} 3d={spy3}; "
            f"sector={sec_etf} 1d={secr1} 3d={secr3}. "
            f"WHY_BOUGHT: {thesis}. "
            f"DEFAULT: sell HALF = {half} of {held_sh} sh; residual keeps trailing stops. "
            f"Market/sector down days are NOT sell reasons — this only fires when session is not."
        )
        events.append(
            {
                "ticker": t,
                "kind": "price_is_news",
                "items": [
                    {
                        "time": now.isoformat(),
                        "source": "holdings_health",
                        "headline": f"{t} multi-day loss vs flat/up market+sector — thesis drift",
                        "summary": summary,
                    }
                ],
                "priority": -1,
                "fade": {
                    "lower_closes": lower,
                    "ret_1d": stock_1d,
                    "ret_3d": stock_ret,
                    "spy_ret_1d": spy_1d,
                    "spy_ret_3d": spy_3d,
                    "sector_etf": sec_etf,
                    "sector_ret_1d": sec_1d,
                    "sector_ret_3d": sec_3d,
                    "half_shares": half,
                    "held_shares": held_sh,
                },
            }
        )
        log(
            f"  fade TRIP {t}: lower={lower} ret_3d={sr} SPY1d={spy1} "
            f"{sec_etf}1d={secr1} -> half={half}"
        )
    return events


def select_events(by_ticker, holdings, max_events=4):
    """Pick actionable events: holdings first (thesis-break), then new names."""
    held = {h["ticker"].upper() for h in holdings}
    events = []
    # Holdings with any new tagged news
    for t in sorted(held):
        if t in by_ticker and by_ticker[t]:
            events.append(
                {
                    "ticker": t,
                    "kind": "holding_news",
                    "items": by_ticker[t][:4],
                    "priority": 0,
                }
            )
    # New single-stock names with symbols on fresh items
    scored = []
    for t, items in by_ticker.items():
        if t in held:
            continue
        score = sum(newsutil.recency_weight(i.get("time") or "") for i in items)
        scored.append((score, t, items))
    scored.sort(reverse=True)
    for score, t, items in scored[:8]:
        if score < 0.25 and len(items) < 1:
            continue
        events.append(
            {
                "ticker": t,
                "kind": "new_catalyst",
                "items": items[:4],
                "priority": 1,
                "score": round(score, 3),
            }
        )
    events.sort(key=lambda e: e["priority"])
    return events[:max_events]


def merge_events(news_events, fade_events, max_events=4):
    """Fade first; drop fade if same ticker already has holding_news."""
    news_tickers = {e["ticker"].upper() for e in news_events}
    merged = []
    for fe in fade_events:
        if fe["ticker"].upper() in news_tickers:
            log(f"  fade defer {fe['ticker']}: holding_news takes priority")
            continue
        merged.append(fe)
    merged.extend(news_events)
    merged.sort(key=lambda e: e.get("priority", 9))
    return merged[:max_events]


def build_user_message(pf, holdings, events, prices, calendar_block, journal):
    lines = []
    lines.append(f"## TIME (UTC): {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    lines.append(f"## PORTFOLIO {PORTFOLIO_NAME}")
    lines.append(f"  Cash: ${pf['current_cash']:,.2f}  Starting: ${pf['starting_cash']:,.2f}")
    lines.append(f"  Holdings ({len(holdings)}):")
    for h in holdings:
        t = h["ticker"]
        px = prices.get(t, {}).get("price")
        r1 = prices.get(t, {}).get("ret_1d")
        r3 = prices.get(t, {}).get("ret_3d")
        px_s = f"${px:.2f}" if px else "?"
        r_s = f"1d {r1:+.1f}%" if r1 is not None else "1d ?"
        r3_s = f"3d {r3:+.1f}%" if r3 is not None else "3d ?"
        thesis = (h.get("rationale") or "")[:180]
        lines.append(
            f"    {t}: {h['shares']:.0f} sh @ ${h['avg_cost']:.2f}  now {px_s} ({r_s}, {r3_s})  WHY_BOUGHT: {thesis}"
        )
    # Tape context
    for bench in ("SPY", "QQQ"):
        b = prices.get(bench) or {}
        if b.get("price"):
            r1 = b.get("ret_1d")
            r3 = b.get("ret_3d")
            lines.append(
                f"  {bench}: ${b['price']:.2f}  "
                f"1d {r1:+.2f}%  3d {r3:+.2f}%"
                if r1 is not None and r3 is not None
                else f"  {bench}: ${b['price']:.2f}"
            )
    lines.append("")
    lines.append(calendar_block)
    lines.append("")
    lines.append("## NEW EVENTS (act on these — this is why you were woken)")
    for ev in events:
        lines.append(f"\n### {ev['ticker']} [{ev['kind']}]")
        if ev.get("score") is not None:
            lines.append(f"  recency_score={ev['score']}")
        fade = ev.get("fade") or {}
        if fade:
            lines.append(
                f"  half_shares={fade.get('half_shares')} held={fade.get('held_shares')} "
                f"lower_closes={fade.get('lower_closes')} ret_3d={fade.get('ret_3d')} "
                f"SPY_3d={fade.get('spy_ret_3d')} sector={fade.get('sector_etf')} "
                f"sector_3d={fade.get('sector_ret_3d')}"
            )
        for it in ev["items"]:
            lines.append(
                f"  - [{it.get('time','')[:16]}] [{it.get('source','')}] {it.get('headline','')}"
            )
            if it.get("summary"):
                lines.append(f"    {it['summary'][:320]}")
        if ev["ticker"] in prices:
            p = prices[ev["ticker"]]
            r1 = p.get("ret_1d")
            r3 = p.get("ret_3d")
            lines.append(
                f"  price_now=${p['price']:.2f}  day={r1:+.1f}%  3d={r3:+.1f}%"
                if r1 is not None and r3 is not None
                else f"  price_now=${p['price']:.2f}"
            )
    if journal:
        lines.append("\n## JOURNAL TAIL (analogy only)")
        for e in journal[-3:]:
            lines.append(f"  {e.get('date')} trades={len(e.get('trades') or [])} {(e.get('reflection') or '')[:120]}")
    lines.append("\n## TASK")
    lines.append(
        "For each event ticker: buy / sell / stand_down. "
        "Holdings with news: re-verify buy thesis — sell if breaking. "
        "price_is_news: research thesis vs multi-day fade; DEFAULT sell half_shares; "
        "stand_down only with concrete thesis-intact reason (not 'no news'). "
        "New names: only buy if thesis fits TODAY and still has room. Output JSON."
    )
    return "\n".join(lines)


def call_go_agent(secrets, user_msg):
    client = anthropic.Anthropic(api_key=secrets["ANTHROPIC_API_KEY"], timeout=LLM_TIMEOUT)
    t0 = time.time()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=GO_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    dt = time.time() - t0
    text = resp.content[0].text
    in_tok, out_tok = resp.usage.input_tokens, resp.usage.output_tokens
    cost = (in_tok * 3.0 + out_tok * 15.0) / 1_000_000
    try:
        LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LLM_LOG, "a") as f:
            f.write(
                json.dumps(
                    {
                        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "agent": "comando_radar_go",
                        "model": MODEL,
                        "in": in_tok,
                        "out": out_tok,
                        "cost": cost,
                        "sec": round(dt, 1),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    log(f"GO agent: in={in_tok} out={out_tok} cost=${cost:.4f} t={dt:.1f}s")
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"No JSON: {text[:300]}")
    return json.loads(m.group(0)), cost, text


def decisions_to_trades(decisions, holdings, events=None):
    held_qty = {h["ticker"].upper(): float(h["shares"]) for h in holdings}
    fade_by_t = {
        e["ticker"].upper(): e
        for e in (events or [])
        if e.get("kind") == "price_is_news" and e.get("fade")
    }
    trades = []
    for d in decisions or []:
        action = (d.get("action") or "stand_down").lower()
        ticker = (d.get("ticker") or "").upper()
        if action == "stand_down" or not ticker:
            continue
        shares = int(d.get("shares") or 0)
        thesis_type = "radar_event"
        exit_class = d.get("exit_classification")
        if action == "sell":
            max_sh = int(held_qty.get(ticker, 0))
            if max_sh <= 0:
                continue
            if ticker in fade_by_t:
                # price_is_news: always half, never full on this path
                half = int(fade_by_t[ticker]["fade"].get("half_shares") or max(1, max_sh // 2))
                half = max(1, min(half, max_sh))
                shares = half
                thesis_type = "radar_price_is_news"
                if not exit_class:
                    exit_class = "thesis_wrong"
            elif shares < 1 or shares > max_sh:
                shares = max_sh
        if action == "buy" and shares < 1:
            continue
        # price_is_news path does not buy
        if action == "buy" and ticker in fade_by_t:
            continue
        trades.append(
            {
                "action": action,
                "ticker": ticker,
                "shares": shares,
                "rationale": d.get("rationale") or d.get("thesis_fit_today") or "radar GO",
                "exit_thesis": d.get("exit_thesis") or "",
                "exit_conditions": d.get("exit_conditions") or {},
                "thesis_type": thesis_type,
                "confidence": d.get("confidence") or 0.5,
                "exit_classification": exit_class,
            }
        )
    return trades


def execute_trades(trades, pf, dry_run, secrets):
    # Reuse Commando validate_and_execute
    import llm_comando as lc

    state = {
        "id": pf["id"],
        "current_cash": pf["current_cash"],
        "starting_cash": pf["starting_cash"],
        "holdings": [],
        "_cycle_name": "radar",
        "_candidate_snapshot": {},
    }
    # total_value approximate
    tv = float(pf["current_cash"])
    return lc.validate_and_execute(trades, state, tv, secrets, dry_run=dry_run)


def post_slack(secrets, channel, text):
    if WebClient is None:
        log("slack_sdk not installed in this interpreter — skip Slack", "WARN")
        return
    try:
        WebClient(token=secrets["SLACK_BOT_TOKEN"]).chat_postMessage(channel=channel, text=text[:12000])
    except Exception as e:
        log(f"slack: {e}", "WARN")


def should_run_fade_scan(rstate, now, force=False):
    if force:
        return True
    last = newsutil._parse_iso(rstate.get("last_fade_scan_iso"))
    if last is None:
        return True
    return (now - last).total_seconds() >= FADE_SCAN_INTERVAL_MIN * 60


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-events", type=int, default=4)
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    ap.add_argument("--force-hours", type=float, default=0.35, help="If cursor empty, look back this many hours")
    ap.add_argument(
        "--force-fade-scan",
        action="store_true",
        help="Ignore 15m fade throttle (still respects per-ticker cooldown)",
    )
    args = ap.parse_args()

    if not acquire_lock(RADAR_LOCK, stale_sec=180):
        log("Another radar instance running — exit")
        return 0

    try:
        secrets = load_secrets()
        for k in ("ANTHROPIC_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY"):
            if k not in secrets:
                log(f"missing {k}", "ERROR")
                return 1

        # Market hours
        from autonomous_trader import get_trading_client

        client = get_trading_client()
        if not client.get_clock().is_open and not args.dry_run:
            log("Market closed — quiet exit")
            return 0

        remaining, fire_st = newsutil.event_fire_budget()
        if remaining <= 0:
            log(f"Event fire budget exhausted ({fire_st.get('fires')}/day)")
            return 0

        pf, holdings = get_portfolio()
        held = [h["ticker"] for h in holdings]

        rstate = newsutil.load_radar_state()
        cursor = newsutil._parse_iso(rstate.get("cursor_iso"))
        now = newsutil._now_utc()
        if cursor is None:
            cursor = now - datetime.timedelta(hours=args.force_hours)
        # never look back more than 6h on a single poll
        min_cursor = now - datetime.timedelta(hours=6)
        if cursor < min_cursor:
            cursor = min_cursor

        log(f"Radar poll since {cursor.isoformat()} holdings={held}")
        try:
            items = newsutil.fetch_alpaca_news(secrets, start=cursor, limit_pages=3)
        except Exception as e:
            log(f"Alpaca news failed: {e}", "ERROR")
            return 1

        fresh, rstate = newsutil.filter_new_items(items, rstate)
        rstate["cursor_iso"] = now.isoformat()
        rstate["last_run"] = now.isoformat()
        newsutil.save_radar_state(rstate)
        log(f"  items={len(items)} fresh={len(fresh)}")

        by_ticker = newsutil.group_fresh_by_ticker(fresh) if fresh else {}
        news_events = select_events(by_ticker, holdings, max_events=args.max_events) if by_ticker else []

        fade_events = []
        prices = {}
        if holdings and should_run_fade_scan(rstate, now, force=args.force_fade_scan):
            rstate["last_fade_scan_iso"] = now.isoformat()
            sector_map = resolve_sectors(held, rstate, now)
            newsutil.save_radar_state(rstate)
            bench = ["SPY", "QQQ"] + list({sector_map.get(t.upper(), "SPY") for t in held})
            need = list(dict.fromkeys([t.upper() for t in held] + bench))
            log(f"  fade scan prices for {need}")
            prices = load_price_stats(need, period="10d")
            fade_events = detect_holdings_fade(holdings, prices, sector_map, rstate, now)
        elif holdings:
            log("  fade scan throttled (15m)")

        events = merge_events(news_events, fade_events, max_events=args.max_events)
        if not events:
            if not fresh:
                log("  quiet: no news, no price_is_news trips")
            else:
                log("  fresh news had no single-stock symbols / no fade — skip LLM")
            return 0

        log("  events: " + ", ".join(f"{e['ticker']}({e['kind']})" for e in events))

        # Shared deliberative lock so we don't race morning cycle
        if not acquire_lock(LOCK_FILE, stale_sec=1200):
            log("Commando cycle/watcher holds main lock — defer events", "WARN")
            return 0

        try:
            tickers = list({e["ticker"] for e in events} | set(held) | {"SPY", "QQQ"})
            # sector ETFs from any fade events
            for e in events:
                se = (e.get("fade") or {}).get("sector_etf")
                if se:
                    tickers.append(se)
            if not prices:
                prices = load_price_stats(tickers, period="10d")
            else:
                missing = [t for t in tickers if t.upper() not in prices]
                if missing:
                    prices.update(load_price_stats(missing, period="10d"))

            cal = newsutil.upcoming_events_block(held, [e["ticker"] for e in events])
            j = journal_tail(5)
            user_msg = build_user_message(pf, holdings, events, prices, cal, j)
            out, cost, raw = call_go_agent(secrets, user_msg)
            newsutil.record_event_fire(
                fire_st, "radar_go", ",".join(f"{e['ticker']}:{e['kind']}" for e in events)
            )

            # Cooldown price_is_news names after we researched them
            fl = dict(rstate.get("fade_last_fire") or {})
            for e in events:
                if e.get("kind") == "price_is_news":
                    fl[e["ticker"].upper()] = now.isoformat()
            rstate["fade_last_fire"] = fl
            newsutil.save_radar_state(rstate)

            decisions = out.get("decisions") or []
            trades = decisions_to_trades(decisions, holdings, events=events)
            log(f"  narrative: {(out.get('market_narrative') or '')[:160]}")
            log(f"  decisions={len(decisions)} trades={len(trades)}")

            exec_results = []
            if trades:
                exec_results = execute_trades(trades, pf, args.dry_run, secrets)
                for tr, res in exec_results:
                    log(f"  exec {tr.get('action')} {tr.get('ticker')}: {res}")

            # Journal append (lightweight)
            try:
                entry = {
                    "date": now.strftime("%Y-%m-%d"),
                    "type": "radar",
                    "ts": now.isoformat(),
                    "market_narrative": out.get("market_narrative"),
                    "events": [
                        {
                            "ticker": e["ticker"],
                            "kind": e["kind"],
                            "n_headlines": len(e["items"]),
                            "fade": e.get("fade"),
                        }
                        for e in events
                    ],
                    "decisions": decisions,
                    "trades": trades,
                    "execution_results": [
                        {"ticker": tr.get("ticker"), "action": tr.get("action"), "result": res}
                        for tr, res in (exec_results or [])
                    ],
                    "cost_usd": cost,
                    "dry_run": args.dry_run,
                }
                JOURNAL.parent.mkdir(parents=True, exist_ok=True)
                with open(JOURNAL, "a") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception as e:
                log(f"journal: {e}", "WARN")

            # Slack
            if not args.dry_run and secrets.get("SLACK_BOT_TOKEN"):
                kinds = ",".join(sorted({e["kind"] for e in events}))
                lines = [
                    f"*Commando RADAR GO* ({kinds})",
                    out.get("market_narrative") or "",
                    "Events: " + ", ".join(f"{e['ticker']}[{e['kind']}]" for e in events),
                ]
                for d in decisions:
                    lines.append(
                        f"• {(d.get('action') or '?').upper()} {d.get('ticker')} "
                        f"— {(d.get('rationale') or '')[:160]}"
                    )
                lines.append(f"Cost ${cost:.3f} | budget left ~{remaining - 1}")
                post_slack(secrets, args.channel, "\n".join(lines))
        finally:
            release_lock(LOCK_FILE)

        return 0
    finally:
        release_lock(RADAR_LOCK)


if __name__ == "__main__":
    raise SystemExit(main() or 0)
