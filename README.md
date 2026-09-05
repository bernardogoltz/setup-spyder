# setup-spyder

![setup-spyder](examples/setup-spyder.gif)

Open the [bernardogoltz/spyder](https://github.com/bernardogoltz/spyder) fork
(Spyder 5.x, a great tool for exploratory data analysis) inside the `.venv` of
any [uv](https://docs.astral.sh/uv/) project. Two commands, same package:

- **`setup-spyder`** — Spyder as a module (`python -m spyder.app.start`), with
  `.spyproject`, JetBrains Mono and the project profile. No AI Terminal.
- **`setup-spyder-fork`** — the isolated instance: pane filter, AI Terminal
  (Codex CLI / Claude Code in a real PTY), agent flags.

No conda, no popups, `~/.spyder-py3` untouched. Runs on Python 3.9 → 3.12
(PyQt5 5.15 wheels) on Windows, macOS and Linux.

## Quick start

```shell
uv add --dev git+https://github.com/bernardogoltz/setup-spyder
uv run setup-spyder
uv run setup-spyder-fork --agent claude
```

`uv run python -c "import spyder; print(spyder.__version__)"` prints the
fork's version (`5.6.0.dev0`), not the PyPI `spyder`.

> This package depends on the fork by Git URL
> (`spyder @ git+https://github.com/bernardogoltz/spyder.git@<commit>`), which
> PyPI does not accept, so it is installed from GitHub (or from the wheel
> attached to a [release](https://github.com/bernardogoltz/setup-spyder/releases)),
> never with a bare `uv add setup-spyder`.

Without adding it to the project:

```shell
uvx --from git+https://github.com/bernardogoltz/setup-spyder setup-spyder
uvx --from git+https://github.com/bernardogoltz/setup-spyder setup-spyder-fork
```

Or import it:

```python
from setup_spyder import launch, launch_fork

if __name__ == "__main__":
    raise SystemExit(launch())           # native module
    # raise SystemExit(launch_fork(agent="claude"))
```

## What happens when you run it

```text
project/.venv
    ├─ uv run setup-spyder
    │     ├─ creates .spyproject/ if missing
    │     ├─ seeds the project profile once (fonts, wrap, no popups)
    │     └─ python -m spyder.app.start -w <root> -p <root>
    │           SPYDER_CONFDIR = <root>/.spyproject/setup-spyder
    │
    └─ uv run setup-spyder-fork --agent codex
          ├─ resolves the project root, the profile and the agent
          ├─ creates .spyproject/ if missing, seeds the profile once
          └─ python -m setup_spyder.bootstrap ...
                └─ the fork, with SPYDER_CONFDIR = <root>/.spyproject/setup-spyder
                      └─ AI Terminal pane (entry point spyder.plugins:setup_spyder_ai)
                            └─ codex | claude in a PTY/ConPTY, cwd = project root
```

Spyder 5.x has no `python -m spyder`; the native module is `spyder.app.start`.
The AI Terminal plugin is installed either way, but it only loads when
`setup-spyder-fork` sets `SETUP_SPYDER_FORK=1`.

- **Profile.** Both commands default to `<root>/.spyproject/setup-spyder/`;
  it is seeded on creation (theme, font, wrap lines, no update/tour/DPI
  dialogs, the project's interpreter as the default one) and never rewritten
  on later starts. `setup-spyder-fork` also has `--profile ephemeral`
  (`--ephemeral`, kept with `--keep-config`) and `--conf-dir PATH`.
  `--reset-profile` wipes and recreates the resolved profile, after checking
  it really is the profile directory.
- **Agent** (`setup-spyder-fork` only). `--agent` overrides the saved
  preference for one run. `auto` starts the only known CLI on `PATH`, shows a
  selector when both are present, and leaves the pane usable with a short hint
  when neither is. `none` opens Spyder without starting anything.
  Authentication, model and permissions stay with the CLI itself; no flag is
  added implicitly.
- **Project pane** (`setup-spyder-fork` only). `.venv`, `dist`, `uv.lock`,
  `.github` and ~20 other names are hidden on top of what Spyder hides
  (`--hide a,b` / `--show .github`).
- **Windows.** UTF-8 console output, `%LOCALAPPDATA%` font lookup, read-only
  cache cleanup and a ConPTY backend (`pywinpty`) are handled for you.

Anything after `--` goes to Spyder (`-- --debug-info verbose`).

## The AI Terminal pane

Loaded only by **`setup-spyder-fork`**. A dockable Spyder plugin
(`AITerminalPlugin`, tabified with the IPython console). Toolbar: provider
selector, **New session**, **Restart**, **Interrupt** (`Ctrl+C`), **Clear**,
**Close session**, and a state indicator (`idle`, `starting`, `running`,
`exited`, `error`). Preferences → AI Terminal: provider, autostart, bell,
scrollback.

- Real TTY: ANSI colours, character-by-character input, resize and `Ctrl+C`
  reach the CLI unchanged.
- Transport is `QWebChannel` inside the process — no local server, no open
  TCP port, no JavaScript from a CDN (xterm.js is bundled).
- The child process tree is terminated when the pane or Spyder closes.
- Missing PTY backend or CLI degrades the pane only; Spyder still opens.

## Integration routine

```shell
uv run setup-spyder-integration               # install from GitHub and open Spyder
uv run setup-spyder-integration --no-launch   # only install and check the import
uv run setup-spyder-integration --local       # use this working tree instead of GitHub
uv run setup-spyder-integration --ref v0.3.0  # another branch/tag/commit
uv run setup-spyder-integration --fresh --keep
```

It builds a throwaway consumer project in `tests/fixture_integration/`,
installs `setup-spyder` there (the fork comes from its pinned GitHub commit),
runs `uv run setup-spyder` and cleans up. Nothing there imports `src/`.

## Development

This repository is also the `setup-spyder/` submodule of the fork. Developing
from the fork checkout (recommended, one venv for both):

```powershell
git clone --recurse-submodules https://github.com/bernardogoltz/spyder
cd spyder
uv venv --python 3.12
uv pip install -r requirements\dev-uv.txt
uv pip install -e . --no-deps
uv pip install -e .\setup-spyder --no-deps
cd setup-spyder
..\.venv\Scripts\python.exe -m pytest tests -p no:cacheprovider
```

Standalone (after the fork commit pinned in `pyproject.toml` is on GitHub):

```shell
uv sync --group dev
uv run pytest
```

Tests are organised by plan phase and by kind (`unit`, `qt`, `pty`,
`integration`, `e2e`); see [tests/README.md](tests/README.md). Style
conventions live in `.claude/skills/cli-code-style/SKILL.md`.

### Updating the fork pin

1. Commit and push the fork (`bernardogoltz/spyder`, branch `main`).
2. Replace the hash in `spyder @ git+https://github.com/bernardogoltz/spyder.git@<hash>`
   in `pyproject.toml` (a tag works too; never a floating branch, never a
   local path).
3. `uv lock`, run the tests, commit.
4. In the fork, `git add setup-spyder` to move the submodule pointer.

## Releasing

Publishing runs on GitHub Releases (`.github/workflows/publish.yml`): bump
`__version__` in `src/setup_spyder/__init__.py`, tag `v<version>`, publish the
release; the workflow refuses to build if the tag and `__version__` disagree,
then attaches the wheel and sdist to the release.
