from pathlib import Path

from lag_cli.do_executor import execute_plan, extract_script_paths


def test_extract_script_paths(tmp_path: Path) -> None:
    plan_text = """
    - run `scripts/a.py`
    - scripts/b.py
    """
    paths = extract_script_paths(plan_text, tmp_path)
    assert len(paths) == 2
    assert paths[0].name == "a.py"
    assert paths[1].name == "b.py"


def test_execute_plan_runs_python_scripts(tmp_path: Path) -> None:
    script = tmp_path / "hello.py"
    script.write_text("print('hello from script')\n", encoding="utf-8")
    plan = tmp_path / "plan.md"
    plan.write_text(f"- run `{script.name}`\n", encoding="utf-8")

    result = execute_plan(
        prompt="execute this plan",
        plan_file=plan,
        run_uid="test-run",
    )

    assert result["run_uid"] == "test-run"
    assert "Executed 1 scripts" in str(result["final_text"])
    script_events = [
        event
        for event in result["trace_events"]
        if event.get("event") == "script_executed"
    ]
    assert len(script_events) == 1
    assert script_events[0]["exit_code"] == 0
