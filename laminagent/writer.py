from __future__ import annotations

from pathlib import Path
from typing import Any

import nbformat


def write_python_script(*, code: str, filename: str, run_uid: str) -> dict[str, Any]:
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    return {
        "status": "success",
        "file": str(path),
        "run_uid": run_uid,
    }


def write_jupyter_notebook(
    *, cells: list[dict[str, str]], filename: str, run_uid: str
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
    nb["cells"] = nb_cells

    with path.open("w", encoding="utf-8") as f:
        nbformat.write(nb, f)
    return {
        "status": "success",
        "file": str(path),
        "run_uid": run_uid,
    }
