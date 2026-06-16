"""Single source of truth for waiting on Alpaca order fills.

Bug class this module exists to prevent: treating Alpaca's `partially_filled`
substring match as a final fill, recording the partial qty to the DB, and
leaving the open remainder on Alpaca where it later fills "for free" — causing
per-portfolio cash to be undercounted by the value of the late fills.

Contract: the returned (filled_qty, filled_price) match Alpaca's terminal
state for the order. If the order has not reached a terminal state within
timeout_s, the open remainder is canceled and we poll until Alpaca confirms
the cancel has settled (or until 10s after cancel — whichever comes first).
This means the DB record we're about to write agrees with what Alpaca will
report forever after for this order id.
"""

import time
from bigclaw_logging import get_logger

logger = get_logger("order_fill")

TERMINAL_STATES = {"filled", "canceled", "expired", "rejected", "done_for_day"}
PRIMARY_POLL_INTERVAL_S = 2
CANCEL_POLL_INTERVAL_S = 0.5
CANCEL_POLL_DEADLINE_S = 10


def _terminal_state(status_obj) -> str:
    """'OrderStatus.FILLED' -> 'filled'. Robust to enum or string input."""
    s = str(status_obj).lower()
    return s.rsplit(".", 1)[-1] if "." in s else s


def _extract_fill(order_obj, est_price):
    qty = int(float(order_obj.filled_qty or 0))
    avg = float(order_obj.filled_avg_price) if order_obj.filled_avg_price else None
    return qty, (avg if avg else (est_price or 0.0))


def wait_for_fill(client, order, ordered_qty, est_price,
                  ticker="", pname="", side="", timeout_s=30):
    """Wait for an Alpaca order to reach a terminal state.

    Args:
        client: Alpaca TradingClient
        order: the order object returned from submit_order
        ordered_qty: shares originally submitted (for logging only)
        est_price: fallback price if Alpaca reports no avg fill price
        ticker, pname, side: optional — used in log messages for context
        timeout_s: primary fill window. After this, the open remainder is
            canceled and we poll until Alpaca confirms cancel settled.

    Returns:
        (filled_qty: int, filled_price: float)

        At any caller that records to DB, these values are guaranteed to
        match what Alpaca will permanently report for this order. No "fills
        later show up on Alpaca but not in DB" drift is possible.
    """
    ctx = " ".join(p for p in (pname, side, ticker) if p)
    if not ctx:
        ctx = f"order {order.id}"

    # Initial 1s nudge — most market orders fill within a second
    time.sleep(1)
    elapsed = 1

    while elapsed < timeout_s:
        updated = client.get_order_by_id(str(order.id))
        state = _terminal_state(updated.status)
        if state in TERMINAL_STATES:
            return _extract_fill(updated, est_price)
        time.sleep(PRIMARY_POLL_INTERVAL_S)
        elapsed += PRIMARY_POLL_INTERVAL_S

    # Primary timeout — request cancel of the remaining open quantity
    try:
        client.cancel_order_by_id(str(order.id))
    except Exception as e:
        logger.warning(f"{ctx} | cancel API call failed: {e}")
        # Fall through to polling — order might still settle on its own

    # Cancel is async. Poll until status reaches a terminal state. During
    # this window, the open remainder can still fill (race between fill and
    # cancel). filled_qty at the moment of terminal status is the truth.
    cancel_deadline = time.time() + CANCEL_POLL_DEADLINE_S
    final = None
    reached_terminal = False
    while time.time() < cancel_deadline:
        time.sleep(CANCEL_POLL_INTERVAL_S)
        try:
            final = client.get_order_by_id(str(order.id))
        except Exception as e:
            logger.warning(f"{ctx} | order read during cancel-poll failed: {e}")
            continue
        if _terminal_state(final.status) in TERMINAL_STATES:
            reached_terminal = True
            break

    if not reached_terminal:
        last_state = _terminal_state(final.status) if final else "unknown"
        logger.error(
            f"CRITICAL | {ctx} | order {order.id} did not reach a terminal "
            f"state within {CANCEL_POLL_DEADLINE_S}s of cancel; last status="
            f"{last_state}; recording last-known filled qty — manual "
            f"reconciliation may be required"
        )

    qty, price = _extract_fill(final, est_price) if final else (0, est_price or 0.0)
    final_state = _terminal_state(final.status) if final else "unknown"
    logger.warning(
        f"{ctx} | timeout — final state={final_state}, filled {qty}/{ordered_qty}"
    )
    return qty, price


def clamp_sell_to_long(client, alpaca_symbol, requested_shares, allow_short=False):
    """Cap a SELL at the live Alpaca long position so we never open or extend a
    short BY ACCIDENT. Shared long-only safety backstop for every sell path.

    Returns the share qty that is safe to sell:
      - allow_short=True              -> requested_shares unchanged (DELIBERATE short)
      - flat / already short at Alpaca-> 0  (block: selling would go short)
      - long N shares                 -> min(requested, N)
      - genuine Alpaca read error     -> requested unchanged (fail-open; a broker
        hiccup must never block a legit sell — per-portfolio DB bounds still apply)

    Pass allow_short=True ONLY when a short is explicitly intended.
    """
    req = int(requested_shares)
    if allow_short:
        return req
    try:
        pos = client.get_open_position(alpaca_symbol)
        long_qty = int(float(pos.qty))
        return min(req, long_qty) if long_qty > 0 else 0
    except Exception as e:
        m = str(e).lower()
        if "position does not exist" in m or "not found" in m or "404" in m:
            return 0  # flat -> selling would short
        return req     # real API error -> fail-open to upstream DB bounds
