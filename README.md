# setup-spyder

Open the [bernardogoltz/spyder](https://github.com/bernardogoltz/spyder) fork
(Spyder 5.x, a great tool for exploratory data analysis) inside the `.venv` of
any [uv](https://docs.astral.sh/uv/) project, with an isolated per-project
profile, JetBrains Mono + wrap lines, and an **AI Terminal** pane that runs the
[Codex CLI](https://developers.openai.com/codex/cli/reference) or
[Claude Code](https://code.claude.com/docs/en/cli-usage) in a real terminal
(xterm.js + ConPTY/PTY). No conda, no popups, `~/.spyder-py3` untouched.

Runs on Python 3.9 → 3.12 (PyQt5 5.15 wheels) on Windows, macOS and Linux.

## Quick start

```shell
uv add --dev git+https://github.com/bernardogoltz/setup-spyder
uv run setup-spyder --agent codex        # or: claude | auto | none
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
```

Or import it:

```python
from setup_spyder import launch

if __name__ == "__main__":
    raise SystemExit(launch(agent="claude"))
```

## What happens when you run it

```text
project/.venv
    └─ uv run setup-spyder --agent codex
          ├─ resolves the project root, the profile and the agent
          ├─ creates .spyproject/ if missing, seeds the profile once (versioned)
          └─ starts a clean child: python -m setup_spyder.bootstrap ...
                └─ the fork, with SPYDER_CONFDIR = <root>/.spyproject/setup-spyder
                      └─ AI Terminal pane (entry point spyder.plugins:setup_spyder_ai)
                            └─ codex | claude in a PTY/ConPTY, cwd = project root
```

- **Profile.** `--profile project` (default) keeps the Spyder configuration in
  `<root>/.spyproject/setup-spyder/`; it is seeded on creation (theme, font,
  wrap lines, no update/tour/DPI dialogs, the project's interpreter as the
  default one) and never rewritten on later starts. `--profile ephemeral`
  (`--ephemeral`) uses a throwaway temp directory (kept with `--keep-config`).
  `--conf-dir PATH` wins over both. `--reset-profile` wipes and recreates the
  resolved profile, after checking it really is the profile directory.
- **Agent.** `--agent` overrides the saved preference for one run. `auto`
  starts the only known CLI on `PATH`, shows a selector when both are present,
  and leaves the pane usable with a short hint when neither is. `none` opens
  Spyder without starting anything. Authentication, model and permissions stay
  with the CLI itself; no flag is added implicitly.
- **Project pane.** `.venv`, `dist`, `uv.lock`, `.github` and ~20 other names
  are hidden on top of what Spyder hides (`--hide a,b` / `--show .github`).
- **Windows.** UTF-8 console output, `%LOCALAPPDATA%` font lookup, read-only
  cache cleanup and a ConPTY backend (`pywinpty`) are handled for you.

Anything after `--` goes to Spyder (`-- --debug-info verbose`).

## The AI Terminal pane

A dockable Spyder plugin (`AITerminalPlugin`, tabified with the IPython
console). Toolbar: provider selector, **New session**, **Restart**,
**Interrupt** (`Ctrl+C`), **Clear**, **Close session**, and a state indicator
(`idle`, `starting`, `running`, `exited`, `error`). Preferences → AI Terminal:
provider, autostart, bell, scrollback.

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
