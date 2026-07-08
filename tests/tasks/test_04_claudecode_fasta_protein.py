import ast
from pathlib import Path

import lamindb as ln
from testutils import TESTDB1_DEV_DIR, is_valid_fasta, run_claudecode

PROMPT = (
    "Write a Python script that writes your favorite protein sequence to a file "
    "called protein.fasta and saves it as a LaminDB artifact. Then run the script."
)

RUN_DIR = Path(f"{TESTDB1_DEV_DIR}/test_04")


def test_claudecode_fasta_protein_is_tracked() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    run_claudecode(RUN_DIR, PROMPT, install_skill=True)

    # tracking assertions — the actual regression test for the lamindb-track skill
    transform = ln.Transform.filter(key="__claudecode__").one_or_none()
    assert transform is not None, "skill never created the __claudecode__ transform"
    run = ln.Run.filter(transform=transform).order_by("-created_at").first()
    assert run is not None, "no Run found for the __claudecode__ transform"
    assert run.report is not None, "skill did not save a run.report"
    assert run.finished_at is not None, "skill never closed the run (Step 3 skipped)"

    # task-completion assertions
    scripts = list(RUN_DIR.rglob("*.py"))
    assert scripts, "Claude Code wrote no script"
    assert len(scripts) == 1, "expected exactly one generated script"
    script = scripts[0]
    ast.parse(script.read_text())

    script_transform = ln.Transform.filter(key=script.name).one_or_none()
    assert script_transform is not None, (
        "generated script was not self-tracked as its own Transform — this is the "
        "same class of bug caught earlier (script saved as plain Artifact instead "
        "of Transform, which destroys the lineage from script to output data)"
    )

    script_run = (
        ln.Run.filter(transform=script_transform).order_by("-created_at").first()
    )
    assert script_run is not None, (
        "script's Transform exists but has no Run — the script was never executed "
        "under ln.track(), so its ln.finish() never closed a run"
    )
    assert script_run.initiated_by_run_id == run.id, (
        "script's Run is not linked back to the __claudecode__ agent run via "
        "initiated_by_run — LAMIN_INITIATED_BY_RUN_UID was not set (or was set "
        "incorrectly) when Claude Code executed the script, breaking the lineage "
        "the skill's 'Self-tracking scripts' section promises"
    )

    fasta_files = list(RUN_DIR.rglob("*.fasta"))
    assert fasta_files, "script ran but produced no .fasta file"
    for fasta in fasta_files:
        assert is_valid_fasta(fasta.read_text()), f"{fasta.name} is not valid FASTA"

    fasta_artifact = ln.Artifact.filter(suffix=".fasta").order_by("-created_at").first()
    assert fasta_artifact is not None, (
        "protein.fasta was written to disk but never saved as a LaminDB Artifact — "
        "the prompt explicitly asked for 'saves it as a LaminDB artifact'"
    )
    assert fasta_artifact.run_id == script_run.id, (
        "protein.fasta Artifact exists but is not attached to the script's own "
        "Run — expected it to auto-attach via the active ln.track() context, per "
        "the skill's 'no run= needed, auto-attaches' convention"
    )
