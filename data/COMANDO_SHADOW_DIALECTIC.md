# Comando shadow dialectic (OpenRouter)

**Live (executes trades):** Anthropic Sonnet Bull + Sonnet Bear + Opus Judge  
**Shadow (log only):** OpenRouter nthropic/claude-sonnet-4.6 Bull + Bear + x-ai/grok-4.5 Judge

## Behavior
- Runs after live execute each morning/midday/afternoon cycle
- Never submits Alpaca orders
- Disable: python3 llm_comando.py --no-shadow or set SHADOW_DIALECTIC_ENABLED = False

## Logs
- data/dialectic_shadow/YYYY-MM-DD.jsonl
- data/judge_ab/YYYY-MM-DD_openrouter_shadow.jsonl
- logs/llm_comando.log lines: SHADOW dialectic starting / SHADOW done

## Goal
Prove OpenRouter stack is reliable enough to retire Anthropic subscription for Comando sessions.
