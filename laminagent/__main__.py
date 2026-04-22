from __future__ import annotations

import os
from pathlib import Path

import click
import lamindb as ln
from dotenv import load_dotenv

from .agent import run_agent
from .run_context import RunContext, create_run_uid
from .tracing import register_trace_and_outputs, save_trace_files


@click.group()
def main() -> None:
    """LaminAgent CLI."""


@main.command("run")
@click.option("--task", required=True, type=str, help="Analysis task prompt.")
@click.option(
    "--output-format",
    type=click.Choice(["py", "ipynb"], case_sensitive=False),
    default="py",
    show_default=True,
)
@click.option("--output-file", type=click.Path(path_type=Path), default=None)
@click.option("--model", type=str, default="gemini-2.5-flash", show_default=True)
@click.option(
    "--trace-json",
    is_flag=True,
    help="Also write trace.json for machine debugging.",
)
def run(
    task: str,
    output_format: str,
    output_file: Path | None,
    model: str,
    trace_json: bool,
) -> None:
    workspace_env_path = Path("~/work/.env").expanduser()
    load_dotenv(dotenv_path=workspace_env_path)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise click.ClickException("GEMINI_API_KEY not found in ~/work/.env")

    ln.track()
    lamindb_run_uid = str(getattr(ln.context.run, "uid", "") or "") or None
    run_uid = create_run_uid(lamindb_run_uid)

    suffix = "ipynb" if output_format == "ipynb" else "py"
    default_name = f"generated_{run_uid}.{suffix}"
    output_path = output_file or Path(default_name)

    run_context = RunContext(
        run_uid=run_uid,
        task=task,
        model=model,
        output_format=output_format,
    )
    result = run_agent(
        api_key=api_key,
        run_context=run_context,
        output_file=output_path,
    )

    trace_txt_path = Path("trace.txt")
    trace_json_path = Path("trace.json") if trace_json else None
    save_trace_files(
        trace_payload=result,
        trace_txt_path=trace_txt_path,
        trace_json_path=trace_json_path,
    )

    generated_file = result.get("generated_file")
    generated_path = Path(generated_file) if isinstance(generated_file, str) else None
    register_trace_and_outputs(
        run_uid=run_uid,
        trace_txt_path=trace_txt_path,
        generated_file=generated_path,
        trace_json_path=trace_json_path,
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


if __name__ == "__main__":
    main()
