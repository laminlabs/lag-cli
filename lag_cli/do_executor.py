from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def extract_script_paths(plan_text: str, plan_dir: Path) -> list[Path]:
    """Extract python script paths from markdown plan text."""
    candidates: list[str] = []
    seen: set[str] = set()

    for match in re.finditer(r"`([^`]+\.py)`", plan_text):
        candidates.append(match.group(1))

    for line in plan_text.splitlines():
        stripped = line.strip().lstrip("-* ").strip()
        if stripped.endswith(".py") and " " not in stripped:
            candidates.append(stripped)

    paths: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if not path.is_absolute():
            path = (plan_dir / path).resolve()
        paths.append(path)
    return paths


def execute_plan(*, prompt: str, plan_file: Path, run_uid: str) -> dict[str, Any]:
    plan_text = plan_file.read_text(encoding="utf-8")
    script_paths = extract_script_paths(plan_text, plan_file.parent)

    trace_events: list[dict[str, Any]] = [
        {
            "step": 0,
            "event": "plan_loaded",
            "plan_file": str(plan_file),
            "prompt": prompt,
            "scripts_detected": [str(path) for path in script_paths],
        }
    ]

    if not script_paths:
        return {
            "run_uid": run_uid,
            "trace_events": trace_events,
            "generated_file": None,
            "final_text": "No script paths found in the plan.",
        }

    for idx, script_path in enumerate(script_paths, start=1):
        if not script_path.exists():
            trace_events.append(
                {
                    "step": idx,
                    "event": "script_missing",
                    "script": str(script_path),
                }
            )
            continue
        completed = subprocess.run(
            [sys.executable, str(script_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        trace_events.append(
            {
                "step": idx,
                "event": "script_executed",
                "script": str(script_path),
                "exit_code": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        )

    failed = [
        event
        for event in trace_events
        if event.get("event") == "script_executed" and event.get("exit_code") != 0
    ]
    final_text = (
        f"Executed {len(script_paths)} scripts from plan; {len(failed)} failed."
        if script_paths
        else "No scripts executed."
    )
    return {
        "run_uid": run_uid,
        "trace_events": trace_events,
        "generated_file": None,
        "final_text": final_text,
    }
