from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import requests

from .context import get_lamindb_skill, get_local_skill
from .writer import write_jupyter_notebook, write_python_script

if TYPE_CHECKING:
    from pathlib import Path

    from .run_context import RunContext

SYSTEM_INSTRUCTION = (
    "You are a scientific coding agent. First retrieve relevant context when useful, "
    "then write runnable analysis code as either a Python script or Jupyter notebook."
)


def _function_declarations(output_format: str) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = [
        {
            "name": "get_local_skill",
            "description": "Find relevant local SKILL.md docs for a topic.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "topic": {"type": "STRING"},
                    "skills_root": {"type": "STRING"},
                },
                "required": ["topic"],
            },
        },
        {
            "name": "get_lamindb_skill",
            "description": "Query laminlabs/biomed-skills for relevant transforms/artifacts.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {"type": "STRING"},
                    "limit": {"type": "NUMBER"},
                },
                "required": ["query"],
            },
        },
    ]
    if output_format == "ipynb":
        declarations.append(
            {
                "name": "write_jupyter_notebook",
                "description": "Write an ipynb notebook file with markdown/code cells.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "filename": {"type": "STRING"},
                        "cells": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "type": {"type": "STRING"},
                                    "content": {"type": "STRING"},
                                },
                                "required": ["type", "content"],
                            },
                        },
                    },
                    "required": ["filename", "cells"],
                },
            }
        )
    else:
        declarations.append(
            {
                "name": "write_python_script",
                "description": "Write a runnable Python script file.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "filename": {"type": "STRING"},
                        "code": {"type": "STRING"},
                    },
                    "required": ["filename", "code"],
                },
            }
        )
    return declarations


def _tool_payload(output_format: str) -> list[dict[str, Any]]:
    return [{"functionDeclarations": _function_declarations(output_format)}]


def _extract_text(parts: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for part in parts:
        text = part.get("text")
        if isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunks).strip()


def _dispatch_tool(
    *,
    name: str,
    args: dict[str, Any],
    run_context: RunContext,
    default_output_file: Path,
) -> dict[str, Any]:
    if name == "get_local_skill":
        return get_local_skill(
            topic=str(args.get("topic", "")),
            skills_root=args.get("skills_root"),
            run_uid=run_context.run_uid,
        )
    if name == "get_lamindb_skill":
        return get_lamindb_skill(
            query=str(args.get("query", "")),
            limit=int(args.get("limit", 5)),
            run_uid=run_context.run_uid,
        )
    if name == "write_python_script":
        filename = str(args.get("filename") or default_output_file)
        return write_python_script(
            code=str(args.get("code", "")),
            filename=filename,
            run_uid=run_context.run_uid,
        )
    if name == "write_jupyter_notebook":
        filename = str(args.get("filename") or default_output_file)
        cells = args.get("cells")
        if not isinstance(cells, list):
            cells = [{"type": "code", "content": ""}]
        return write_jupyter_notebook(
            cells=cells,
            filename=filename,
            run_uid=run_context.run_uid,
        )
    return {
        "status": "error",
        "message": f"Unknown tool: {name}",
        "run_uid": run_context.run_uid,
    }


def run_agent(
    *,
    api_key: str,
    run_context: RunContext,
    output_file: Path,
    max_steps: int = 20,
) -> dict[str, Any]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{run_context.model}:generateContent?key={api_key}"
    )
    contents: list[dict[str, Any]] = [
        {
            "role": "user",
            "parts": [
                {"text": f"{SYSTEM_INSTRUCTION}\n\nTask: {run_context.task}"},
            ],
        }
    ]
    trace_events: list[dict[str, Any]] = []
    generated_file: str | None = None
    final_text = ""

    for step in range(1, max_steps + 1):
        payload = {
            "contents": contents,
            "tools": _tool_payload(run_context.output_format),
            "generationConfig": {"temperature": 0.2},
        }
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        candidate = data.get("candidates", [{}])[0]
        response_message = candidate.get("content", {})
        contents.append(response_message)
        parts = response_message.get("parts", [])

        trace_events.append({"step": step, "model_response": response_message})
        tool_calls = [p.get("functionCall") for p in parts if "functionCall" in p]
        if not tool_calls:
            final_text = _extract_text(parts)
            break

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            name = str(tool_call.get("name", ""))
            args = tool_call.get("args", {})
            if not isinstance(args, dict):
                args = {}

            result = _dispatch_tool(
                name=name,
                args=args,
                run_context=run_context,
                default_output_file=output_file,
            )
            generated = result.get("file")
            if isinstance(generated, str) and generated:
                generated_file = generated

            trace_events.append(
                {
                    "step": step,
                    "tool": name,
                    "tool_args": args,
                    "tool_result": result,
                }
            )
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": name,
                                "response": result,
                            }
                        }
                    ],
                }
            )

    return {
        "run_uid": run_context.run_uid,
        "contents": contents,
        "trace_events": trace_events,
        "generated_file": generated_file,
        "final_text": final_text,
    }


def write_trace_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
