# lag-cli

Minimal code-generating agent MVP using Gemini REST and LaminDB tracking.

## What it does

- Runs a Gemini tool-calling loop with no agent framework SDK.
- Generates either a runnable Python script (`.py`) or notebook (`.ipynb`).
- Executes script paths listed in markdown plans via the `do` workflow.
- Optionally pulls context from:
  - local scientific skill `SKILL.md` files
  - `laminlabs/biomed-skills` via direct LaminDB lookup
- Logs full model/tool execution to stdout (captured by Lamin run logging).
- Saves generated tool files and outputs into LaminDB.

## Setup

1. Install package:

```bash
pip install -e .
```

2. Add Gemini key in `~/llms.env`:

```bash
GEMINI_API_KEY=your_api_key_here
```

3. Ensure LaminDB is initialized/connected for your target instance.

## Usage

Default mode (`do`):

```bash
lag --prompt "Write a text file with 'Hello agent!' in it, please"
```

In default mode, if no plan is found, `lag` generates runnable scripts/notebooks and then executes them automatically.
Generated scripts/notebooks include `ln.track()`/`ln.finish()` and auto-register new output files as artifacts by default.

Planning mode:

```bash
lag --plan --prompt "Please make a plan for analyzing the pbmc3k dataset"
```

Optional: choose output type in planning mode:

```bash
lag --plan --prompt "Write a Scanpy analysis script" --output-format py
```

If a plan exists (`plan.md` or latest `plan_*.md`), default mode executes scripts/notebooks listed in the plan. You can also pass one explicitly:

```bash
lag --prompt "Execute the current plan" --plan-file ./plan.md
```

Disable auto-tracking code injection when needed:

```bash
lag --prompt "..." --no-track
```

Optional flags:

- `--model gemini-flash-latest`
- `--output-file my_analysis.py`

## Notes

- `run_uid` is propagated into all internal tool calls and output metadata.
- Custom trace artifact files are no longer used; rely on run logs.

## Generated Tools vs Produced Outputs

- Generated tool files are the files the agent writes directly, such as:
  - `plan_*.md` (planning docs)
  - `*.py` (generated scripts)
  - `*.ipynb` (generated notebooks)
- Produced outputs are files created when those generated tools execute, such as:
  - `hello-agent.txt`
  - data tables, plots, model artifacts, etc.
- In default `do` mode, `lag` can generate a script/notebook and then execute it; this second step is what creates produced outputs.
- With default tracking injection (unless `--no-track`), generated scripts/notebooks include `ln.track()`/`ln.finish()`, so produced outputs are tracked during execution.
