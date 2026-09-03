# fixture_integration

Projeto descartável usado pela rotina de integração. Ele consome `setup-spyder`
como **dependência externa** (baixada do GitHub), exatamente como outro
repositório faria — nada aqui importa o `src/` deste repo.

Da raiz do repositório:

```shell
uv run integration               # instala do GitHub e abre o Spyder
uv run integration --no-launch   # só instala e confere o import (CI)
uv run integration --local       # instala o working tree em vez do GitHub
uv run integration --ref develop # instala a partir de outro branch/tag
uv run integration --fresh       # recria o projeto do zero
```

O `pyproject.toml`, o `uv.lock`, o `main.py`, o `.venv/` e o `.spyproject/`
daqui são gerados pela rotina e ficam fora do git.
