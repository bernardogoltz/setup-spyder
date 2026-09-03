"""Rotina de integração: instala o pacote a partir do GitHub e abre o Spyder.

Cria (ou reaproveita) o projeto descartável em ``tests/fixture_integration/``,
adiciona ``setup-spyder`` vindo do GitHub e roda ``uv run setup-spyder`` lá
dentro — o mesmo fluxo que outra pessoa faria em outro repositório.

Uso::

    uv run integration               # instala do GitHub e abre o Spyder
    uv run integration --no-launch   # só instala e confere o import
    uv run integration --local       # usa o working tree em vez do GitHub
    uv run integration --ref develop # instala a partir de outro branch/tag
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from setup_spyder.cli import (
    REPO_URL,
    log,
    log_error,
    log_kv,
    log_ok,
    log_warn,
)

FIXTURE_RELPATH = Path("tests") / "fixture_integration"
FIXTURE_NAME = "setup-spyder-integration-fixture"

#: Gerado pela rotina; some com ``--fresh`` e fica fora do git.
GENERATED = (".venv", ".spyproject", "pyproject.toml", "uv.lock", "main.py")

#: Variáveis do ``uv run`` externo que não podem vazar para o projeto de teste.
INHERITED_ENV_TO_DROP = (
    "VIRTUAL_ENV",
    "UV_PROJECT_ENVIRONMENT",
    "PYTHONPATH",
    "PYTHONHOME",
    "SPYDER_CONFDIR",
)

FIXTURE_PYPROJECT = f"""\
# Gerado por `uv run integration` — não edite à mão.
[project]
name = "{FIXTURE_NAME}"
version = "0.0.0"
description = "Projeto descartável que consome setup-spyder como dependência."
requires-python = ">=3.11,<3.13"
dependencies = []

[tool.uv]
package = false
"""

FIXTURE_MAIN = '''\
"""Script de exemplo aberto pelo Spyder na rotina de integração."""

# %% imports
import pandas as pd

from setup_spyder import __version__

# %% dados
vendas = pd.DataFrame(
    {
        "produto": ["cafe", "cha", "cafe", "mate"],
        "regiao": ["sul", "sul", "norte", "norte"],
        "valor": [12.5, 8.0, 15.0, 6.5],
    }
)

# %% exploracao
print(f"setup-spyder {__version__} · pandas {pd.__version__}")
print(vendas.groupby("regiao")["valor"].sum())
'''


def find_repo_root(start: Path | None = None) -> Path:
    """Acha a raiz do repositório subindo a partir do cwd (ou deste arquivo)."""
    seeds = [(start or Path.cwd()).resolve(), Path(__file__).resolve()]
    for seed in seeds:
        for directory in (seed, *seed.parents):
            if (directory / FIXTURE_RELPATH).is_dir():
                return directory
            if (directory / "src" / "setup_spyder" / "cli.py").is_file():
                return directory
    raise FileNotFoundError(
        "raiz do repositório setup-spyder não encontrada; rode a partir do repo."
    )

def clean_fixture(fixture: Path) -> list[str]:
    """Apaga o que a rotina gera, preservando o que está versionado."""
    removed: list[str] = []
    for name in GENERATED:
        target = fixture / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            removed.append(name)
        elif target.exists():
            target.unlink()
            removed.append(name)
    return removed


def scaffold_fixture(fixture: Path) -> None:
    """Garante o `pyproject.toml` e o script de exemplo do projeto descartável."""
    fixture.mkdir(parents=True, exist_ok=True)

    pyproject = fixture / "pyproject.toml"
    if pyproject.is_file():
        log_ok(f"pyproject.toml já existe: {pyproject}")
    else:
        pyproject.write_text(FIXTURE_PYPROJECT)
        log_ok(f"pyproject.toml criado: {pyproject}")

    main_py = fixture / "main.py"
    if main_py.is_file():
        log_ok(f"main.py já existe: {main_py}")
    else:
        main_py.write_text(FIXTURE_MAIN)
        log_ok(f"main.py criado: {main_py}")


def dependency_spec(root: Path, *, ref: str | None, local: bool) -> str:
    """Monta o alvo do ``uv add``: caminho local ou URL do GitHub."""
    if local:
        return str(root)
    if ref:
        return f"git+{REPO_URL}@{ref}"
    return f"git+{REPO_URL}"


def child_env() -> dict[str, str]:
    """Ambiente limpo: o ``uv run`` de fora não pode apontar para o venv errado."""
    env = dict(os.environ)
    for key in INHERITED_ENV_TO_DROP:
        env.pop(key, None)
    return env


def run_step(
    cmd: Sequence[str], *, cwd: Path, title: str, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    log(title)
    log_kv("comando", " ".join(cmd))
    log_kv("cwd", cwd)
    completed = subprocess.run(
        list(cmd),
        cwd=cwd,
        env=child_env(),
        check=False,
        text=True,
        capture_output=capture,
    )
    if completed.returncode == 0:
        log_ok(f"{title} — ok")
    else:
        log_error(f"{title} — falhou (código {completed.returncode})")
        if capture and completed.stderr:
            log(completed.stderr.strip())
    return completed


def run_integration(
    *,
    ref: str | None = None,
    local: bool = False,
    fresh: bool = False,
    no_launch: bool = False,
    spyder_args: Sequence[str] = (),
) -> int:
    """Instala o pacote num projeto novo e abre o Spyder por lá."""
    uv = shutil.which("uv")
    if uv is None:
        log_error("'uv' não está no PATH — instale: curl -LsSf https://astral.sh/uv/install.sh | sh")
        return 1

    try:
        root = find_repo_root()
    except FileNotFoundError as exc:
        log_error(str(exc))
        return 1

    fixture = root / FIXTURE_RELPATH
    spec = dependency_spec(root, ref=ref, local=local)

    log_ok("Rotina de integração do setup-spyder")
    log_kv("repositório", root)
    log_kv("projeto de teste", fixture)
    log_kv("dependência", spec)

    if fresh:
        removed = clean_fixture(fixture)
        if removed:
            log_ok(f"--fresh: removido {', '.join(removed)}")
        else:
            log("--fresh: nada para remover")

    scaffold_fixture(fixture)

    add_cmd = [uv, "add", "--refresh-package", "setup-spyder", spec]
    if run_step(add_cmd, cwd=fixture, title="Instalando setup-spyder").returncode:
        return 1

    check = run_step(
        [uv, "run", "python", "-c", "import setup_spyder; print(setup_spyder.__version__)"],
        cwd=fixture,
        title="Conferindo o import de setup_spyder",
        capture=True,
    )
    if check.returncode:
        return 1
    log_kv("setup_spyder.__version__", check.stdout.strip())

    launch_cmd = [uv, "run", "setup-spyder"]
    if no_launch:
        launch_cmd.append("--no-launch")
    extra = [arg for arg in spyder_args if arg != "--"]
    if extra:
        launch_cmd += ["--", *extra]

    completed = run_step(launch_cmd, cwd=fixture, title="Rodando o Spyder no projeto de teste")
    if completed.returncode:
        return completed.returncode

    log_ok("Integração concluída.")
    if not fresh:
        log("Rode com --fresh para refazer o projeto de teste do zero.")
    return 0


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="integration",
        description=(
            "Cria o projeto descartável em tests/fixture_integration, instala "
            "setup-spyder a partir do GitHub e abre o Spyder por lá."
        ),
    )
    parser.add_argument(
        "--ref",
        default=None,
        help="Branch, tag ou commit do GitHub (padrão: branch default do repo).",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Instala o working tree local em vez de baixar do GitHub.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Apaga o projeto de teste antes de recriá-lo.",
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Só instala e configura; não abre a janela do Spyder.",
    )
    parser.add_argument(
        "spyder_args",
        nargs=argparse.REMAINDER,
        help="Argumentos extras repassados ao setup-spyder (depois de --).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.local and args.ref:
        log_warn("--ref é ignorado junto com --local")
    return run_integration(
        ref=args.ref,
        local=args.local,
        fresh=args.fresh,
        no_launch=args.no_launch,
        spyder_args=args.spyder_args,
    )


if __name__ == "__main__":
    raise SystemExit(main())
