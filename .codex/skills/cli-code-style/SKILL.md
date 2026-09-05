---
name: cli-code-style
description: >
  Maintains the code style of src/setup_spyder/cli.py when writing or editing
  Python in this repo. Use whenever adding functions, logging, argparse
  flags, Rich output, Path handling, or Spyder-related code in setup_spyder
  — especially cli.py, integration.py, and __init__.py. Use when the user
  mentions style, formatting, conventions, Rich logs, or matching cli.py.
paths:
  - src/setup_spyder/**/*.py
---

# cli.py code style

Canonical file: `src/setup_spyder/cli.py`. Copy its patterns. `integration.py`
already follows them (shared `log_*` helpers, Rich panels, argparse,
`main` + `SystemExit`). New Python in `src/setup_spyder/` should too.

Snippet shapes for logs, late imports, and argparse: [examples.md](examples.md).

Do not introduce Black/Ruff/isort config, `logging`, `click`, `typer`,
`print()`, or Spyder imports at module top.

## File skeleton

```python
"""One-line module docstring, imperative, period."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

FONT_FAMILY = "JetBrains Mono"
REPO_URL = "https://github.com/bernardogoltz/setup-spyder"

console = Console(highlight=False)


def public_helper(...) -> ...:
    ...


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    ...


def main(argv: Sequence[str] | None = None) -> int:
    ...


if __name__ == "__main__":
    raise SystemExit(main())
```

- Module docstring first, then `from __future__ import annotations`.
- Stdlib `import X` block, then stdlib `from ... import`, blank line, then
  third-party. First-party only when needed (`from setup_spyder.cli import ...`).
- Constants: `UPPER_SNAKE`. Tuples for fixed collections (`FONT_DIRS`).
- Two blank lines between top-level functions. One blank line inside a
  function only to split distinct phases.
- `parse_args` / `main` / `__main__` last, in that order.
- Double quotes. f-strings. Trailing commas on multiline call arguments.
- Wrap around 88–100 columns; hanging indent for continuations.
- English for docstrings, argparse help, and user-facing log lines.

## Types

- Builtin generics and `|` unions: `str | None`, `Path | None`,
  `tuple[str, list[Path]]`, `Sequence[str]`. No `Optional`, `List`, `Tuple`
  from `typing` unless a `NamedTuple` / `TypedDict` is the actual model
  (`Step` in `integration.py` is the existing exception).
- Annotate every function. `-> None` for helpers that only print.
- `object` for values that are only stringified (`log_kv` `value: object`).
- Keyword-only parameters after `*` for optional flags:

  ```python
  def launch(
      spyder_args: Sequence[str] = (),
      *,
      no_launch: bool = False,
      keep_config: bool = False,
      workdir: str | Path | None = None,
  ) -> int:
  ```

- Sequences default to `()` not `None`. Booleans default to `False`.
- Prefer `Path` over `str` for filesystem. Resolve with
  `Path(...).resolve()`. Iterate with `.glob`, `.rglob`, `.is_dir()`,
  `.is_file()`.

## Late Spyder imports

Import `spyder`, `spyder_kernels`, `CONF`, `EmptyProject`, and
`spyder.config.fonts` **inside the function that needs them**, never at
module top. Reasons: friendly `ImportError`, `SPYDER_CONFDIR` must be set
before `CONF` loads, unit tests stub `sys.modules`.

```python
os.environ["SPYDER_CONFDIR"] = str(conf_dir)
from spyder.config.manager import CONF
```

Expected user errors return `1` and log; they do not raise. Use
`try/except ImportError`. Cleanup goes in `finally`.

## Logging (Rich, not logging)

Reuse `console`, `_prefix`, `log`, `log_ok`, `log_warn`, `log_error`,
`log_kv` from `cli.py`. Do not add a new logger.

| Helper | Glyph / style |
| --- | --- |
| `_prefix()` | `setup-spyder` bold cyan |
| `log` | two spaces, white message |
| `log_ok` | `✓ ` bold green + green message |
| `log_warn` | `! ` bold yellow + yellow message |
| `log_error` | `✗ ` bold red + red message |
| `log_kv` | four spaces, `key: ` dim cyan, value bold white |

Always `soft_wrap=True`. Key/value pairs use `log_kv`, not f-strings inside
`log`. User-facing copy may use a middle dot `·` as a separator.

Banner: `Panel` with `box.ROUNDED`, `padding=(1, 2)`,
`title="[bold cyan]◆ …[/]"`, dim subtitle, `border_style="bright_cyan"`
(or green/red for a success/failure summary, as in `integration.py`).
Env dumps: `Table` with `box.SIMPLE`, `show_header=False`,
`padding=(0, 2)`, `expand=False`.

## argparse

- `ArgumentParser(prog="setup-spyder", description=...)`.
- Flags: `action="store_true"` with a one-line `help=`.
- Extra Spyder argv: `nargs=argparse.REMAINDER`, name `spyder_args`.
- `main(argv: Sequence[str] | None = None) -> int` parses then calls the
  implementation. Exit codes: `0` success, `1` failure. Callers use
  `raise SystemExit(main())`.

## Functions and docs

- Small functions named for the action: `ensure_spyproject`,
  `apply_spyder_config`, `resolve_editor_font`. Leading `_` only for
  helpers not part of the module's story (`_prefix`).
- One-line docstrings for obvious functions. Longer docstring on the public
  entry (`launch`) with a short usage example in a `::` block.
- Comments are rare. Prefer a log line the user can see over an inline
  comment restating the code.
- Public constants and helpers used by `integration.py` stay in `cli.py`
  (`REPO_URL`, `console`, `log_*`). Do not duplicate them.

## What not to "clean up"

- Do not merge the `log_*` helpers into one function with a `level` argument.
- Do not replace Rich with stdlib `print` / `logging`.
- Do not eager-import Spyder to satisfy linters.
- Do not switch quotes, add type comments, or reformat the whole file
  while changing one function.
