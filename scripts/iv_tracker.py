"""IV tracker — daily snapshot of options-implied volatility signatures.

Captures forward-looking IV signals (skew + call-put spread) for current holdings
AND top-scoring candidates across all portfolios. Writes to iv_history table for
a 30-day data-gathering experiment (started 2026-05-31).

Goal: assemble enough point-in-time data to ask:
  - Did stocks bought with bullish IV signature outperform vs those without?
  - Across the broader candidate set, do bullish-IV names beat bearish-IV?
  - At what threshold / persistence does the signal become robust?

Then use those answers to design how (if at all) to wire IV into the decision engine.
DOES NOT modify the decision engine. Pure data collection.

Signals captured per ticker per expiry:
  - skew = OTM put IV (~10% below spot) minus ATM call IV
           steep positive = downside fear (bearish)
  - spread = ATM call IV minus ATM put IV
            positive = informed bullish demand
  - classification = BULLISH / BEARISH / MIXED

Universe each day:
  - All current holdings (~60)
  - Top 10 scored candidates per portfolio from signals.json (~70 unique)
  - Union, ~100-130 unique tickers per day

Expiries captured per ticker: nearest to ~30d AND ~60d out (two rows per ticker).
"""
import os, sys, sqlite3, json, datetime
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

os.chdir(str(Path.home() / "bigclaw-ai"))
import yfinance as yf

DB_PATH = "src/portfolios.db"
SIGNALS_PATH = "docs/data/signals.json"
TOP_N_PER_PORTFOLIO = 10
TARGET_DAYS = [30, 60]
OTM_PCT = 0.10  # OTM put strike = spot * (1 - 0.10)

# ---------- DB setup ----------
def init_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS iv_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            target_days INTEGER NOT NULL,
            expiry TEXT NOT NULL,
            spot REAL,
            atm_call_iv REAL,
            atm_put_iv REAL,
            otm_put_iv REAL,
            otm_put_strike REAL,
            skew REAL,
            spread REAL,
            classification TEXT,
            captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(snapshot_date, ticker, target_days)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_iv_history_date_ticker ON iv_history(snapshot_date, ticker)")
    conn.commit()

# ---------- universe ----------
def build_universe():
    """Holdings + top-10 candidates per portfolio."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    rows = conn.execute("SELECT DISTINCT ticker FROM holdings WHERE shares > 0").fetchall()
    conn.close()
    universe = {r[0] for r in rows}
    try:
        sig = json.load(open(SIGNALS_PATH))
        for pname, pf_sigs in sig.get("portfolio_signals", {}).items():
            ranked = sorted(pf_sigs.items(), key=lambda kv: -kv[1].get("score", 0))[:TOP_N_PER_PORTFOLIO]
            universe.update(t for t, _ in ranked)
    except Exception as e:
        print(f"WARN: signals.json read failed ({e}); proceeding with holdings only")
    return sorted(universe)

# ---------- IV signature per ticker ----------
def chain_for_expiry(tk, target_days):
    exps = tk.options
    if not exps:
        return None, None
    target_date = datetime.date.today() + datetime.timedelta(days=target_days)
    best = min(exps, key=lambda e: abs(
        (datetime.datetime.strptime(e, "%Y-%m-%d").date() - target_date).days))
    try:
        ch = tk.option_chain(best)
    except Exception:
        return best, None
    return best, ch

def signature(ticker, target_days, spot):
    tk = yf.Ticker(ticker)
    expiry, ch = chain_for_expiry(tk, target_days)
    if ch is None or ch.calls.empty or ch.puts.empty:
        return None
    calls = ch.calls[(ch.calls.openInterest > 0) | (ch.calls.volume > 0)]
    puts  = ch.puts[(ch.puts.openInterest > 0)  | (ch.puts.volume > 0)]
    if calls.empty or puts.empty:
        return None
    calls = calls.assign(d=(calls.strike - spot).abs())
    puts  = puts.assign(d=(puts.strike - spot).abs())
    atm_c = calls.loc[calls.d.idxmin()]
    atm_p = puts.loc[puts.d.idxmin()]
    otm_strike = spot * (1 - OTM_PCT)
    p2 = puts.assign(d2=(puts.strike - otm_strike).abs())
    otm_p = p2.loc[p2.d2.idxmin()]
    skew = float(otm_p.impliedVolatility) - float(atm_c.impliedVolatility)
    spread = float(atm_c.impliedVolatility) - float(atm_p.impliedVolatility)
    cls = "MIXED"
    if spread > 0 and skew <= 0: cls = "BULLISH"
    elif spread < 0 and skew > 0: cls = "BEARISH"
    return {
        "expiry": expiry,
        "atm_call_iv": float(atm_c.impliedVolatility),
        "atm_put_iv": float(atm_p.impliedVolatility),
        "otm_put_iv": float(otm_p.impliedVolatility),
        "otm_put_strike": float(otm_p.strike),
        "skew": skew, "spread": spread, "classification": cls,
    }

# ---------- main ----------
def main():
    snapshot_date = datetime.date.today().isoformat()
    universe = build_universe()
    print(f"[{snapshot_date}] universe size: {len(universe)}")

    # batch spot prices once
    px = yf.download(universe, period="2d", progress=False, threads=True)["Close"]
    spots = {}
    for t in universe:
        try:
            v = float(px[t].iloc[-1])
            if v == v and v > 0:
                spots[t] = v
        except Exception:
            pass
    print(f"  spots fetched: {len(spots)}/{len(universe)}")

    conn = sqlite3.connect(DB_PATH, timeout=10)
    init_table(conn)
    inserted = skipped = errored = 0
    counts_by_cls = {"BULLISH": 0, "BEARISH": 0, "MIXED": 0}

    for ticker in universe:
        if ticker not in spots:
            skipped += 1
            continue
        spot = spots[ticker]
        for td in TARGET_DAYS:
            try:
                sig = signature(ticker, td, spot)
                if sig is None:
                    skipped += 1
                    continue
                conn.execute("""
                    INSERT OR IGNORE INTO iv_history
                    (snapshot_date, ticker, target_days, expiry, spot,
                     atm_call_iv, atm_put_iv, otm_put_iv, otm_put_strike,
                     skew, spread, classification)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (snapshot_date, ticker, td, sig["expiry"], spot,
                      sig["atm_call_iv"], sig["atm_put_iv"], sig["otm_put_iv"],
                      sig["otm_put_strike"], sig["skew"], sig["spread"],
                      sig["classification"]))
                inserted += 1
                if td == 60:
                    counts_by_cls[sig["classification"]] += 1
            except Exception:
                errored += 1
                continue
    conn.commit()
    conn.close()

    print(f"  inserted: {inserted}  skipped: {skipped}  errored: {errored}")
    print(f"  60-day distribution: BULLISH={counts_by_cls['BULLISH']}  "
          f"MIXED={counts_by_cls['MIXED']}  BEARISH={counts_by_cls['BEARISH']}")

if __name__ == "__main__":
    main()
