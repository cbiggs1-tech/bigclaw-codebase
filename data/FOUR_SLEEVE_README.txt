Four-sleeve cutover 2026-07-21 (after close)

DONE tonight:
- DB backup portfolios.db.bak-pre-4sleeve-20260721
- Universes reduced to Innovation / Momentum / AI Defense (unique ~131)
- candidate_screener capped + only KEEP books
- llm_portfolio* crons disabled
- Comando NORTH STAR doctrine + journal-as-analogy + entry feature logger

TOMORROW AT OPEN (~08:40 CT / 09:40 ET):
  source ~/.env_secrets
  python3 ~/bigclaw-ai/scripts/flatten_kill_portfolios.py --dry-run
  python3 ~/bigclaw-ai/scripts/flatten_kill_portfolios.py --execute
  # after fills + DB reconcile of kill books to 0 shares:
  python3 ~/bigclaw-ai/scripts/flatten_kill_portfolios.py --deactivate-only

KEEP: Innovation Fund, Momentum Growth, AI Defense, LLM-Comando
KILL: Value, Growth Value, Income, Nuclear, LLM-ETF Focus
