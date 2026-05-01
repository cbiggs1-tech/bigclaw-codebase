"""Patch style_compliance.py to use style_gates with AI reasoning for the weekly audit."""

filepath = "/home/cbiggs90/.openclaw/workspace/scripts/style_compliance.py"
with open(filepath, "r") as f:
    content = f.read()

# 1. Add import for style_gates after existing imports
old_import = "from bigclaw_retry import retry"
new_import = """from bigclaw_retry import retry
from style_gates import passes_style_gate"""

if "from style_gates import" not in content:
    content = content.replace(old_import, new_import)

# 2. Replace the per-holding check loop to use style_gates with AI reasoning
# The current audit manually checks require/reject rules inline.
# Replace with a call to passes_style_gate(context="holding_audit")

old_check_loop = """        # Check each holding against style requirements
        for h in holdings:
            ticker = h["ticker"]
            info = info_map.get(ticker, {})

            # Require checks
            for check_name, check_def in rules.get("require", {}).items():
                try:
                    passed = check_def["check"](info)
                    if not passed:
                        port_result["warnings"].append(
                            f"{ticker}: fails '{check_def['desc']}' requirement"
                        )
                except Exception:
                    pass  # Missing data, skip

            # Reject checks (these are violations)
            for check_name, check_def in rules.get("reject", {}).items():
                try:
                    triggered = check_def["check"](info)
                    if triggered:
                        port_result["violations"].append(
                            f"{ticker}: {check_def['desc']} — contradicts {rules['label']} thesis"
                        )
                except Exception:
                    pass"""

new_check_loop = """        # Check each holding against style gates (with AI reasoning for borderline cases)
        for h in holdings:
            ticker = h["ticker"]
            info = info_map.get(ticker, {})

            # Use the unified gate check — same gates as pre-buy, applied to current holdings
            gate_result = passes_style_gate(
                ticker, pname, info,
                context="holding_audit"
            )

            if gate_result["pass"]:
                if gate_result.get("ai_decision") == "ALLOW":
                    # AI overrode a borderline failure — note it as a pass with context
                    port_result["passes"].append(
                        f"{ticker}: borderline but AI approved — {gate_result.get('ai_reason', '')}"
                    )
                else:
                    port_result["passes"].append(f"{ticker}: passes style gate")
            elif gate_result.get("severity") == "reject":
                # Hard violation
                port_result["violations"].append(
                    f"{ticker}: {gate_result['reason']}"
                )
            else:
                # Borderline failure — AI was consulted and agreed to block
                ai_note = ""
                if gate_result.get("ai_decision") == "BLOCK":
                    ai_note = f" (AI confirmed: {gate_result.get('ai_reason', '')})"
                port_result["warnings"].append(
                    f"{ticker}: {gate_result['reason']}{ai_note}"
                )

            # Also run the legacy require/reject checks for any rules not covered by gates
            for check_name, check_def in rules.get("require", {}).items():
                try:
                    passed = check_def["check"](info)
                    if not passed:
                        msg = f"{ticker}: fails '{check_def['desc']}' requirement"
                        if msg not in port_result["warnings"]:
                            port_result["warnings"].append(msg)
                except Exception:
                    pass

            for check_name, check_def in rules.get("reject", {}).items():
                try:
                    triggered = check_def["check"](info)
                    if triggered:
                        msg = f"{ticker}: {check_def['desc']} — contradicts {rules['label']} thesis"
                        if msg not in port_result["violations"]:
                            port_result["violations"].append(msg)
                except Exception:
                    pass"""

content = content.replace(old_check_loop, new_check_loop)

with open(filepath, "w") as f:
    f.write(content)
print("style_compliance.py patched with AI-powered gate checks for weekly audit")
