from __future__ import annotations

import subprocess
from pathlib import Path

import click
import lamindb as ln


def save_generated_artifact(path_str: str | None, run_uid: str) -> None:
    if not path_str:
        return
    path = Path(path_str)
    if not path.exists():
        return
    ln.Artifact(
        str(path),
        description=f"Generated analysis output (run_uid={run_uid})",
    ).save()


def save_generated_tool_files(paths: list[str]) -> None:
    seen: set[str] = set()
    for path_str in paths:
        if not path_str or path_str in seen:
            continue
        seen.add(path_str)
        path = Path(path_str)
        if not path.exists():
            continue
        completed = subprocess.run(
            ["lamin", "save", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            raise click.ClickException(
                f"Failed to save generated tool file via lamin save: {path}. {stderr}"
            )
