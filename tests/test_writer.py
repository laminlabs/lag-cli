from pathlib import Path

from lag_cli.writer import write_jupyter_notebook, write_python_script


def test_write_python_script(tmp_path: Path) -> None:
    out = tmp_path / "generated.py"
    result = write_python_script(
        code="print('hello')\n",
        filename=str(out),
        run_uid="test-run",
    )
    assert result["status"] == "success"
    assert out.exists()
    assert "hello" in out.read_text(encoding="utf-8")


def test_write_jupyter_notebook(tmp_path: Path) -> None:
    out = tmp_path / "generated.ipynb"
    result = write_jupyter_notebook(
        cells=[
            {"type": "markdown", "content": "# Title"},
            {"type": "code", "content": "x = 1"},
        ],
        filename=str(out),
        run_uid="test-run",
    )
    assert result["status"] == "success"
    assert out.exists()
