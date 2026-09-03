# setup-spyder
Run [Spyder-IDE](https://www.spyder-ide.org/) @ version 5.6 (great tool for Exploratory Data Analysis) within a isolated Virtual-Environment using [uv](https://docs.astral.sh/uv/) package 
manager. 
Runs on Python 3.9 → 3.14, on **macOS, Windows and Linux**.

## __quick launch__ `[tl;dr]`

### with pip

```shell
pip install setup-spyder
setup-spyder
```

### with [uv](https://docs.astral.sh/uv/)

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh          # macOS / Linux
```
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # Windows
```
```
uvx --from setup-spyder setup-spyder
```
### 2. add the package @ `pyproject.toml`
```shell
uv add setup-spyder
```

```shell
uv run setup-spyder
```

### A clean Project pane

Spyder's Project pane only shows what you actually work on. `.venv`, `dist`,
`uv.lock`, `.github`, `.python-version` and ~20 other names are hidden, on top
of what Spyder hides by itself (`.git`, `__pycache__`, `.pytest_cache`, ...).

```shell
setup-spyder --hide notes.txt,scratch   # hide more
setup-spyder --show .github             # bring a default back
```
### Windows

Same commands, in PowerShell or `cmd`:

```powershell
uv run setup-spyder
```

What is platform-specific is handled for you:

| Piece | macOS / Linux | Windows |
| --- | --- | --- |
| JetBrains Mono lookup | `~/Library/Fonts`, `/usr/share/fonts`, ... | `%LOCALAPPDATA%\Microsoft\Windows\Fonts`, `%WINDIR%\Fonts` |
| Font fallback | Spyder's default (Menlo, DejaVu Sans Mono) | Spyder's default (Consolas) |
| Console glyphs | UTF-8 already | stdout/stderr switched to UTF-8, so `✓` does not crash a cp1252 console |
| Isolated config cleanup | `shutil.rmtree` | retries after clearing the read-only bit on cached files |
| Repo shortcut script | `./run-spyder5.sh` | `run-spyder5.cmd` |

The `.spyproject`, the isolated config directory and the Project pane filter
work the same way on all three platforms; `~/.spyder-py3` (`%APPDATA%` on
Windows) is never touched.

## __Actually readable section:__
## Why this repository exists?
- Spyder could be considered the best IDE/Tool for either doing EDA and teaching Python, Data Science, Analytics and more due to it's Variable Explorer, Interactive IPython Console and Graphics Engine for  Data Visualization. 
- Many frustrated tentatives of emulating the spyder experience in VSCode-ish IDE's where thought I could got a great Software Engineering Platform the understanding of data were prejudicated. 
- I really miss working with spyder...
### Isolated python interpreter. 
```shell
% which python3
> /usr/bin/python3
```
```shell
% source .venv/bin/activate
% which python
> setup-data-analytics/.venv/bin/python
```

On Windows the same venv lives in `.venv\Scripts\`:

```powershell
> .venv\Scripts\activate
> where python
setup-data-analytics\.venv\Scripts\python.exe
```

## Use in another repository

Add it as a dependency (no need to clone this repo into the other project):

```shell
uv add setup-spyder
```

Or straight from git, to track `main` ahead of a release:

```shell
uv add git+https://github.com/bernardogoltz/setup-spyder
```

That installs Spyder 5.x into the other project's environment. Then open it from that repo:

```shell
uv run setup-spyder
```

Or import it:

```python
from setup_spyder import launch

if __name__ == "__main__":
    raise SystemExit(launch())
```

`launch()` starts Spyder with JetBrains Mono, wrap lines, and the current repository as the working directory.

Without adding it to the project:

```shell
uvx --from setup-spyder setup-spyder
```

## Integration routine

One command to answer one question: **does this package actually work when
someone installs it from GitHub?**

```shell
uv run setup-spyder-integration
```

That builds a throwaway project in `tests/fixture_integration/` and, inside it:

1. installs `setup-spyder` straight from GitHub (`uv add git+...`),
2. checks that `import setup_spyder` works,
3. runs `uv run setup-spyder`, opening Spyder on that project,
4. prints a summary of every step, then deletes the throwaway project.

Nothing there imports `src/` — it is a real outside consumer, same as any other
repository would be. The install lands in the fixture's own `.venv/`, which is
erased at the end, so your main environment is never touched.

### Flags

| Flag | What changes |
| --- | --- |
| `--no-launch` | Stops after the install and the import check; no Spyder window. |
| `--local` | Installs the local working tree instead of GitHub — use it to test changes you have not pushed yet. |
| `--ref develop` | Installs from another branch, tag or commit. |
| `--fresh` | Deletes the throwaway project first and rebuilds it from scratch. |
| `--keep` | Skips the cleanup, so you can inspect the fixture — handy after a failure. |

Anything after `--` goes to `setup-spyder`:

```shell
uv run setup-spyder-integration --fresh -- main.py
```

### Generated files

The routine writes the fixture's `pyproject.toml`, `uv.lock`, `main.py`,
`.venv/` and `.spyproject/`, and removes all five when it finishes — pass
`--keep` to hold on to them. They are gitignored either way; only the fixture's
`README.md` is versioned, so nothing you care about can be deleted.

## Tests

Unit tests run on every push/PR, and again before publishing to PyPI.

```shell
uv sync
uv run pytest -v
```

## Releasing to PyPI

Publishing runs on [trusted publishing](https://docs.pypi.org/trusted-publishers/)
— no API token lives in this repo. One-time setup, on both `pypi.org` and
`test.pypi.org` (Account → Publishing → add a pending publisher):

| Field | Value |
| --- | --- |
| PyPI project name | `setup-spyder` |
| Owner | `bernardogoltz` |
| Repository | `setup-spyder` |
| Workflow name | `publish.yml` |
| Environment | `pypi` (or `testpypi`) |

Then create the matching GitHub environments (Settings → Environments) with the
same names, so the OIDC claim is environment-scoped.

To cut a release:

1. Bump `__version__` in `src/setup_spyder/__init__.py` — it is the single
   source of truth; `pyproject.toml` reads it via `[tool.hatch.version]`.
2. Run the **Publish** workflow manually with `target: testpypi` and check the
   rendered page plus a clean install.
3. Tag and publish a GitHub release named `v<version>`. The workflow refuses to
   build if the tag and `__version__` disagree, then publishes to PyPI.

