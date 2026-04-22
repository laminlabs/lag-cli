from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(slots=True)
class RunContext:
    run_uid: str
    mode: str
    prompt: str
    model: str
    output_format: str
    track_outputs: bool = True


def create_run_uid(lamindb_run_uid: str | None = None) -> str:
    if lamindb_run_uid:
        return str(lamindb_run_uid)
    return f"agent-{uuid4().hex[:12]}"
