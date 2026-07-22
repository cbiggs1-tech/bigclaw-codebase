#!/usr/bin/env python3
"""Post-migration recheck: direct Anthropic dependency for subscription kill."""
from pathlib import Path
import re
import subprocess

ROOT = Path.home() / "bigclaw-ai"
SKIP = re.compile(r"(\.bak|attic|__pycache__|venv|migrate_|fix_|audit_|promote_|patch_|smoke_)")

print("=" * 70)
print("1) Hard ANTHROPIC_API_KEY requirements (would fail without key)")
print("=" * 70)
for p in list((ROOT / "scripts").rglob("*.py")) + list((ROOT / "src").rglob("*.py")):
    if SKIP.search(str(p)):
        continue
    text = p.read_text(errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        if "ANTHROPIC_API_KEY" not in line:
            continue
        # skip comments / optional
        if any(
            x in line
            for x in (
                "optional",
                "legacy",
                "OPENROUTER",
                "or ANTHROPIC",
                "#",
            )
        ):
            # still show if it's the only key required
            if "OPENROUTER" in line or "optional" in line.lower() or "legacy" in line.lower():
                continue
        if re.search(r'os\.environ\[["\']ANTHROPIC_API_KEY|secrets\.get\(["\']ANTHROPIC|ANTHROPIC_API_KEY not|missing.*ANTHROPIC|ANTHROPIC_API_KEY["\']\)', line):
            print(f"  {p.relative_to(ROOT)}:{i}: {line.strip()[:140]}")

print()
print("=" * 70)
print("2) Anthropic() constructions (SDK clients)")
print("=" * 70)
for p in list((ROOT / "scripts").rglob("*.py")) + list((ROOT / "src").rglob("*.py")):
    if SKIP.search(str(p)):
        continue
    text = p.read_text(errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"anthropic\.Anthropic\(|from anthropic import Anthropic", line):
            # classify base_url openrouter
            ctx = "\n".join(text.splitlines()[max(0, i - 3) : i + 5])
            via = "OPENROUTER base_url" if "openrouter.ai" in ctx else "DIRECT?"
            print(f"  {p.relative_to(ROOT)}:{i}: [{via}] {line.strip()[:100]}")

print()
print("=" * 70)
print("3) Migrated scripts use OpenRouter?")
print("=" * 70)
for name in [
    "morning_briefing.py",
    "afternoon_summary.py",
    "weekly_research.py",
    "sector_rotation.py",
    "overnight_case.py",
    "llm_comando_reconciler.py",
    "llm_comando.py",
    "llm_comando_radar.py",
    "llm_comando_watcher.py",
    "research_dossier.py",
    "llm_portfolio.py",
    "llm_portfolio_watcher.py",
    "llm_portfolio_reconciler.py",
    "or_llm.py",
]:
    p = ROOT / "scripts" / name
    if not p.exists():
        print(f"  MISSING {name}")
        continue
    t = p.read_text()
    or_ok = "or_llm" in t or "call_openrouter" in t or "OPENROUTER" in t or "openrouter.ai" in t
    ant = bool(re.search(r"anthropic\.Anthropic\(|ANTHROPIC_API_KEY not", t))
    status = "OR" if or_ok and not ant else ("MIXED" if or_ok and ant else ("ANTHROPIC" if ant else "?"))
    print(f"  [{status:8s}] {name}")

print()
print("=" * 70)
print("4) Scheduled ACTIVE crons vs provider")
print("=" * 70)
cron = subprocess.check_output(["crontab", "-l"], text=True)
map_scripts = {
    "morning_briefing.py": "OpenRouter Sonnet",
    "afternoon_summary.py": "OpenRouter Sonnet",
    "weekly_research.py": "OpenRouter Sonnet",
    "sector_rotation.py": "OpenRouter Sonnet",
    "overnight_case.py": "OpenRouter Sonnet+Grok",
    "llm_comando.py": "OpenRouter Sonnet/Sonnet/Grok",
    "llm_comando_radar.py": "OpenRouter Sonnet",
    "llm_comando_watcher.py": "OpenRouter Sonnet",
    "llm_comando_reconciler.py": "OpenRouter Sonnet (extract)",
}
for line in cron.splitlines():
    if line.strip().startswith("#") or not line.strip():
        continue
    for s, prov in map_scripts.items():
        if s in line:
            print(f"  ACTIVE {s:28s} -> {prov}")

print()
print("=" * 70)
print("5) Smoke OpenRouter")
print("=" * 70)
import os
import sys

sys.path.insert(0, str(ROOT / "scripts"))
# load secrets
for line in (Path.home() / ".env_secrets").read_text().splitlines():
    line = line.strip()
    if line.startswith("export "):
        line = line[7:]
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
from or_llm import call_openrouter, SONNET, GROK

for model, label in [(SONNET, "sonnet"), (GROK, "grok")]:
    text, cost, dt, *_ = call_openrouter(
        "Reply with exactly: OK", "tester", model=model, max_tokens=16, agent=f"recheck_{label}"
    )
    print(f"  {label}: {text!r} cost=${cost:.4f} t={dt:.1f}s")
print("SMOKE OK")
print()
print("NOTE: bot.py still constructs anthropic.Anthropic but with base_url=OpenRouter when OPENROUTER_API_KEY set.")
print("That traffic bills OpenRouter, not Anthropic subscription — as long as OPENROUTER_API_KEY is present.")
