from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

import requests

from .context import get_lamindb_skill, get_local_skill
from .writer import (
    write_from_template,
    write_jupyter_notebook,
    write_markdown_plan,
    write_python_script,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from .run_context import RunContext

PLAN_SYSTEM_INSTRUCTION = (
    "You are a planning and generation agent. For each prompt, you may read skills, "
    "query LaminDB, write markdown plans, generate scripts/notebooks from scratch, "
    "or create outputs from templates."
)

DO_SYSTEM_INSTRUCTION = (
    "You are a scientific coding agent. First retrieve relevant context when useful, "
    "then write runnable analysis code. For every output file your script/notebook writes, "
    "explicitly call ln.Artifact('<output_path>').save() in the generated code."
)


def _function_declarations(mode: str, output_format: str) -> list[dict[str, Any]]:
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
    if mode == "plan":
        declarations.extend(
            [
                {
                    "name": "write_markdown_plan",
                    "description": "Write a markdown planning document.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "filename": {"type": "STRING"},
                            "markdown": {"type": "STRING"},
                        },
                        "required": ["filename", "markdown"],
                    },
                },
                {
                    "name": "write_from_template",
                    "description": "Create a file from an existing template path.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "template_path": {"type": "STRING"},
                            "filename": {"type": "STRING"},
                        },
                        "required": ["template_path", "filename"],
                    },
                },
            ]
        )
    if output_format == "ipynb" or mode == "plan":
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
    if output_format == "py" or mode == "plan":
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


def _tool_payload(mode: str, output_format: str) -> list[dict[str, Any]]:
    return [{"functionDeclarations": _function_declarations(mode, output_format)}]


def _extract_text(parts: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for part in parts:
        text = part.get("text")
        if isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunks).strip()


def _post_generate_content(
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_seconds: int = 120,
    max_attempts: int = 4,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key,
    }
    backoff_seconds = 1.0
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            if progress_callback is not None:
                progress_callback(f"gemini request attempt {attempt}/{max_attempts}")
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
            )
            status = response.status_code
            if status in {429, 500, 502, 503, 504} and attempt < max_attempts:
                if progress_callback is not None:
                    progress_callback(
                        f"gemini transient status {status}, retrying in {backoff_seconds:.1f}s"
                    )
                time.sleep(backoff_seconds)
                backoff_seconds *= 2
                continue
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= max_attempts:
                break
            if progress_callback is not None:
                progress_callback(
                    f"gemini request failed ({exc.__class__.__name__}), retrying in {backoff_seconds:.1f}s"
                )
            time.sleep(backoff_seconds)
            backoff_seconds *= 2

    if isinstance(last_error, requests.HTTPError) and last_error.response is not None:
        status = last_error.response.status_code
        body_preview = last_error.response.text[:1000]
        raise RuntimeError(
            f"Gemini API request failed after retries (status={status}). "
            f"Response preview: {body_preview}"
        ) from last_error
    raise RuntimeError("Gemini API request failed after retries.") from last_error


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
            track_outputs=run_context.track_outputs,
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
            track_outputs=run_context.track_outputs,
        )
    if name == "write_markdown_plan":
        filename = str(args.get("filename") or default_output_file)
        return write_markdown_plan(
            markdown=str(args.get("markdown", "")),
            filename=filename,
            run_uid=run_context.run_uid,
        )
    if name == "write_from_template":
        filename = str(args.get("filename") or default_output_file)
        return write_from_template(
            template_path=str(args.get("template_path", "")),
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
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    system_instruction = (
        PLAN_SYSTEM_INSTRUCTION if run_context.mode == "plan" else DO_SYSTEM_INSTRUCTION
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{run_context.model}:generateContent"
    )
    contents: list[dict[str, Any]] = [
        {
            "role": "user",
            "parts": [
                {"text": f"{system_instruction}\n\nPrompt: {run_context.prompt}"},
            ],
        }
    ]
    trace_events: list[dict[str, Any]] = []
    generated_file: str | None = None
    generated_files: list[str] = []
    final_text = ""
    if progress_callback is not None:
        progress_callback(f"mode={run_context.mode} model={run_context.model}")
        progress_callback(f"prompt: {run_context.prompt}")

    for step in range(1, max_steps + 1):
        if progress_callback is not None:
            progress_callback(f"step {step}: waiting for model response")
        payload = {
            "contents": contents,
            "tools": _tool_payload(run_context.mode, run_context.output_format),
            "generationConfig": {"temperature": 0.2},
        }
        data = _post_generate_content(
            url=url,
            api_key=api_key,
            payload=payload,
            progress_callback=progress_callback,
        )
        candidate = data.get("candidates", [{}])[0]
        response_message = candidate.get("content", {})
        contents.append(response_message)
        parts = response_message.get("parts", [])
        text_preview = _extract_text(parts)
        if progress_callback is not None and text_preview:
            preview = (
                text_preview if len(text_preview) <= 300 else f"{text_preview[:300]}..."
            )
            progress_callback(f"step {step}: model text: {preview}")

        trace_events.append({"step": step, "model_response": response_message})
        tool_calls = [p.get("functionCall") for p in parts if "functionCall" in p]
        if not tool_calls:
            final_text = _extract_text(parts)
            if progress_callback is not None:
                progress_callback("model finished without further tool calls")
            break

        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            name = str(tool_call.get("name", ""))
            args = tool_call.get("args", {})
            if not isinstance(args, dict):
                args = {}
            if progress_callback is not None:
                progress_callback(
                    f"step {step}: tool call -> {name} args={json.dumps(args)}"
                )

            result = _dispatch_tool(
                name=name,
                args=args,
                run_context=run_context,
                default_output_file=output_file,
            )
            generated = result.get("file")
            if isinstance(generated, str) and generated:
                generated_file = generated
                if generated not in generated_files:
                    generated_files.append(generated)
                if progress_callback is not None:
                    progress_callback(f"step {step}: wrote file {generated}")

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
            if progress_callback is not None:
                status = result.get("status", "ok")
                progress_callback(f"step {step}: tool result status={status}")

    return {
        "run_uid": run_context.run_uid,
        "contents": contents,
        "trace_events": trace_events,
        "generated_file": generated_file,
        "generated_files": generated_files,
        "final_text": final_text,
    }


def write_trace_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
