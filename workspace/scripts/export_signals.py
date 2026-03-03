#!/usr/bin/env python3
"""Export signals and macro data to JSON for the BigClaw website."""

import json
import os
import subprocess
import sys
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.expanduser("~/bigclaw-ai/docs/data")

def run_script(cmd, output_file, label):
    """Run a script, capture JSON stdout, save to file."""
    print(f"[export_signals] Running {label}...", file=sys.stderr)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600,
            cwd=SCRIPTS_DIR,
            env={**os.environ}
        )
        if result.returncode != 0:
            print(f"  ⚠ {label} failed (exit {result.returncode})", file=sys.stderr)
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}", file=sys.stderr)
            return False

        stdout = result.stdout.strip()
        if not stdout:
            print(f"  ⚠ {label} produced no output", file=sys.stderr)
            return False

        # Validate JSON
        data = json.loads(stdout)
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"  ✅ {label} → {output_file}", file=sys.stderr)
        return True

    except json.JSONDecodeError as e:
        print(f"  ⚠ {label} output is not valid JSON: {e}", file=sys.stderr)
        # Save raw output for debugging
        with open(output_file + ".raw", "w") as f:
            f.write(stdout)
        return False
    except subprocess.TimeoutExpired:
        print(f"  ⚠ {label} timed out (600s)", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  ⚠ {label} error: {e}", file=sys.stderr)
        return False


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    results = {}

    # Decision Engine → signals.json
    results["signals"] = run_script(
        [sys.executable, "decision_engine.py", "--json"],
        os.path.join(DATA_DIR, "signals.json"),
        "Decision Engine"
    )

    # Macro Scanner → macro.json
    results["macro"] = run_script(
        [sys.executable, "macro_scanner.py", "--json"],
        os.path.join(DATA_DIR, "macro.json"),
        "Macro Scanner"
    )

    # Update metadata
    metadata_path = os.path.join(DATA_DIR, "metadata.json")
    try:
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        metadata = {}

    metadata["signals_updated"] = datetime.now().isoformat()
    metadata["signals_export_results"] = results

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  ✅ metadata → {metadata_path}", file=sys.stderr)

    success = all(results.values())
    print(f"\n[export_signals] Done. {'All succeeded ✅' if success else 'Some failed ⚠'}", file=sys.stderr)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
