# Lag: Lamin's Agent CLI

`lag` can retrieve or generate scripts (`.py`), notebooks (`.ipynb`), and skills & plans (`.md`) and then perform work with these tools.

## Setup

```bash
pip install lag-cli
```

Create `~/llms.env` with:

```bash
GEMINI_API_KEY=your_api_key_here
```

Make sure LaminDB is initialized and connected.

## Quick Start

Run in default mode:

```bash
lag --prompt "Write a text file with 'Hello agent!' in it, please"
```

## Modes

### Default mode

- If a plan exists (`plan.md` or latest `plan_*.md`, or `--plan-file`), `lag` executes the referenced runnable tools.
- Otherwise, `lag` generates runnable tool file(s), shows their contents, and asks for confirmation before execution.
- In default mode, generated code includes `ln.track()` / `ln.finish()` unless `--no-track` is used.

### Planning mode (`--plan`)

Generate tools without executing them:

```bash
lag --plan --prompt "Write a plan for this analysis"
```

Generated tool files are saved via `lamin save` in plan mode.

## Common Flags

- `--project <name>` sets `LAMIN_CURRENT_PROJECT`.
- `--model <model-name>` selects the Gemini model.
- `--output-file <path>` sets output filename for generated content.
- `--output-format [md|py|ipynb]` applies in `--plan` mode.
- `--plan-file <path>` executes a specific plan in default mode.
- `--no-track` disables `ln.track()` / `ln.finish()` injection.
- `--yes` skips confirmation for executing newly generated tools.

## Run Context Propagation

When `lag` executes scripts/notebooks, it propagates:

- `LAMIN_INITIATED_BY_RUN_UID` (master run uid)
- `LAMIN_CURRENT_PROJECT` (if `--project` is provided)

`lag` itself does not directly create output artifacts; produced outputs are tracked by executed tool code.
