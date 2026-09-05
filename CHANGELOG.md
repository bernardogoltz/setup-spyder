# Changelog

## Unreleased

### Fixed
- CI was red on every job since 0.3.0. `tests/unit/test_profile.py` asserted
  that `~/.spyder-py3` still existed after `reset_profile` refused it, which
  only holds on a machine where Spyder has already run; on a clean runner the
  directory never existed. The test now checks that the refusal neither
  deletes nor creates the path.
- A `pytest.importorskip` at the top of `tests/qt/conftest.py` (and
  `tests/pty/conftest.py`) skipped the *whole session* when QtWebEngine could
  not be imported (Linux without `libnss3`): pytest 7 reported
  "collected 0 items / 1 skipped" and exit code 5, taking `tests/unit` down
  with it. The skip is now scoped to that directory
  (`helpers.pending.pular_diretorio`).
- `QT_QPA_PLATFORM=offscreen` is set only on Linux in both workflows. On the
  Windows runner it made QtWebEngine crash with an access violation on the
  first `QWebEngineView`, killing the `full` job mid-run.
- `setup-uv` cache keyed on `pyproject.toml` (there is no lockfile), instead
  of a key that never invalidates.

## 0.3.0 — 2026-09-04

Launcher for the `bernardogoltz/spyder` fork with the AI Terminal pane.

### Added
- `spyder` now resolves to the fork `bernardogoltz/spyder` (Spyder 5.x API,
  `5.6.0.dev0`), pinned by commit in `pyproject.toml`; the PyPI `spyder` is no
  longer a dependency. Direct-URL requirements are refused by PyPI, so releases
  are published as GitHub Release assets and installed from Git.
- **AI Terminal** plugin (`spyder.plugins` entry point `setup_spyder_ai`):
  xterm.js + `QWebChannel` + ConPTY (`pywinpty`) / PTY (`ptyprocess`) terminal
  pane that starts `codex` or `claude`; provider selector, new session,
  restart, interrupt, clear, close, state indicator, preferences page.
- `--agent {auto,codex,claude,none}`, `--profile {ephemeral,project}`,
  `--reset-profile`, `--conf-dir`, `--ephemeral`, `--sem-estilo`.
- Persistent per-project profile in `<root>/.spyproject/setup-spyder/`, seeded
  once (versioned seed, never rewritten on later starts); ephemeral profile
  keeps the old temp-directory behaviour.
- The Spyder child tree (kernels, pylsp, QtWebEngine) is tied to the launcher:
  Job Object with kill-on-close on Windows, own session plus SIGTERM/SIGINT
  forwarding on POSIX, so killing `setup-spyder` never leaves orphans.
- Clean child bootstrap (`python -m setup_spyder.bootstrap`): the parent never
  imports Spyder's configuration or Qt; `SPYDER_CONFDIR`, `SETUP_SPYDER_AGENT`,
  `SETUP_SPYDER_WORKDIR`, `SETUP_SPYDER_AUTOSTART` are set before Spyder starts.
- Test suite organised by plan phase (`unit`, `qt`, `pty`, `integration`,
  `e2e`), with a deterministic fake TUI for the PTY contract.

### Changed
- `launch()` keeps its signature and gains keyword-only options; `main`,
  `open_spyder`, `setup-spyder-integration` and the existing flags
  (`--no-launch`, `--keep-config`, `-w`, `--hide`, `--show`) are preserved.
- `.spyproject/` is created without importing Spyder; `single_instance` is
  left at Spyder's default so a project profile is not opened twice.
- CI runs unit tests on Linux/macOS/Windows and the Qt/PTY suite on Windows
  and Linux (offscreen); `uv.lock` is no longer versioned.

### Removed
- No `CONDA_*` cleanup, no global `QApplication.beep` patch, no disabling of
  internal error reports or dependency warnings.

## 0.2.0

- Project-pane clutter filter (`--hide` / `--show`), Windows support,
  integration routine, PyPI release workflow.
