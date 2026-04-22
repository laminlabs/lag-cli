from __future__ import annotations

import os
from pathlib import Path

import click
import lamindb as ln
from dotenv import load_dotenv

from .agent import run_agent
from .do_executor import execute_plan, find_plan_file
from .run_context import RunContext, create_run_uid
from .tracing import register_trace_and_outputs, save_trace_files


def _progress(message: str) -> None:
    click.echo(f"→ {message}")


def _flow_run_agent_mode(
    *,
    mode: str,
    prompt: str,
    output_file: Path | None,
    model: str,
    output_format: str,
    api_key: str,
) -> dict[str, str | None]:
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
    )
    result = run_agent(
        api_key=api_key,
        run_context=run_context,
        output_file=output_path,
        progress_callback=_progress,
    )

    trace_txt_path = Path("trace.txt")
    save_trace_files(
        trace_payload=result,
        trace_txt_path=trace_txt_path,
    )

    generated_file = result.get("generated_file")
    generated_path = Path(generated_file) if isinstance(generated_file, str) else None
    register_trace_and_outputs(
        run_uid=run_uid,
        trace_txt_path=trace_txt_path,
        generated_file=generated_path,
    )
    return {
        "run_uid": run_uid,
        "trace_path": str(trace_txt_path),
        "generated_path": str(generated_path) if generated_path else None,
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
    trace_txt_path = Path("trace.txt")
    save_trace_files(
        trace_payload=result,
        trace_txt_path=trace_txt_path,
    )
    register_trace_and_outputs(
        run_uid=run_uid,
        trace_txt_path=trace_txt_path,
        generated_file=None,
    )
    return {
        "run_uid": run_uid,
        "trace_path": str(trace_txt_path),
        "plan_path": str(plan_file),
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
@ln.flow("wDJpT3xdqjY8")
def main(
    prompt: str,
    plan_mode: bool,
    output_file: Path | None,
    model: str,
    output_format: str,
    plan_file: Path | None,
) -> None:
    """LAG CLI."""
    workspace_env_path = Path("~/llms.env").expanduser()
    load_dotenv(dotenv_path=workspace_env_path)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise click.ClickException("GEMINI_API_KEY not found in ~/llms.env")

    if plan_mode:
        outcome = _flow_run_agent_mode(
            mode="plan",
            prompt=prompt,
            output_file=output_file,
            model=model,
            output_format=output_format,
            api_key=api_key,
        )
        click.echo(f"run_uid={outcome['run_uid']}")
        click.echo(f"trace={outcome['trace_path']}")
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
        click.echo(f"trace={outcome['trace_path']}")
        click.echo(f"plan={outcome['plan_path']}")
        click.echo(str(outcome["final_text"]))
        return

    outcome = _flow_run_agent_mode(
        mode="do",
        prompt=prompt,
        output_file=output_file,
        model=model,
        output_format="py",
        api_key=api_key,
    )
    click.echo(f"run_uid={outcome['run_uid']}")
    click.echo(f"trace={outcome['trace_path']}")
    if outcome["generated_path"]:
        click.echo(f"generated={outcome['generated_path']}")
    if outcome["final_text"]:
        click.echo("\nFinal response:\n")
        click.echo(str(outcome["final_text"]))


if __name__ == "__main__":
    main()
