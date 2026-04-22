from __future__ import annotations

import os
from pathlib import Path

import click
import lamindb as ln
from dotenv import load_dotenv

from .agent import run_agent
from .do_executor import execute_plan, execute_runnable_paths, find_plan_file
from .output_saver import save_generated_tool_files
from .run_context import RunContext, create_run_uid


def _progress(message: str) -> None:
    click.echo(f"→ {message}")


def _parse_generated_paths(generated_paths_csv: str) -> list[Path]:
    return [
        Path(path_str).resolve()
        for path_str in generated_paths_csv.split(",")
        if path_str.strip()
    ]


def _print_generated_tool_contents(paths: list[Path]) -> None:
    seen: set[Path] = set()
    for path in paths:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        click.echo(f"\n--- generated tool: {path} ---")
        content = path.read_text(encoding="utf-8")
        click.echo(content)
        click.echo("--- end generated tool ---")


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
    help="Optional path to plan file to execute in default do mode.",
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
    help="Auto-confirm execution of newly generated tools in default do mode.",
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
) -> None:
    """LAG CLI."""
    if plan_mode:
        outcome = _flow_run_agent_mode(
            mode="plan",
            prompt=prompt,
            output_file=output_file,
            model=model,
            output_format=output_format,
            track_outputs=not no_track,
        )
        click.echo(f"run_uid={outcome['run_uid']}")
        if outcome["generated_path"]:
            click.echo(f"generated={outcome['generated_path']}")
        if outcome["final_text"]:
            click.echo("\nFinal response:\n")
            click.echo(str(outcome["final_text"]))
        return

    chosen_plan_file = find_plan_file(plan_file)
    if chosen_plan_file is not None:
        outcome = _flow_execute_plan(
            prompt=prompt,
            plan_file=chosen_plan_file,
        )
        click.echo(f"run_uid={outcome['run_uid']}")
        click.echo(f"plan={outcome['plan_path']}")
        click.echo(str(outcome["final_text"]))
        return

    outcome = _flow_run_agent_mode(
        mode="do",
        prompt=prompt,
        output_file=output_file,
        model=model,
        output_format="py",
        track_outputs=not no_track,
    )
    click.echo(f"run_uid={outcome['run_uid']}")
    if outcome["generated_path"]:
        click.echo(f"generated={outcome['generated_path']}")
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
            click.echo(f"exec_run_uid={exec_outcome['run_uid']}")
            click.echo(str(exec_outcome["final_text"]))
        else:
            click.echo("Skipped execution of newly generated tools.")
    if outcome["final_text"]:
        click.echo("\nFinal response:\n")
        click.echo(str(outcome["final_text"]))


if __name__ == "__main__":
    main()
