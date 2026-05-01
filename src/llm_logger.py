"""Shared LLM-call logger. Writes one JSON line per Anthropic API call to
~/bigclaw-ai/logs/llm_calls.jsonl. Logging never raises — never breaks the call.

Used by: morning_briefing, afternoon_summary, weekly_research, agent (bot),
scheduler. Aggregator at scripts/llm_token_report.py reads this file daily.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

# Per-million-token pricing (input, output) as of May 2026
PRICES = {
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
}

LOG_PATH = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"


def estimate_cost(model, input_tokens, output_tokens):
    """Return est USD cost. Defaults to Opus pricing if model unknown."""
    in_rate, out_rate = PRICES.get(model, (15.0, 75.0))
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


def log_call(script_name, response, duration_s):
    """Append a record for one Anthropic messages.create call.

    Args:
        script_name: short label like "bot.agent", "scheduler", "morning_briefing"
        response: anthropic SDK response object (must have .model and .usage)
        duration_s: wall-clock seconds for the call
    """
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        in_tok = response.usage.input_tokens
        out_tok = response.usage.output_tokens
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "script": script_name,
            "model": response.model,
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "duration_s": round(duration_s, 2),
            "est_cost_usd": round(estimate_cost(response.model, in_tok, out_tok), 6),
        }
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # logging must never break the call
