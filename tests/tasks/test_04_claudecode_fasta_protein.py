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

    result = run_claudecode(RUN_DIR, PROMPT, install_skill=True)
    print(f"\n--- claude stdout ---\n{result.stdout}")

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

    # Find the script's own Run via its initiated_by_run lineage, not by guessing
    # its self-assigned Transform key: the key is path-qualified (e.g.
    # "test_04/save_protein.py") in a way we can't reliably predict, and other
    # tests' scripts can share the same bare filename (test_01 also writes a
    # save_protein.py), which would silently match the wrong Transform if we
    # filtered by key alone. initiated_by_run is collision-proof by construction.
    script_run = ln.Run.filter(initiated_by_run=run).order_by("-created_at").first()
    assert script_run is not None, (
        "no Run is linked back to the __claudecode__ agent run via initiated_by_run "
        "— the generated script was not self-tracked with LAMIN_INITIATED_BY_RUN_UID "
        "set, per the skill's 'Self-tracking scripts' section (or it was saved as a "
        "plain Artifact instead of a Transform, the same class of bug caught earlier)"
    )

    fasta_files = list(RUN_DIR.rglob("*.fasta"))
    assert fasta_files, "script ran but produced no .fasta file"
    for fasta in fasta_files:
        assert is_valid_fasta(fasta.read_text()), f"{fasta.name} is not valid FASTA"

    fasta_artifact = (
        ln.Artifact.filter(run=script_run, suffix=".fasta")
        .order_by("-created_at")
        .first()
    )
    assert fasta_artifact is not None, (
        "protein.fasta was written to disk but never saved as a LaminDB Artifact "
        "attached to the script's own Run — the prompt explicitly asked for "
        "'saves it as a LaminDB artifact'"
    )
