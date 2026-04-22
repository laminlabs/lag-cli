from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import lamindb as ln

if TYPE_CHECKING:
    from pathlib import Path


def render_trace_text(trace_payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"run_uid: {trace_payload.get('run_uid', '')}")
    lines.append("")
    final_text = str(trace_payload.get("final_text", "") or "").strip()
    if final_text:
        lines.append("final_response:")
        lines.append(final_text)
        lines.append("")

    lines.append("events:")
    for event in trace_payload.get("trace_events", []):
        step = event.get("step", "?")
        tool = event.get("tool")
        if tool:
            lines.append(f"- step {step}: tool={tool}")
            args = json.dumps(event.get("tool_args", {}), ensure_ascii=False)
            result = json.dumps(event.get("tool_result", {}), ensure_ascii=False)
            lines.append(f"  args: {args}")
            lines.append(f"  result: {result}")
        else:
            lines.append(f"- step {step}: model_response")
    return "\n".join(lines) + "\n"


def save_trace_files(
    *,
    trace_payload: dict[str, Any],
    trace_txt_path: Path,
    trace_json_path: Path | None = None,
) -> None:
    trace_txt_path.write_text(render_trace_text(trace_payload), encoding="utf-8")
    if trace_json_path is not None:
        trace_json_path.write_text(
            json.dumps(trace_payload, indent=2), encoding="utf-8"
        )


def register_trace_and_outputs(
    *,
    run_uid: str,
    trace_txt_path: Path,
    generated_file: Path | None,
    trace_json_path: Path | None = None,
) -> None:
    if generated_file and generated_file.exists():
        ln.Artifact(
            str(generated_file),
            description=f"Generated analysis output (run_uid={run_uid})",
        ).save()

    if trace_json_path and trace_json_path.exists():
        ln.Artifact(
            str(trace_json_path),
            description=f"Gemini trace json (run_uid={run_uid})",
        ).save()

    report_artifact = ln.Artifact(
        str(trace_txt_path),
        description=f"Gemini trace report (run_uid={run_uid})",
        run=False,
        kind="__lamindb_run__",
    ).save()
    if ln.context.run is not None:
        ln.context.run.report = report_artifact
        ln.context.run.save()
