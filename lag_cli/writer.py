from __future__ import annotations

import shutil
import textwrap
from pathlib import Path
from typing import Any

import nbformat


def _ensure_tracked_python_code(code: str) -> str:
    if "ln.track(" in code and "ln.finish(" in code:
        return code

    indented = textwrap.indent(code.rstrip() + "\n", "    ")
    return (
        "import lamindb as ln\n"
        "from pathlib import Path\n\n"
        "ln.track()\n"
        "_before_files = {p.resolve() for p in Path('.').rglob('*') if p.is_file()}\n\n"
        "try:\n"
        f"{indented}"
        "finally:\n"
        "    _after_files = {p.resolve() for p in Path('.').rglob('*') if p.is_file()}\n"
        "    for _path in sorted(_after_files - _before_files):\n"
        "        if _path.name in {'trace.txt', 'trace_exec.txt'}:\n"
        "            continue\n"
        "        try:\n"
        "            ln.Artifact(str(_path), description='Auto-tracked generated output').save()\n"
        "        except Exception as _exc:\n"
        "            print(f'Warning: failed to track {_path}: {_exc}')\n"
        "    ln.finish()\n"
    )


def _tracking_prologue_cell() -> str:
    return (
        "import lamindb as ln\n"
        "from pathlib import Path\n\n"
        "ln.track()\n"
        "_before_files = {p.resolve() for p in Path('.').rglob('*') if p.is_file()}\n"
    )


def _tracking_epilogue_cell() -> str:
    return (
        "_after_files = {p.resolve() for p in Path('.').rglob('*') if p.is_file()}\n"
        "for _path in sorted(_after_files - _before_files):\n"
        "    if _path.name in {'trace.txt', 'trace_exec.txt'}:\n"
        "        continue\n"
        "    try:\n"
        "        ln.Artifact(str(_path), description='Auto-tracked generated output').save()\n"
        "    except Exception as _exc:\n"
        "        print(f'Warning: failed to track {_path}: {_exc}')\n"
        "ln.finish()\n"
    )


def write_python_script(
    *,
    code: str,
    filename: str,
    run_uid: str,
    track_outputs: bool = True,
) -> dict[str, Any]:
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    code_to_write = _ensure_tracked_python_code(code) if track_outputs else code
    path.write_text(code_to_write, encoding="utf-8")
    return {
        "status": "success",
        "file": str(path),
        "run_uid": run_uid,
        "tracking_enabled": track_outputs,
    }


def write_jupyter_notebook(
    *,
    cells: list[dict[str, str]],
    filename: str,
    run_uid: str,
    track_outputs: bool = True,
) -> dict[str, Any]:
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    nb = nbformat.v4.new_notebook()
    nb_cells: list[Any] = []
    for cell in cells:
        cell_type = cell.get("type", "code")
        content = cell.get("content", "")
        if cell_type == "markdown":
            nb_cells.append(nbformat.v4.new_markdown_cell(content))
        else:
            nb_cells.append(nbformat.v4.new_code_cell(content))
    if track_outputs:
        has_track = any(
            "ln.track(" in str(cell.get("content", ""))
            for cell in cells
            if cell.get("type") == "code"
        )
        has_finish = any(
            "ln.finish(" in str(cell.get("content", ""))
            for cell in cells
            if cell.get("type") == "code"
        )
        if not has_track:
            nb_cells.insert(0, nbformat.v4.new_code_cell(_tracking_prologue_cell()))
        if not has_finish:
            nb_cells.append(nbformat.v4.new_code_cell(_tracking_epilogue_cell()))
    nb["cells"] = nb_cells

    with path.open("w", encoding="utf-8") as f:
        nbformat.write(nb, f)
    return {
        "status": "success",
        "file": str(path),
        "run_uid": run_uid,
        "tracking_enabled": track_outputs,
    }


def write_markdown_plan(
    *,
    markdown: str,
    filename: str,
    run_uid: str,
) -> dict[str, Any]:
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return {
        "status": "success",
        "file": str(path),
        "run_uid": run_uid,
    }


def write_from_template(
    *,
    template_path: str,
    filename: str,
    run_uid: str,
) -> dict[str, Any]:
    src = Path(template_path)
    if not src.exists():
        return {
            "status": "error",
            "message": f"Template not found: {src}",
            "run_uid": run_uid,
        }
    dst = Path(filename)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {
        "status": "success",
        "file": str(dst),
        "template": str(src),
        "run_uid": run_uid,
    }
