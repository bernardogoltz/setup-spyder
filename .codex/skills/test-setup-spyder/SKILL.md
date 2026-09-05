---
name: test-setup-spyder
description: >
  Writes, extends, and runs pytest for setup-spyder (uv + conftest Spyder
  stubs). Use whenever adding or changing tests, after editing cli.py or
  integration.py, when pytest or CI fails, or when the user mentions tests,
  coverage, pytest, fixtures, or the integration routine.
paths:
  - tests/**
  - src/setup_spyder/**
  - .github/workflows/ci.yml
allowed-tools: Bash(uv *) Read Grep Glob
---

# Test setup-spyder

## Commands

From the repository root. Never call `pytest` without `uv run`.

```bash
uv sync
uv run pytest -v
uv run pytest -v tests/test_cli.py
uv run pytest -v tests/test_cli.py::test_launch_no_launch_creates_project_and_skips_gui
```

CI (`.github/workflows/ci.yml`) runs the same unit tests on Python 3.9–3.13.
It does **not** open Spyder and does **not** run `setup-spyder-integration`.

## Two layers — do not mix them

| Layer | Where | Needs Qt / display / real Spyder? |
| --- | --- | --- |
| Unit tests | `tests/test_cli.py`, `tests/test_integration.py` | No. `tests/conftest.py` stubs Spyder. |
| Integration routine | `uv run setup-spyder-integration` | Yes (unless `--no-launch`). Not pytest. |

Do not start the Spyder GUI from a unit test. Do not add the throwaway
project under `tests/fixture_integration/` to pytest. That directory is a
consumer fixture: only `README.md` is versioned; generated files stay in
`.gitignore`.

When the user asks to **run tests**, run pytest. Run the integration
routine only when they ask for an end-to-end / GitHub-install check.

## Why the stubs work

`cli.py` imports Spyder **inside functions**, after `SPYDER_CONFDIR` is set.
`tests/conftest.py` has an `autouse` fixture that injects fake modules into
`sys.modules` before those imports run:

- `spyder` (`__version__ = "5.5.6"`), `spyder_kernels`
- `spyder.config.manager.CONF` → `FakeCONF` (dict + writes `spyder.ini`)
- `spyder.config.fonts.MONOSPACE` → `["Menlo", "Monospace"]`
- `spyder.plugins.projects.api.EmptyProject` → `FakeEmptyProject`

If a change moves `import spyder` (or `CONF`, `EmptyProject`, `MONOSPACE`)
to module top, **every unit test that touches launch/config will break**.
Do not "fix" that by installing real Spyder in tests. Keep the late import.

## Where to add a test

| Change in | Test file |
| --- | --- |
| `src/setup_spyder/cli.py` | `tests/test_cli.py` |
| `src/setup_spyder/integration.py` | `tests/test_integration.py` |
| Public API (`launch`, `open_spyder`, `__version__`) | `tests/test_cli.py` (`test_public_api_aliases`) |
| New argparse flag | the matching `test_parse_args_*` |

Do not create a new test module unless the change is a new source module.

## How to write a test here

Match `tests/test_cli.py` / `tests/test_integration.py`:

1. `from __future__ import annotations` then stdlib, then `pytest`, then
   `setup_spyder` / `setup_spyder.cli` / `setup_spyder.integration`.
2. Name: `test_<behavior>` (what it asserts, not the implementation).
3. Return type `-> None`.
4. `tmp_path` for files and workdirs. `monkeypatch` for `FONT_DIRS`,
   `shutil.which`, `subprocess.run`, `cli.launch`, env vars.
5. `MagicMock` for "was this called?". `SimpleNamespace(returncode=0)` when
   only the exit code matters.
6. Patch **on the module under test** (`cli.subprocess.run`, not
   `subprocess.run`).
7. Assert behavior: exit code, files created, argv passed to Spyder, env
   keys dropped, fixture files kept or deleted. Do not assert Rich markup
   or log wording unless the change is specifically about those strings.
8. One behavior per test. Prefer a new function over extra asserts that
   mix unrelated paths.

### CLI patterns already covered — extend, do not duplicate

`parse_args`, JetBrains Mono found/missing, `ensure_spyproject` create vs
reuse, `apply_spyder_config` font+wrap and fallback, `launch` with
`--no-launch`, spyder argv (`--conf-dir`, `--new-instance`, `-w`, `-p`),
missing binary, isolated-config `rmtree` vs `--keep-config`, ImportError
→ `1`, `main()` forwarding flags.

New `launch()` branch (flag, early return, extra argv) needs a test that
calls `launch(...)` with `workdir=tmp_path` and stubs `which` / `run`.

### Integration patterns already covered

`parse_args`, `dependency_spec` (GitHub / `@ref` / local path),
`child_env()` dropping `VIRTUAL_ENV` and `SPYDER_CONFDIR`, scaffold
reuse, `clean_fixture` keeping `README.md`, `find_repo_root`,
`run_integration` command sequence, cleanup on success/failure/`--keep`,
`--no-launch` extra args, `--local`, stop after failed `uv add`, `--fresh`.

Stub `uv` with `monkeypatch.setattr(integration.shutil, "which", ...)`.
Record `uv` argv via a fake `subprocess.run` that returns
`CompletedProcess`. Use the `fake_repo` fixture (or the same shape) so
nothing touches the real `tests/fixture_integration/` tree.

## After writing tests

1. Run the focused file, then the full suite: `uv run pytest -v`.
2. If a failure is a stub gap (new `import spyder.*` inside a function),
   extend `fake_spyder` in `conftest.py` the same way as `FakeCONF` /
   `FakeEmptyProject`. Do not skip the test.
3. Do not add pytest plugins, coverage config, or tox unless asked.
4. Do not commit generated fixture files (`pyproject.toml`, `main.py`,
   `uv.lock`, `.venv`, `.spyproject` under `tests/fixture_integration/`).

## Isolated test work

For a self-contained "write tests / run pytest / report" pass, delegate
to the `pytest-tester` subagent. It preloads this skill.
