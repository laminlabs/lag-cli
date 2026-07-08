import os
import subprocess
import tempfile
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


def run_laminagent(run_dir: str, *args: str) -> subprocess.CompletedProcess[str]:
    return _run_cli(["lag", *args], cwd=run_dir)


def _install_lamindb_track_skill(run_dir: Path) -> None:
    """Install the lamindb-track skill into run_dir so Claude Code auto-discovers it.

    trace_agents.md in laminlabs/lamin-skills is already a complete, standalone
    skill file (frontmatter included, name: lamindb-track) — it just ships nested
    under the generic lamindb skill's references/, which Claude Code's discovery
    (.claude/skills/<name>/SKILL.md) won't scan into on its own. Fetch the official
    package via its documented installer, then copy that one file to its own
    top-level skill path.
    """
    with tempfile.TemporaryDirectory() as tmp:
        _run_cli(
            ["npx", "--yes", "skills", "add", "laminlabs/lamin-skills", "--agent", "claude-code", "-y"],
            cwd=tmp,
        )
        content = Path(
            tmp, ".claude", "skills", "lamindb", "references", "trace_agents.md"
        ).read_text()

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
