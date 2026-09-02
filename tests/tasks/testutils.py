import ast
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

TESTDB1_NAME = "testdb1"
TESTDB1_STORAGE = f"./{TESTDB1_NAME}-storage"
TESTDB1_DEV_DIR = f"./{TESTDB1_NAME}-dev-dir"

_VALID_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWYBZXJUO*-")
_TRACKING_QUESTION = "should this session be tracked in lamindb"


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


def _assert_tracking_consent_requested(
    result: subprocess.CompletedProcess[str], agent: str
) -> None:
    assert _TRACKING_QUESTION in result.stdout.lower(), (
        f"{agent} did not ask whether the session should be tracked before "
        f"starting the task.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


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


def _install_lamindb_skill(run_dir: Path, skills_dir: Path) -> None:
    """Copy the packaged lamindb skill into an agent's project skill directory."""
    import shutil

    import lamindb

    src = Path(lamindb.__file__).parent / ".agents" / "skills" / "lamindb"
    dst = run_dir / skills_dir / "lamindb"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


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
        _install_lamindb_skill(run_dir, Path(".claude/skills"))

    env = {**os.environ, "ANTHROPIC_API_KEY": api_key}
    initial = _run_cli(
        [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            "bypassPermissions",
        ],
        cwd=str(run_dir),
        env=env,
    )
    _assert_tracking_consent_requested(initial, "Claude Code")
    try:
        session_id = json.loads(initial.stdout)["session_id"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AssertionError(
            f"Claude Code did not return a resumable session ID:\n{initial.stdout}"
        ) from exc

    command = [
        "claude",
        "-p",
        "yes",
        "--resume",
        session_id,
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
    ]
    return _run_cli(command, cwd=str(run_dir), env=env)


def run_copilot(
    run_dir: str | Path,
    prompt: str,
    install_skill: bool = False,
) -> subprocess.CompletedProcess[str]:
    load_dotenv(dotenv_path=Path("~/llms.env").expanduser())
    token = os.getenv("LAMIN_COPILOT_TOKEN")
    if not token:
        raise RuntimeError(
            "LAMIN_COPILOT_TOKEN not set (add to ~/llms.env or as env var)"
        )

    run_dir = Path(run_dir)
    if install_skill:
        _install_lamindb_skill(run_dir, Path(".agents/skills"))

    env = {
        **os.environ,
        # Use Copilot's highest-precedence credential variable so the Actions
        # GITHUB_TOKEN cannot accidentally shadow the dedicated test token.
        "COPILOT_GITHUB_TOKEN": token,
        "COPILOT_AUTO_UPDATE": "false",
    }
    session_id = str(uuid4())
    common_args = [
        "--allow-all",
        "--secret-env-vars=LAMIN_COPILOT_TOKEN,COPILOT_GITHUB_TOKEN,GITHUB_TOKEN",
    ]
    initial = _run_cli(
        ["copilot", "-p", prompt, "--session-id", session_id, *common_args],
        cwd=str(run_dir),
        env=env,
    )
    _assert_tracking_consent_requested(initial, "Copilot")

    command = [
        "copilot",
        "-p",
        "yes",
        f"--resume={session_id}",
        *common_args,
    ]
    return _run_cli(command, cwd=str(run_dir), env=env)
