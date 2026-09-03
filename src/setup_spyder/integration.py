"""Rotina de integração: instala o pacote a partir do GitHub e abre o Spyder.

Cria o projeto descartável em ``tests/fixture_integration/``, adiciona
``setup-spyder`` vindo do GitHub e roda ``uv run setup-spyder`` lá dentro — o
mesmo fluxo que outra pessoa faria em outro repositório. No fim imprime o
resumo e apaga tudo o que gerou.

Uso::

    uv run integration               # instala do GitHub e abre o Spyder
    uv run integration --no-launch   # só instala e confere o import
    uv run integration --local       # usa o working tree em vez do GitHub
    uv run integration --ref develop # instala a partir de outro branch/tag
    uv run integration --keep        # não apaga o projeto de teste no fim
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from setup_spyder.cli import (
    REPO_URL,
    console,
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


def short(value: object, root: Path) -> str:
    """Encolhe caminhos e URLs para caberem numa linha do resumo."""
    text = str(value)
    if text.startswith("git+"):
        return text.removeprefix("git+").removeprefix("https://").removeprefix("github.com/")
    try:
        return str(Path(text).relative_to(root))
    except ValueError:
        return text


class Step(NamedTuple):
    """Uma etapa da rotina, do jeito que aparece no resumo final."""

    title: str
    ok: bool
    detail: str


def print_summary(steps: Sequence[Step], *, code: int, location: str) -> None:
    """Resumo final: uma linha por etapa, verde se passou, vermelho se não."""
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2), expand=False)
    table.add_column(justify="center", width=1)
    table.add_column(style="bold white")
    table.add_column(style="dim", overflow="fold")
    for step in steps:
        glyph = Text("✓", style="bold green") if step.ok else Text("✗", style="bold red")
        table.add_row(glyph, step.title, step.detail)

    ok = code == 0
    verdict = Text()
    verdict.append("Rotina de integração ", style="white")
    verdict.append("concluída com sucesso" if ok else f"falhou (código {code})",
                   style="bold green" if ok else "bold red")
    verdict.append("\n")
    verdict.append(location, style="dim")

    console.print()
    console.print(
        Panel(
            Group(verdict, Text(), table),
            title="[bold green]◆ integração ok[/]" if ok else "[bold red]◆ integração falhou[/]",
            subtitle="[dim]projeto de teste descartável · não toca no ambiente principal[/]",
            border_style="green" if ok else "red",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()


def cleanup_fixture(fixture: Path, *, keep: bool, failed: bool) -> None:
    """Apaga o que a rotina gerou — o projeto de teste é descartável."""
    if keep:
        log_warn(f"--keep: mantendo o projeto de teste em {fixture}")
        return

    log(f"Limpando o projeto de teste: {fixture}")
    removed = clean_fixture(fixture)
    for name in removed:
        log_kv("removido", name)
    if removed:
        log_ok("Fixture limpa — nada ficou instalado fora dela.")
    else:
        log_ok("Nada para limpar; a fixture já estava vazia.")
    if failed:
        log("Rode com --keep para inspecionar o projeto de teste depois de uma falha.")


def _run_steps(
    uv: str,
    root: Path,
    fixture: Path,
    spec: str,
    *,
    no_launch: bool,
    spyder_args: Sequence[str],
    steps: list[Step],
) -> int:
    scaffold_fixture(fixture)
    steps.append(Step("Projeto de teste criado", True, short(fixture, root)))

    add = run_step(
        [uv, "add", "--refresh-package", "setup-spyder", spec],
        cwd=fixture,
        title="Instalando setup-spyder",
    )
    steps.append(Step("setup-spyder instalado", add.returncode == 0, short(spec, root)))
    if add.returncode:
        return 1

    check = run_step(
        [uv, "run", "python", "-c", "import setup_spyder; print(setup_spyder.__version__)"],
        cwd=fixture,
        title="Conferindo o import de setup_spyder",
        capture=True,
    )
    version = check.stdout.strip()
    steps.append(
        Step(
            "import setup_spyder",
            check.returncode == 0,
            f"versão {version}" if check.returncode == 0 else "import falhou",
        )
    )
    if check.returncode:
        return 1
    log_kv("setup_spyder.__version__", version)

    launch_cmd = [uv, "run", "setup-spyder"]
    if no_launch:
        launch_cmd.append("--no-launch")
    extra = [arg for arg in spyder_args if arg != "--"]
    if extra:
        launch_cmd += ["--", *extra]

    completed = run_step(
        launch_cmd, cwd=fixture, title="Rodando o Spyder no projeto de teste"
    )
    steps.append(
        Step(
            "Spyder configurado" if no_launch else "Spyder aberto e encerrado",
            completed.returncode == 0,
            "uv " + " ".join(launch_cmd[1:]),
        )
    )
    return completed.returncode


def run_integration(
    *,
    ref: str | None = None,
    local: bool = False,
    fresh: bool = False,
    no_launch: bool = False,
    keep: bool = False,
    spyder_args: Sequence[str] = (),
) -> int:
    """Instala o pacote num projeto novo, abre o Spyder e limpa tudo no fim."""
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
        log_ok(f"--fresh: removido {', '.join(removed)}" if removed else "--fresh: nada para remover")

    steps = [
        Step("Ambiente isolado", True, "sem herança do uv run externo")
    ]
    code = 1
    try:
        code = _run_steps(
            uv, root, fixture, spec, no_launch=no_launch, spyder_args=spyder_args, steps=steps
        )
        return code
    finally:
        print_summary(steps, code=code, location=short(fixture, root))
        cleanup_fixture(fixture, keep=keep, failed=code != 0)


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
        "--keep",
        action="store_true",
        help="Não apaga o projeto de teste ao final (útil para inspecionar).",
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
        keep=args.keep,
        spyder_args=args.spyder_args,
    )


if __name__ == "__main__":
    raise SystemExit(main())
