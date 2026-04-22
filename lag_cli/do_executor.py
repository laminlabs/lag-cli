from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import nbformat


def find_plan_file(explicit_plan_file: Path | None = None) -> Path | None:
    """Find an explicit or best candidate markdown plan file."""
    if explicit_plan_file is not None:
        return explicit_plan_file.resolve()

    direct = Path("plan.md")
    if direct.exists():
        return direct.resolve()

    candidates = sorted(
        Path().glob("plan_*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0].resolve()
    return None


def extract_runnable_paths(plan_text: str, plan_dir: Path) -> list[Path]:
    """Extract python scripts and notebooks from markdown plan text."""
    candidates: list[str] = []
    seen: set[str] = set()

    for match in re.finditer(r"`([^`]+\.(?:py|ipynb))`", plan_text):
        candidates.append(match.group(1))

    for line in plan_text.splitlines():
        stripped = line.strip().lstrip("-* ").strip()
        if (
            stripped.endswith(".py") or stripped.endswith(".ipynb")
        ) and " " not in stripped:
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


def _execute_python(script_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "kind": "python_script",
        "path": str(script_path),
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _execute_notebook(notebook_path: Path) -> dict[str, Any]:
    nb = nbformat.read(notebook_path, as_version=4)
    globals_ns: dict[str, Any] = {}
    outputs: list[str] = []
    errors: list[str] = []
    for idx, cell in enumerate(nb.cells):
        if cell.cell_type != "code":
            continue
        source = str(cell.source or "")
        try:
            exec(compile(source, str(notebook_path), "exec"), globals_ns)  # noqa: S102
            outputs.append(f"cell_{idx}: ok")
        except Exception as exc:
            errors.append(f"cell_{idx}: {exc}")
            break
    return {
        "kind": "notebook",
        "path": str(notebook_path),
        "exit_code": 1 if errors else 0,
        "stdout": "\n".join(outputs)[-4000:],
        "stderr": "\n".join(errors)[-4000:],
    }


def execute_plan(*, prompt: str, plan_file: Path, run_uid: str) -> dict[str, Any]:
    plan_text = plan_file.read_text(encoding="utf-8")
    runnable_paths = extract_runnable_paths(plan_text, plan_file.parent)

    trace_events: list[dict[str, Any]] = [
        {
            "step": 0,
            "event": "plan_loaded",
            "plan_file": str(plan_file),
            "prompt": prompt,
            "runnables_detected": [str(path) for path in runnable_paths],
        }
    ]

    if not runnable_paths:
        return {
            "run_uid": run_uid,
            "trace_events": trace_events,
            "generated_file": None,
            "final_text": "No runnable script/notebook paths found in the plan.",
        }

    for idx, runnable_path in enumerate(runnable_paths, start=1):
        if not runnable_path.exists():
            trace_events.append(
                {
                    "step": idx,
                    "event": "runnable_missing",
                    "path": str(runnable_path),
                }
            )
            continue

        if runnable_path.suffix == ".ipynb":
            execution = _execute_notebook(runnable_path)
            event = "notebook_executed"
        else:
            execution = _execute_python(runnable_path)
            event = "script_executed"

        trace_events.append(
            {
                "step": idx,
                "event": event,
                **execution,
            }
        )

    failed = [
        event
        for event in trace_events
        if event.get("event") in {"script_executed", "notebook_executed"}
        and event.get("exit_code") != 0
    ]
    final_text = (
        f"Executed {len(runnable_paths)} runnables from plan; {len(failed)} failed."
        if runnable_paths
        else "No runnables executed."
    )
    return {
        "run_uid": run_uid,
        "trace_events": trace_events,
        "generated_file": None,
        "final_text": final_text,
    }
