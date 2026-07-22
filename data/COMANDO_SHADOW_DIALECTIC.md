# Commando LIVE = former OpenRouter shadow (2026-07-22)

## Live (executes trades)
| Seat | Model via OpenRouter |
|------|----------------------|
| Bull | anthropic/claude-sonnet-4.6 |
| Bear | anthropic/claude-sonnet-4.6 |
| Judge | x-ai/grok-4.5 |

Radar GO + watcher triggers: OpenRouter Sonnet.

## Dual shadow path
**OFF** — no longer run a second dialectic after live (was ~2x cost).

## Secrets
Required: `OPENROUTER_API_KEY` in `~/.env_secrets`  
Optional: `ANTHROPIC_API_KEY` for Slack bot / Claude Code / legacy scripts only.

## Anthropic subscription
Commando trading path no longer needs direct Anthropic API billing.
You may still pay OpenRouter for Claude tokens (usage-based).
Slack interactive bot (`src/bot.py`) still expects Anthropic if you use it.

## Rollback
Restore `scripts/llm_comando.py.bak_pre_or_grad` (and radar/watcher same suffix).
