from __future__ import annotations

import os
import re
from pathlib import Path

import click
import lamindb as ln
from dotenv import load_dotenv
from lamin_utils import logger

from .agent import run_agent
from .do_executor import execute_plan, execute_runnable_paths, find_plan_file
from .output_saver import save_generated_tool_files
from .run_context import RunContext, create_run_uid

_STEP_PATTERN = re.compile(r"^step (\d+):\s*(.*)$")
_COLOR_ENABLED = os.getenv("NO_COLOR") is None


def _secho(
    message: str,
    *,
    fg: str | None = None,
    bold: bool = False,
    nl: bool = True,
) -> None:
    click.secho(message, fg=fg, bold=bold, nl=nl, color=_COLOR_ENABLED)


def _echo_info(message: str) -> None:
    _secho(f"→ {message}", fg="bright_black")


def _echo_success(message: str) -> None:
    _secho(f"✓ {message}", fg="green")


def _echo_warning(message: str) -> None:
    _secho(f"! {message}", fg="yellow")


def _echo_section(title: str) -> None:
    _secho(f"\n[{title}]", fg="bright_cyan", bold=True)


def _echo_key_value(key: str, value: str, *, value_color: str = "white") -> None:
    _secho("→ ", nl=False, fg="bright_black")
    _secho(f"{key}=", nl=False, fg="bright_black")
    _secho(value, fg=value_color)


def _progress(message: str) -> None:
    if message.startswith("mode="):
        pretty_message = message.replace("mode=do", "mode=default")
        _echo_info(pretty_message)
        return
    if message.startswith("prompt: "):
        _secho("→ prompt: ", nl=False, fg="bright_black")
        _secho(message.removeprefix("prompt: "), fg="cyan")
        return
    if message.startswith("gemini request attempt"):
        _secho(f"→ {message}", fg="magenta")
        return
    if message.startswith("gemini transient status"):
        _secho(f"→ {message}", fg="yellow")
        return
    if message.startswith("gemini request failed"):
        _secho(f"→ {message}", fg="red")
        return
    if message == "model finished without further tool calls":
        _secho(f"→ {message}", fg="green")
        return

    step_match = _STEP_PATTERN.match(message)
    if step_match is None:
        _echo_info(message)
        return

    step, detail = step_match.groups()
    _secho(f"→ step {step}: ", nl=False, fg="bright_black")
    if detail.startswith("waiting for model response"):
        _secho(detail, fg="blue")
    elif detail.startswith("model text: "):
        _secho("model text: ", nl=False, fg="blue")
        _secho(detail.removeprefix("model text: "), fg="white")
    elif detail.startswith("tool call -> "):
        _secho("tool call -> ", nl=False, fg="magenta")
        _secho(detail.removeprefix("tool call -> "), fg="white")
    elif detail.startswith("wrote file "):
        _secho(detail, fg="green")
    elif detail.startswith("tool result status="):
        status = detail.removeprefix("tool result status=")
        color = "green" if status == "success" else "yellow"
        _secho("tool result status=", nl=False, fg="bright_black")
        _secho(status, fg=color)
    else:
        _secho(detail, fg="white")


def _parse_generated_paths(generated_paths_csv: str) -> list[Path]:
    return [
        Path(path_str).resolve()
        for path_str in generated_paths_csv.split(",")
        if path_str.strip()
    ]


def _set_current_project_env(project: str | None) -> str | None:
    if project:
        os.environ["LAMIN_CURRENT_PROJECT"] = project
    return project


def _project_option_callback(
    _ctx: click.Context, _param: click.Parameter, value: str | None
) -> str | None:
    return _set_current_project_env(value)


def _warn_if_missing_project(project: str | None) -> None:
    if not project:
        logger.warning(
            "No --project was provided; LAMIN_CURRENT_PROJECT is unset for this run."
        )


def _print_generated_tool_contents(paths: list[Path]) -> None:
    seen: set[Path] = set()
    for path in paths:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        _echo_section(f"Generated Tool {path.name}")
        _secho(str(path), fg="bright_black")
        content = path.read_text(encoding="utf-8")
        _secho(content, fg="white")
        _secho("--- end generated tool ---", fg="bright_black")


def _flow_run_agent_mode(
    *,
    mode: str,
    prompt: str,
    output_file: Path | None,
    model: str,
    output_format: str,
    track_outputs: bool,
) -> dict[str, str | None]:
    workspace_env_path = Path("~/llms.env").expanduser()
    load_dotenv(dotenv_path=workspace_env_path)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise click.ClickException("GEMINI_API_KEY not found in ~/llms.env")

    lamindb_run_uid = str(getattr(ln.context.run, "uid", "") or "") or None
    run_uid = create_run_uid(lamindb_run_uid)

    suffix = "md" if output_format == "md" else output_format
    default_name = f"{mode}_{run_uid}.{suffix}"
    output_path = output_file or Path(default_name)

    run_context = RunContext(
        run_uid=run_uid,
        mode=mode,
        prompt=prompt,
        model=model,
        output_format=output_format,
        track_outputs=track_outputs,
    )
    result = run_agent(
        api_key=api_key,
        run_context=run_context,
        output_file=output_path,
        progress_callback=_progress,
    )

    generated_file = result.get("generated_file")
    generated_files = [
        path_str
        for path_str in result.get("generated_files", [])
        if isinstance(path_str, str) and path_str
    ]
    if mode == "plan":
        save_generated_tool_files(generated_files)
    return {
        "run_uid": run_uid,
        "generated_path": generated_file if isinstance(generated_file, str) else None,
        "generated_paths": ",".join(generated_files),
        "final_text": str(result.get("final_text", "") or "").strip(),
    }


def _flow_execute_plan(
    prompt: str,
    plan_file: Path,
) -> dict[str, str | None]:
    lamindb_run_uid = str(getattr(ln.context.run, "uid", "") or "") or None
    run_uid = create_run_uid(lamindb_run_uid)

    result = execute_plan(
        prompt=prompt,
        plan_file=plan_file,
        run_uid=run_uid,
    )
    return {
        "run_uid": run_uid,
        "plan_path": str(plan_file),
        "final_text": str(result.get("final_text", "")),
    }


def _flow_execute_generated(
    *,
    prompt: str,
    generated_paths_csv: str,
) -> dict[str, str | None]:
    lamindb_run_uid = str(getattr(ln.context.run, "uid", "") or "") or None
    run_uid = create_run_uid(lamindb_run_uid)
    runnable_paths = _parse_generated_paths(generated_paths_csv)
    result = execute_runnable_paths(
        prompt=prompt,
        runnable_paths=runnable_paths,
        run_uid=run_uid,
        source="generated_outputs",
    )
    return {
        "run_uid": run_uid,
        "final_text": str(result.get("final_text", "")),
    }


@click.command()
@click.option("--prompt", required=True, type=str, help="User prompt.")
@click.option(
    "--plan",
    "plan_mode",
    is_flag=True,
    help="Switch to planning mode (plan generation).",
)
@click.option("--output-file", type=click.Path(path_type=Path), default=None)
@click.option("--model", type=str, default="gemini-flash-latest", show_default=True)
@click.option(
    "--output-format",
    type=click.Choice(["md", "py", "ipynb"], case_sensitive=False),
    default="md",
    show_default=True,
    help="Used in --plan mode; ignored otherwise.",
)
@click.option(
    "--plan-file",
    type=click.Path(path_type=Path, exists=True),
    default=None,
    help="Optional path to plan file to execute in default mode.",
)
@click.option(
    "--no-track",
    is_flag=True,
    help="Disable automatic insertion of ln.track()/ln.finish() in generated scripts/notebooks.",
)
@click.option(
    "--yes",
    "auto_confirm_execute",
    is_flag=True,
    help="Auto-confirm execution of newly generated tools in default mode.",
)
@click.option(
    "--project",
    type=str,
    default=None,
    callback=_project_option_callback,
    help="Project name to set as LAMIN_CURRENT_PROJECT for the initiated run.",
)
@ln.flow("wDJpT3xdqjY8")
def main(
    prompt: str,
    plan_mode: bool,
    output_file: Path | None,
    model: str,
    output_format: str,
    plan_file: Path | None,
    no_track: bool,
    auto_confirm_execute: bool,
    project: str | None,
) -> None:
    """LAG CLI."""
    _warn_if_missing_project(project)
    if plan_mode:
        _echo_section("User Input")
        _echo_key_value("prompt", prompt, value_color="cyan")
        _echo_key_value("mode", "plan", value_color="bright_cyan")
        if project:
            _echo_key_value("project", project, value_color="bright_green")
        outcome = _flow_run_agent_mode(
            mode="plan",
            prompt=prompt,
            output_file=output_file,
            model=model,
            output_format=output_format,
            track_outputs=not no_track,
        )
        _echo_section("Run")
        _echo_key_value("run_uid", str(outcome["run_uid"]), value_color="green")
        if outcome["generated_path"]:
            _echo_key_value(
                "generated",
                str(outcome["generated_path"]),
                value_color="bright_magenta",
            )
        if outcome["final_text"]:
            _echo_section("Model Output")
            _secho(str(outcome["final_text"]), fg="white")
        return

    chosen_plan_file = find_plan_file(plan_file)
    if chosen_plan_file is not None:
        _echo_section("User Input")
        _echo_key_value("prompt", prompt, value_color="cyan")
        _echo_key_value("mode", "execute-plan", value_color="bright_cyan")
        if project:
            _echo_key_value("project", project, value_color="bright_green")
        outcome = _flow_execute_plan(
            prompt=prompt,
            plan_file=chosen_plan_file,
        )
        _echo_section("Run")
        _echo_key_value("run_uid", str(outcome["run_uid"]), value_color="green")
        _echo_key_value("plan", str(outcome["plan_path"]), value_color="magenta")
        _secho(str(outcome["final_text"]), fg="white")
        return

    _echo_section("User Input")
    _echo_key_value("prompt", prompt, value_color="cyan")
    _echo_key_value("mode", "default", value_color="bright_cyan")
    if project:
        _echo_key_value("project", project, value_color="bright_green")
    outcome = _flow_run_agent_mode(
        mode="do",
        prompt=prompt,
        output_file=output_file,
        model=model,
        output_format="py",
        track_outputs=not no_track,
    )
    _echo_section("Run")
    _echo_key_value("run_uid", str(outcome["run_uid"]), value_color="green")
    if outcome["generated_path"]:
        _echo_key_value(
            "generated",
            str(outcome["generated_path"]),
            value_color="bright_magenta",
        )
    if outcome["generated_paths"]:
        generated_paths_csv = str(outcome["generated_paths"])
        generated_paths = _parse_generated_paths(generated_paths_csv)
        _print_generated_tool_contents(generated_paths)
        should_execute = auto_confirm_execute or click.confirm(
            "Execute newly generated tool files now?",
            default=True,
        )
        if should_execute:
            exec_outcome = _flow_execute_generated(
                prompt=prompt,
                generated_paths_csv=generated_paths_csv,
            )
            _echo_key_value(
                "exec_run_uid",
                str(exec_outcome["run_uid"]),
                value_color="green",
            )
            _secho(str(exec_outcome["final_text"]), fg="white")
        else:
            _echo_warning("Skipped execution of newly generated tools.")
    if outcome["final_text"]:
        _echo_section("Model Output")
        _secho(str(outcome["final_text"]), fg="white")


if __name__ == "__main__":
    main()
