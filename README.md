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
uvx --from git+https://github.com/bernardogoltz/setup-spyder setup-spyder
```

