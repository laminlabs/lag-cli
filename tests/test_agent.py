from pathlib import Path

from lag_cli.agent import _dispatch_tool, _looks_like_wrapper_runner
from lag_cli.run_context import RunContext


def test_detects_subprocess_wrapper_runner() -> None:
    code = """
import subprocess
result = subprocess.run(["python", "write_hello.py"], capture_output=True, text=True)
print(result.stdout)
"""
    assert _looks_like_wrapper_runner(code, ["write_hello.py"])


def test_allows_regular_task_script() -> None:
    code = """
import lamindb as ln
with open("hello.txt", "w") as f:
    f.write("Hello agent!")
ln.Artifact("hello.txt").save()
"""
    assert not _looks_like_wrapper_runner(code, [])


def test_rejects_additional_runnable_filename_in_do_mode() -> None:
    run_context = RunContext(
        run_uid="run-1",
        mode="do",
        prompt="p",
        model="m",
    )
    result = _dispatch_tool(
        name="write_python_script",
        args={"filename": "create_hello_file.py", "code": "print('x')"},
        run_context=run_context,
        default_output_file=Path("out.py"),
        existing_generated_files=["hello_agent.py"],
    )
    assert result["status"] == "error"
    assert "Rejected additional runnable tool file in do mode" in str(result["message"])


def test_allows_overwriting_existing_runnable_filename_in_do_mode(
    monkeypatch,
) -> None:
    run_context = RunContext(
        run_uid="run-1",
        mode="do",
        prompt="p",
        model="m",
    )

    def _fake_write_python_script(**kwargs):
        return {"status": "success", "file": str(kwargs["filename"])}

    monkeypatch.setattr("lag_cli.agent.write_python_script", _fake_write_python_script)
    result = _dispatch_tool(
        name="write_python_script",
        args={"filename": "hello_agent.py", "code": "print('x')"},
        run_context=run_context,
        default_output_file=Path("out.py"),
        existing_generated_files=["hello_agent.py"],
    )
    assert result["status"] == "success"
    assert result["file"] == "hello_agent.py"


def test_defaults_python_extension_by_tool_type(monkeypatch) -> None:
    run_context = RunContext(
        run_uid="run-1",
        mode="plan",
        prompt="p",
        model="m",
    )
    captured: dict[str, str] = {}

    def _fake_write_python_script(**kwargs):
        captured["filename"] = str(kwargs["filename"])
        return {"status": "success", "file": str(kwargs["filename"])}

    monkeypatch.setattr("lag_cli.agent.write_python_script", _fake_write_python_script)
    _dispatch_tool(
        name="write_python_script",
        args={"code": "print('x')"},
        run_context=run_context,
        default_output_file=Path("plan_run.md"),
        existing_generated_files=[],
    )
    assert captured["filename"].endswith(".py")
    assert captured["filename"] == "plan_run.py"


def test_defaults_notebook_extension_by_tool_type(monkeypatch) -> None:
    run_context = RunContext(
        run_uid="run-1",
        mode="plan",
        prompt="p",
        model="m",
    )
    captured: dict[str, str] = {}

    def _fake_write_jupyter_notebook(**kwargs):
        captured["filename"] = str(kwargs["filename"])
        return {"status": "success", "file": str(kwargs["filename"])}

    monkeypatch.setattr(
        "lag_cli.agent.write_jupyter_notebook", _fake_write_jupyter_notebook
    )
    _dispatch_tool(
        name="write_jupyter_notebook",
        args={"cells": [{"type": "code", "content": "x=1"}]},
        run_context=run_context,
        default_output_file=Path("plan_run.md"),
        existing_generated_files=[],
    )
    assert captured["filename"].endswith(".ipynb")
    assert captured["filename"] == "plan_run.ipynb"


def test_defaults_markdown_extension_by_tool_type(monkeypatch) -> None:
    run_context = RunContext(
        run_uid="run-1",
        mode="plan",
        prompt="p",
        model="m",
    )
    captured: dict[str, str] = {}

    def _fake_write_markdown_plan(**kwargs):
        captured["filename"] = str(kwargs["filename"])
        return {"status": "success", "file": str(kwargs["filename"])}

    monkeypatch.setattr("lag_cli.agent.write_markdown_plan", _fake_write_markdown_plan)
    _dispatch_tool(
        name="write_markdown_plan",
        args={"markdown": "# Plan"},
        run_context=run_context,
        default_output_file=Path("analysis.py"),
        existing_generated_files=[],
    )
    assert captured["filename"].endswith(".md")
    assert captured["filename"] == "analysis.md"
