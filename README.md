# setup-spyder
Run [Spyder-IDE](https://www.spyder-ide.org/) @ version 5.6 (great tool for Exploratory Data Analysis) within a isolated Virtual-Environment using [uv](https://docs.astral.sh/uv/) package 
manager. 
## __quick launch__ `[tl;dr]`
### System requirements
#### Requires [uv](https://docs.astral.sh/uv/)
```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```
### 2. add the package @ `pyproject.toml`
```shell
uv add git+https://github.com/bernardogoltz/setup-spyder
```

```shell
uv run setup-spyder
```
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

## Use in another repository

Add this repo as a dependency (no need to clone it into the other project):

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
uvx --from git+https://github.com/bernardogoltz/setup-spyder setup-spyder
```

## Integration routine

One command to answer one question: **does this package actually work when
someone installs it from GitHub?**

```shell
uv run integration
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
uv run integration --fresh -- main.py
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

