import ast
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

TESTDB1_NAME = "testdb1"
TESTDB1_STORAGE = f"./{TESTDB1_NAME}-storage"
TESTDB1_DEV_DIR = f"./{TESTDB1_NAME}-dev-dir"

_VALID_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWYBZXJUO*-")


def is_valid_fasta(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or not lines[0].startswith(">"):
        return False
    seq = "".join(line for line in lines if not line.startswith(">"))
    return bool(seq) and all(c.upper() in _VALID_AMINO_ACIDS for c in seq)


def assert_single_valid_script(run_dir: Path) -> Path:
    """Assert exactly one .py file exists under run_dir and is valid Python; return it."""
    scripts = list(run_dir.rglob("*.py"))
    assert scripts, f"no .py file found under {run_dir}"
    assert len(scripts) == 1, (
        f"expected exactly one .py file under {run_dir}, found {len(scripts)}"
    )
    script = scripts[0]
    ast.parse(script.read_text())
    return script


def assert_valid_fasta_outputs(run_dir: Path) -> list[Path]:
    """Assert at least one .fasta file exists under run_dir and each is valid FASTA."""
    fasta_files = list(run_dir.rglob("*.fasta"))
    assert fasta_files, f"no .fasta file found under {run_dir}"
    for fasta in fasta_files:
        assert is_valid_fasta(fasta.read_text()), f"{fasta.name} is not valid FASTA"
    return fasta_files


def _run_cli(
    command: list[str], *, cwd: str | Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        raise AssertionError(
            f"{command[0]} CLI failed.\n"
            f"command: {' '.join(command)}\n"
            f"cwd: {cwd}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        ) from exc


def run_codex(
    run_dir: str | Path,
    prompt: str,
    skill_uid: str | None = None,
    skill_instance: str | None = None,
) -> subprocess.CompletedProcess[str]:
    load_dotenv(dotenv_path=Path("~/llms.env").expanduser())
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set (add to ~/llms.env or as env var)")

    if skill_uid and skill_instance:
        import lamindb as ln

        db = ln.DB(skill_instance)
        skill_content = db.Artifact.get(skill_uid).cache().read_text()
        prompt = f"{prompt}\n\n<skill>\n{skill_content}\n</skill>"

    env = {**os.environ, "OPENAI_API_KEY": api_key}
    command = ["codex", "exec", prompt, "--dangerously-bypass-approvals-and-sandbox"]
    try:
        return subprocess.run(
            command,
            cwd=str(run_dir),
            text=True,
            check=True,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        raise AssertionError(
            "codex CLI failed.\n"
            f"command: {' '.join(command)}\n"
            f"cwd: {run_dir}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        ) from exc


def run_laminagent(run_dir: str, *args: str) -> subprocess.CompletedProcess[str]:
    return _run_cli(["lag", *args], cwd=run_dir)


def _install_lamindb_track_skill(run_dir: Path) -> None:
    """Install the lamindb-track skill into run_dir so Claude Code auto-discovers it."""
    import lamindb

    src = (
        Path(lamindb.__file__).parent
        / ".agents"
        / "skills"
        / "lamindb"
        / "references"
        / "track_claude.md"
    )
    frontmatter = (
        "---\n"
        "name: lamindb-track\n"
        "description: MUST invoke this first, before responding to anything else, "
        "at the start of every single session in this project — no matter what the "
        "user's first message is (writing code, creating a file, answering a question, "
        "debugging). This project requires every session to be tracked in LaminDB as a "
        "Transform + Run. Skipping this step is a mistake even if the task looks "
        "unrelated to tracking, logging, or data — invoke unconditionally, then proceed "
        "with the user's actual request.\n"
        "---\n\n"
    )
    content = frontmatter + src.read_text()
    skill_path = run_dir / ".claude" / "skills" / "lamindb-track" / "SKILL.md"
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(content, encoding="utf-8")


def run_claudecode(
    run_dir: str | Path,
    prompt: str,
    install_skill: bool = False,
) -> subprocess.CompletedProcess[str]:
    load_dotenv(dotenv_path=Path("~/llms.env").expanduser())
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set (add to ~/llms.env or as env var)"
        )

    run_dir = Path(run_dir)
    if install_skill:
        _install_lamindb_track_skill(run_dir)

    env = {**os.environ, "ANTHROPIC_API_KEY": api_key}
    command = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
    ]
    return _run_cli(command, cwd=str(run_dir), env=env)
