from __future__ import annotations

import os
from pathlib import Path

import click
import lamindb as ln
from dotenv import load_dotenv

from .agent import run_agent
from .do_executor import execute_plan
from .run_context import RunContext, create_run_uid
from .tracing import register_trace_and_outputs, save_trace_files


@click.group()
def main() -> None:
    """LAG CLI."""


def _run_plan_mode(
    *,
    prompt: str,
    output_file: Path | None,
    model: str,
    output_format: str,
) -> None:
    workspace_env_path = Path("~/work/llms.env").expanduser()
    load_dotenv(dotenv_path=workspace_env_path)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise click.ClickException("GEMINI_API_KEY not found in ~/work/.env")

    ln.track()
    lamindb_run_uid = str(getattr(ln.context.run, "uid", "") or "") or None
    run_uid = create_run_uid(lamindb_run_uid)

    suffix = "md" if output_format == "md" else output_format
    default_name = f"plan_{run_uid}.{suffix}"
    output_path = output_file or Path(default_name)

    run_context = RunContext(
        run_uid=run_uid,
        mode="plan",
        prompt=prompt,
        model=model,
        output_format=output_format,
    )
    result = run_agent(
        api_key=api_key,
        run_context=run_context,
        output_file=output_path,
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
    ln.finish()

    click.echo(f"run_uid={run_uid}")
    click.echo(f"trace={trace_txt_path}")
    if generated_path:
        click.echo(f"generated={generated_path}")
    final_text = str(result.get("final_text", "") or "").strip()
    if final_text:
        click.echo("\nFinal response:\n")
        click.echo(final_text)


@main.group("plan")
def plan_group() -> None:
    """Planning and generation workflows."""


@plan_group.command("run")
@click.option("--prompt", required=True, type=str, help="User prompt.")
@click.option("--output-file", type=click.Path(path_type=Path), default=None)
@click.option("--model", type=str, default="gemini-2.5-flash", show_default=True)
@click.option(
    "--output-format",
    type=click.Choice(["md", "py", "ipynb"], case_sensitive=False),
    default="md",
    show_default=True,
)
def plan_run(
    prompt: str,
    output_file: Path | None,
    model: str,
    output_format: str,
) -> None:
    _run_plan_mode(
        prompt=prompt,
        output_file=output_file,
        model=model,
        output_format=output_format,
    )


@main.group("do")
def do_group() -> None:
    """Execution-focused workflows."""


@do_group.command("run")
@click.option("--prompt", required=True, type=str, help="User prompt.")
@click.option(
    "--plan-file",
    required=True,
    type=click.Path(path_type=Path, exists=True),
    help="Path to markdown plan file containing script paths.",
)
def do_run(
    prompt: str,
    plan_file: Path,
) -> None:
    ln.track()
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
    ln.finish()

    click.echo(f"run_uid={run_uid}")
    click.echo(f"trace={trace_txt_path}")
    click.echo(str(result.get("final_text", "")))


if __name__ == "__main__":
    main()
