# lag-cli

Minimal code-generating agent MVP using Gemini REST and LaminDB tracking.

## What it does

- Runs a Gemini tool-calling loop with no agent framework SDK.
- Generates either a runnable Python script (`.py`) or notebook (`.ipynb`).
- Executes script paths listed in markdown plans via the `do` workflow.
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

## Commands

Create a markdown plan:

```bash
lag plan run --prompt "Create a plan for single-cell RNA-seq analysis"
```

Create a Python script from a prompt:

```bash
lag plan run --prompt "Write a Scanpy analysis script" --output-format py
```

Execute scripts referenced in an existing plan:

```bash
lag do run --prompt "Execute this plan" --plan-file ./plan.md
```

Optional flags:

- `--model gemini-2.5-flash`
- `--output-file my_analysis.py` (plan group only)

## Notes

- `run_uid` is propagated into all internal tool calls and output metadata.
- `trace.txt` is saved as an artifact and linked as the run report.
