---
name: self-improve
description: Analyze and fix your own configs, prompts, or response quality using Grok 4 reasoning. Use when Curtis says "fix yourself", "improve response", "debug config", "why so factual", "why not analytical", "tune yourself", "you can do better", or any feedback about response quality, personality, analytical depth, or config issues.
---

# Self-Improve

Diagnose and fix issues with your own behavior, configs, prompts, or response quality.

## When to Activate
- Curtis gives feedback about response quality (too factual, not analytical enough, too hedgy, too verbose, etc.)
- Explicit commands: "fix yourself", "improve", "tune yourself", "debug config"
- After a response that felt weak or off-brand
- Config or skill troubleshooting
- **Auto-trigger (SOUL.md handles this):** On complex financial/analysis queries, the self-reflection check in SOUL.md's Meta-Improvement Directive fires automatically — no skill invocation needed. This skill is for deeper diagnostic work when something is structurally wrong.

## Diagnosis Protocol

### Step 1: Identify the Problem Category

| Symptom | Likely Cause | Fix Target |
|---------|-------------|------------|
| Too factual / dashboard-like | SOUL.md analytical mandates not strong enough | SOUL.md |
| Too hedgy / intern-like | Temperature too low or safety language too strong | openclaw.json params + SOUL.md |
| Missing synthesis / no "so what" | Post-data synthesis loop not triggering | SOUL.md "How to Work" section |
| Wrong model / slow / fallback | Auth or config issue | openclaw.json + auth-profiles.json |
| Skills not loading | Stale session snapshots | sessions.json cleanup |
| Personality off | IDENTITY.md or SOUL.md tone section | SOUL.md personality section |
| Repetitive / checklist-y | presence_penalty too low | openclaw.json params |
| Too short / truncated | maxTokens too low | openclaw.json params |
| Stale data in reports | Cron or export pipeline issue | cron jobs + export_dashboard.py |

### Step 2: Read Current Configs

```bash
# Response quality issues — read the brain files
cat ~/.openclaw/workspace/SOUL.md
cat ~/.openclaw/workspace/MEMORY.md
cat ~/.openclaw/workspace/ANALYSIS.md

# Model/config issues — read the configs (redact keys in output)
python3 -c "
import json
with open('$HOME/.openclaw/openclaw.json') as f:
    d = json.load(f)
params = d.get('agents',{}).get('defaults',{}).get('models',{}).get('xai/grok-4',{}).get('params',{})
model = d.get('agents',{}).get('defaults',{}).get('model',{})
print('Primary model:', model.get('primary'))
print('Fallbacks:', model.get('fallbacks'))
print('Grok-4 params:', json.dumps(params, indent=2))
"

# Auth issues
python3 -c "
import json
with open('$HOME/.openclaw/agents/main/agent/auth-profiles.json') as f:
    d = json.load(f)
for k in d: print(f'{k}: provider={d[k].get(\"provider\")}')
"

# Skills visibility
python3 -c "
import json
with open('$HOME/.openclaw/agents/main/sessions/sessions.json') as f:
    d = json.load(f)
main = d.get('agent:main:main', {})
skills = main.get('skillsSnapshot', {}).get('skills', [])
print(f'Main session: {len(skills)} skills loaded')
print(f'Model: {main.get(\"model\")} via {main.get(\"modelProvider\")}')
"
```

### Step 3: Propose Changes

For each issue found, output:
1. **What's wrong** — specific diagnosis
2. **Why it causes the symptom** — causal reasoning
3. **Proposed fix** — exact file edits as code blocks
4. **Risk assessment** — what could go wrong

Example format:
```
DIAGNOSIS: Temperature at 0.7 producing overly safe token selection
CAUSE: Grok 4 defaults to conservative phrasing at lower temps
FIX: Edit ~/.openclaw/openclaw.json → xai/grok-4 params → temperature: 0.9
RISK: Slight increase in creative phrasing, negligible hallucination risk at 0.9
```

### Step 4: Apply Changes (with approval)

**Config changes** — edit the JSON directly:
```bash
# Example: bump temperature
python3 -c "
import json
path = '$HOME/.openclaw/openclaw.json'
with open(path) as f: d = json.load(f)
d['agents']['defaults']['models']['xai/grok-4']['params']['temperature'] = 0.9
with open(path, 'w') as f: json.dump(d, f, indent=2)
print('Updated temperature to 0.9')
"
```

**Prompt changes** — edit workspace markdown files directly using the edit tool.

**Session cache** — clear stale snapshots if skills aren't loading:
```bash
python3 -c "
import json
path = '$HOME/.openclaw/agents/main/sessions/sessions.json'
with open(path) as f: d = json.load(f)
cleared = 0
for key in list(d.keys()):
    if isinstance(d[key], dict) and 'skillsSnapshot' in d[key]:
        del d[key]['skillsSnapshot']
        d[key]['systemSent'] = False
        cleared += 1
with open(path, 'w') as f: json.dump(d, f)
print(f'Cleared {cleared} stale session snapshots')
"
```

**Always restart gateway after config changes:**
```bash
systemctl --user restart openclaw-gateway
sleep 3
systemctl --user status openclaw-gateway | head -5
```

### Step 5: Validate

After applying changes, verify:
```bash
# Check gateway is up with correct model
journalctl _PID=$(systemctl --user show openclaw-gateway -p MainPID --value) -n 20 --no-pager 2>/dev/null | grep -i "model\|param\|error\|slack\|discord"

# Check params are applied (look for temperature/maxTokens in log)
grep "extraParams\|streamFn\|temperature\|maxTokens" /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log 2>/dev/null | tail -5
```

## Key Files Reference

| File | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | Model config, params, fallbacks, channels |
| `~/.openclaw/agents/main/agent/auth-profiles.json` | API key auth for model providers |
| `~/.openclaw/agents/main/sessions/sessions.json` | Session cache (skills snapshots) |
| `~/.openclaw/workspace/SOUL.md` | Personality, analytical depth, response structure |
| `~/.openclaw/workspace/MEMORY.md` | Long-term memory, portfolio context |
| `~/.openclaw/workspace/ANALYSIS.md` | Deep synthesis protocol reference |
| `~/.openclaw/workspace/IDENTITY.md` | Name, vibe, avatar |
| `~/.openclaw/workspace/AGENTS.md` | Behavioral rules, heartbeat, safety |
| `~/.openclaw/workspace/TOOLS.md` | Tool inventory, API notes |
| `~/.openclaw/cron/jobs.json` | Scheduled job configs and models |

## Tuning Cheat Sheet

| Param | Effect | Range | Current |
|-------|--------|-------|---------|
| `temperature` | Creativity vs safety | 0.0–2.0 | 0.9 |
| `maxTokens` | Response length cap | 1K–128K | 16384 |
| `top_p` | Token diversity | 0.0–1.0 | 0.92 |
| `presence_penalty` | Anti-repetition | -2.0–2.0 | 0.3 |
| `frequency_penalty` | Anti-word-repeat | -2.0–2.0 | not set |

**Rules of thumb:**
- Too factual/robotic → raise temperature (0.85–1.0)
- Too repetitive/listy → raise presence_penalty (0.3–0.5)
- Truncated responses → raise maxTokens
- Too wild/hallucinating → lower temperature, raise top_p
- Too safe/hedgy → edit SOUL.md, remove safety-heavy language
