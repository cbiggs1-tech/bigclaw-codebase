#!/usr/bin/env python3
"""
LLM-Comando event-driven radar.

Poll frequently during RTH. When NEW news arrives on holdings or strong
single-stock names, run a focused Judge-style decision WITHOUT waiting for
09:00 / 11:30 / 14:30 sessions.

Usage:
  source ~/.env_secrets
  python3 llm_comando_radar.py --dry-run
  python3 llm_comando_radar.py
  python3 llm_comando_radar.py --max-events 3

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

PORTFOLIO_NAME = "LLM-Comando"
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

GO_SYSTEM = """You are the LLM-Comando decision agent on an EVENT-DRIVEN path.
New market information just arrived. You must decide NOW — do not wait for a scheduled session.

NORTH STAR:
- Figure out how to win THIS session from today's narrative.
- Study the stock(s) below; weigh bull and bear angles briefly; decide.
- Day-trader speed with investor sense: real thesis + falsifiers, or stand down.
- SELL when a holding's buy thesis is breaking on this news.
- Journal history is analogy only — yesterday's failure may win today.
- Individual stocks only — never ETFs.

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
- If news only affects a holding's thesis, sell/hold that name; do not force a new buy.
- exit_classification for sells: thesis_wrong | thesis_changed | thesis_played_out
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
        raise RuntimeError("Comando portfolio not found/active")
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


def quick_prices(tickers):
    out = {}
    if not tickers:
        return out
    try:
        hist = yf.download(list(tickers), period="5d", progress=False, threads=True)["Close"]
        for t in tickers:
            try:
                if hasattr(hist, "columns") and t in hist.columns:
                    s = hist[t].dropna()
                else:
                    s = hist.dropna()
                if len(s) < 1:
                    continue
                px = float(s.iloc[-1])
                r1 = float(s.iloc[-1] / s.iloc[-2] - 1) * 100 if len(s) >= 2 else 0.0
                out[t] = {"price": px, "ret_1d": r1}
            except Exception:
                pass
    except Exception as e:
        log(f"price fetch: {e}", "WARN")
    return out


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
        px_s = f"${px:.2f}" if px else "?"
        r_s = f"{r1:+.1f}%" if r1 is not None else "?"
        thesis = (h.get("rationale") or "")[:180]
        lines.append(
            f"    {t}: {h['shares']:.0f} sh @ ${h['avg_cost']:.2f}  now {px_s} ({r_s})  WHY_BOUGHT: {thesis}"
        )
    lines.append("")
    lines.append(calendar_block)
    lines.append("")
    lines.append("## NEW EVENTS (act on these — this is why you were woken)")
    for ev in events:
        lines.append(f"\n### {ev['ticker']} [{ev['kind']}]")
        if ev.get("score") is not None:
            lines.append(f"  recency_score={ev['score']}")
        for it in ev["items"]:
            lines.append(
                f"  - [{it.get('time','')[:16]}] [{it.get('source','')}] {it.get('headline','')}"
            )
            if it.get("summary"):
                lines.append(f"    {it['summary'][:220]}")
        if ev["ticker"] in prices:
            lines.append(
                f"  price_now=${prices[ev['ticker']]['price']:.2f}  day={prices[ev['ticker']].get('ret_1d',0):+.1f}%"
            )
    if journal:
        lines.append("\n## JOURNAL TAIL (analogy only)")
        for e in journal[-3:]:
            lines.append(f"  {e.get('date')} trades={len(e.get('trades') or [])} {(e.get('reflection') or '')[:120]}")
    lines.append("\n## TASK")
    lines.append(
        "For each event ticker: buy / sell / stand_down. "
        "Holdings with news: re-verify buy thesis — sell if breaking. "
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


def decisions_to_trades(decisions, holdings):
    held_qty = {h["ticker"].upper(): float(h["shares"]) for h in holdings}
    trades = []
    for d in decisions or []:
        action = (d.get("action") or "stand_down").lower()
        ticker = (d.get("ticker") or "").upper()
        if action == "stand_down" or not ticker:
            continue
        shares = int(d.get("shares") or 0)
        if action == "sell":
            max_sh = int(held_qty.get(ticker, 0))
            if max_sh <= 0:
                continue
            if shares < 1 or shares > max_sh:
                shares = max_sh
        if action == "buy" and shares < 1:
            continue
        trades.append(
            {
                "action": action,
                "ticker": ticker,
                "shares": shares,
                "rationale": d.get("rationale") or d.get("thesis_fit_today") or "radar GO",
                "exit_thesis": d.get("exit_thesis") or "",
                "exit_conditions": d.get("exit_conditions") or {},
                "thesis_type": "radar_event",
                "confidence": d.get("confidence") or 0.5,
                "exit_classification": d.get("exit_classification"),
            }
        )
    return trades


def execute_trades(trades, pf, dry_run, secrets):
    # Reuse Comando validate_and_execute
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-events", type=int, default=4)
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    ap.add_argument("--force-hours", type=float, default=0.35, help="If cursor empty, look back this many hours")
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

        if not fresh:
            return 0

        by_ticker = newsutil.group_fresh_by_ticker(fresh)
        # Also attach RSS-only headlines to context without inventing symbols
        events = select_events(by_ticker, holdings, max_events=args.max_events)
        if not events:
            log("  fresh news had no single-stock symbols — skip LLM")
            return 0

        log(
            "  events: "
            + ", ".join(f"{e['ticker']}({e['kind']})" for e in events)
        )

        # Shared deliberative lock so we don't race morning cycle
        if not acquire_lock(LOCK_FILE, stale_sec=1200):
            log("Comando cycle/watcher holds main lock — defer events", "WARN")
            return 0

        try:
            tickers = list({e["ticker"] for e in events} | set(held))
            prices = quick_prices(tickers + ["SPY", "QQQ", "XLK"])
            cal = newsutil.upcoming_events_block(held, [e["ticker"] for e in events])
            j = journal_tail(5)
            user_msg = build_user_message(pf, holdings, events, prices, cal, j)
            out, cost, raw = call_go_agent(secrets, user_msg)
            newsutil.record_event_fire(
                fire_st, "radar_go", ",".join(e["ticker"] for e in events)
            )

            decisions = out.get("decisions") or []
            trades = decisions_to_trades(decisions, holdings)
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
                        {"ticker": e["ticker"], "kind": e["kind"], "n_headlines": len(e["items"])}
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
                lines = [
                    f"*Comando RADAR GO* ({'dry-run' if args.dry_run else 'live'})",
                    out.get("market_narrative") or "",
                    "Events: " + ", ".join(f"{e['ticker']}" for e in events),
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
