import importlib
import platform
import re
import shlex
import subprocess
from pathlib import Path

import click
import lamindb as ln

ln.connect("laminlabs/lamindata")


@click.group()
def main():
    """LaminProfiler."""


def parse_duration(path: Path) -> float:
    """Extract duration from pyinstrument output; line like 'Duration: 2.315     CPU time: 2.216'."""
    text = path.read_text()
    # below prints the pyinstrament report
    # keep it here! it's formatted for human readability
    print(text)
    match = re.search(r"Duration:\s+([\d.]+)", text)
    return float(match.group(1)) if match else 0.0


def run_profiler(script: Path, repeats: int) -> None:
    """Run script with pyinstrument; profile0 warmup, remaining runs for averaging."""
    script_str = str(script.resolve())
    is_darwin = platform.system() == "Darwin"
    if repeats == 1:
        print("WARNING: --repeats=1 disables cache warming; timing may be noisier.")
    for i in range(repeats):
        print(f"running script {i}...")
        out = Path(f"profile{i}.txt")
        if is_darwin:
            subprocess.run(
                ["script", "-q", str(out), "pyinstrument", script_str],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            cmd = f"pyinstrument {shlex.quote(script_str)}"
            subprocess.run(
                ["script", "-q", "-c", cmd, str(out)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


@main.command("run")
@click.argument(
    "script",
    type=click.Path(path_type=Path, exists=True),
)
@click.option(
    "--repeats",
    default=4,
    type=click.IntRange(min=1),
    show_default=True,
    help="Number of profiling runs. With repeats > 1, first run is warmup.",
)
def run(script: Path, repeats: int) -> None:
    """Run script with pyinstrument; profile0 warmup if repeats > 1."""
    run_profiler(script, repeats)


@main.command("check")
@click.argument(
    "script",
    type=click.Path(path_type=Path, exists=True),
)
@click.option(
    "--threshold",
    default=None,
    type=float,
    help="Max allowed duration in seconds; exit 1 if exceeded. Omit to skip check.",
)
@click.option(
    "--no-run",
    "no_run",
    is_flag=True,
    help="Skip running the profiler; use existing profile files.",
)
@click.option(
    "--repeats",
    default=4,
    type=click.IntRange(min=1),
    show_default=True,
    help="Number of profiling runs. With repeats > 1, first run is warmup.",
)
@ln.flow("BVQ42qdoymVS")
def check(script: Path, threshold: float | None, no_run: bool, repeats: int) -> None:
    script = script.resolve()
    assert script.parent.name == "profiling"
    assert script.parent.parent.name == "tests"
    package_name = script.parent.parent.parent.name.replace("-", "_")
    script_basename = script.name

    if not no_run:
        run_profiler(script, repeats)

    if repeats == 1:
        if no_run:
            print("WARNING: --repeats=1 disables cache warming; timing may be noisier.")
        durations = [parse_duration(Path("profile0.txt"))]
    else:
        # Exclude warmup run (profile0) from averaging.
        durations = [parse_duration(Path(f"profile{i}.txt")) for i in range(1, repeats)]
    duration = sum(durations) / len(durations)

    module = importlib.import_module(package_name, package=".")
    version = module.__version__

    print("first duration: ", parse_duration(Path("profile0.txt")))
    print(
        f"measured durations: {[f'{d:.3f}s' for d in durations]} → avg {duration:.3f}s"
    )
    laminagent = ln.Record.get(name="LaminProfiler")
    package = ln.Record.get(name=package_name, type=laminagent, is_type=True).save()
    task = ln.Record.get(name=script_basename, type=package, is_type=True).save()
    measurement = ln.Record(type=task).save()
    measurement.features.add_values(
        {
            "package_version": version,
            "duration_in_sec": duration,
        }
    )

    if threshold is not None and duration > threshold:
        print(
            f"ERROR: Profiling time {duration:.3f}s exceeds threshold {threshold:.3f}s "
            f"for script {script_basename}"
        )
        raise SystemExit(1)

    # clean up profile files
    for i in range(repeats):
        Path(f"profile{i}.txt").unlink()


if __name__ == "__main__":
    main()
