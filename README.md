# laminagent

Minimal code-generating agent MVP using Gemini REST and LaminDB tracking.

## What it does

- Runs a Gemini tool-calling loop with no agent framework SDK.
- Generates either a runnable Python script (`.py`) or notebook (`.ipynb`).
- Optionally pulls context from:
  - local scientific skill `SKILL.md` files
  - `laminlabs/biomed-skills` via direct LaminDB lookup
- Tracks run outputs in LaminDB and saves a human-readable `trace.txt`.
- Maps `trace.txt` to the LaminDB run report.

## Setup

1. Install package:

```bash
pip install -e .
```

2. Add Gemini key in `~/work/.env`:

```bash
GEMINI_API_KEY=your_api_key_here
```

3. Ensure LaminDB is initialized/connected for your target instance.

## Run

Generate a Python script:

```bash
laminagent run --task "Analyze single-cell RNA-seq data using Scanpy" --output-format py
```

Generate a notebook:

```bash
laminagent run --task "Do exploratory analysis of a CSV and plot summary stats" --output-format ipynb
```

Optional flags:

- `--model gemini-2.5-flash`
- `--output-file my_analysis.py`
- `--trace-json` (save `trace.json` in addition to `trace.txt`)

## Notes

- `run_uid` is propagated into all internal tool calls and output metadata.
- `trace.txt` is saved as an artifact and linked as the run report.
