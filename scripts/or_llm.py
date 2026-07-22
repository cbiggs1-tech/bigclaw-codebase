#!/usr/bin/env python3
"""Shared OpenRouter LLM helper for BigClaw scripts (no direct Anthropic)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional, Tuple

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_LOG = Path.home() / "bigclaw-ai" / "logs" / "llm_calls.jsonl"

# Preferred production models (all via OpenRouter)
SONNET = "anthropic/claude-sonnet-4.6"
GROK = "x-ai/grok-4.5"
GEMINI_FLASH = "google/gemini-3.1-flash-lite-preview"

# Approximate $/MTok for local cost logs (OpenRouter bills actual)
_PRICING = {
    SONNET: (3.0, 15.0),
    GROK: (3.0, 15.0),
    GEMINI_FLASH: (0.25, 1.5),
    "anthropic/claude-opus-4.6": (5.0, 25.0),
    "anthropic/claude-sonnet-4-6": (3.0, 15.0),
}


def _api_key(secrets: Optional[dict] = None) -> str:
    if secrets and secrets.get("OPENROUTER_API_KEY"):
        return secrets["OPENROUTER_API_KEY"]
    k = os.environ.get("OPENROUTER_API_KEY")
    if not k:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return k


def call_openrouter(
    prompt: str,
    system: str = "",
    model: str = SONNET,
    max_tokens: int = 4000,
    temperature: float = 0.3,
    timeout: float = 120.0,
    secrets: Optional[dict] = None,
    agent: str = "or_llm",
) -> Tuple[str, float, float, int, int]:
    """Returns (text, cost_usd, duration_s, in_tok, out_tok)."""
    headers = {
        "Authorization": f"Bearer {_api_key(secrets)}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://bigclaw.grandpapa.net",
        "X-Title": "BigClaw AI",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    t0 = time.time()
    last = None
    data = None
    for attempt in range(3):
        try:
            r = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    if data is None:
        raise last
    dt = time.time() - t0
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not text.strip():
        raise RuntimeError(f"OpenRouter empty content model={model}")
    usage = data.get("usage") or {}
    in_tok = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    out_tok = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    ir, orr = _PRICING.get(model, (3.0, 15.0))
    cost = (in_tok * ir + out_tok * orr) / 1_000_000
    if usage.get("total_cost") is not None:
        try:
            cost = float(usage["total_cost"])
        except Exception:
            pass
    try:
        LLM_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LLM_LOG.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                        "agent": agent,
                        "model": model,
                        "in": in_tok,
                        "out": out_tok,
                        "cost": round(cost, 6),
                        "sec": round(dt, 2),
                        "provider": "openrouter",
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    return text, cost, dt, in_tok, out_tok
