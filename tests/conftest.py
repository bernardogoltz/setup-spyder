"""Fixtures compartilhadas da suite `setup-spyder` + AI Terminal.

A suite e escrita contra `docs/plan.md` (revisao de 2026-09-04). Boa parte do
plano ainda nao existe em codigo, entao a suite tem dois modos:

* **modo padrao** - testes de modulos ainda nao implementados sao *pulados*
  com uma mensagem dizendo qual entrega do plano falta. O que ja existe
  (launcher, perfis e bootstrap filho da Fase 2) e testado de verdade e
  precisa passar.
* **modo estrito** - com ``SETUP_SPYDER_STRICT=1`` os mesmos skips viram
  falhas. E assim que cada fase do plano "fecha": ao terminar a Fase 3, por
  exemplo, roda-se ``SETUP_SPYDER_STRICT=1 pytest -m "phase0 or phase3"``.

Variaveis de ambiente reconhecidas:

``SETUP_SPYDER_STRICT``   1 -> transforma "ainda nao implementado" em falha.
``SETUP_SPYDER_E2E``      1 -> habilita os testes que abrem o Spyder de fato.
``SETUP_SPYDER_WHEEL``    caminho de uma wheel construida, para os testes de
                          empacotamento da Fase 6.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import stat
import sys
import textwrap
from pathlib import Path

import pytest

HELPERS = Path(__file__).parent / "helpers"


# Ambiente de execucao ---------------------------------------------------

# `not_implemented` / `require_module` / `require_attr` / `child_env` moram em
# helpers/pending.py e sao reexportados aqui so por conveniencia: os arquivos de
# teste devem importar de `helpers.pending`, porque um `conftest.py` aninhado
# sombreia o nome de modulo `conftest`.
from helpers.pending import (  # noqa: E402,F401
    STRICT,
    child_env,
    flag as _flag,
    not_implemented,
    require_attr,
    require_module,
)


# Pacote sob teste -------------------------------------------------------


@pytest.fixture(scope="session")
def setup_spyder():
    """O pacote instalado. Ausencia aqui e falha, nao skip."""
    try:
        return importlib.import_module("setup_spyder")
    except ImportError as exc:  # pragma: no cover - ambiente mal montado
        pytest.fail(
            "setup_spyder nao esta instalado neste ambiente "
            f"({exc}). Rode a suite no venv do projeto."
        )


@pytest.fixture(scope="session")
def setup_spyder_cli():
    return importlib.import_module("setup_spyder.cli")


@pytest.fixture(scope="session")
def setup_spyder_fork():
    return importlib.import_module("setup_spyder.fork")


@pytest.fixture(scope="session")
def spyder_available() -> bool:
    return importlib.util.find_spec("spyder") is not None


# Projetos temporarios ---------------------------------------------------


def _make_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "demo.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    """Raiz de projeto trivial, caminho ASCII e sem espacos."""
    return _make_project(tmp_path / "projeto")


@pytest.fixture()
def awkward_project_root(tmp_path: Path) -> Path:
    """Raiz com espaco e caracteres nao-ASCII (criterio da secao 10 do plano)."""
    return _make_project(tmp_path / "proj com espaço" / "análise maçã")


# PATH controlado --------------------------------------------------------


@pytest.fixture()
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Diretorio que passa a ser o *unico* PATH do processo de teste.

    Serve para provar a descoberta de `codex`/`claude` sem depender do que
    esta instalado na maquina de quem roda a suite.
    """
    directory = tmp_path / "bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", str(directory))
    return directory


@pytest.fixture()
def fake_bin(bin_dir: Path):
    """Cria um executavel falso, descobrivel por ``shutil.which``.

    Retorna uma fabrica ``fake_bin(nome, exit_code=0) -> Path``. O programa
    grava os argumentos recebidos em ``<nome>.argv`` no mesmo diretorio, o que
    permite provar que o argv chegou como lista, sem shell no meio.
    """

    def factory(name: str, exit_code: int = 0) -> Path:
        payload = HELPERS / "fake_cli.py"
        record = bin_dir / f"{name}.argv"
        if os.name == "nt":
            target = bin_dir / f"{name}.cmd"
            target.write_text(
                "@echo off\r\n"
                f'"{sys.executable}" "{payload}" "{record}" {exit_code} %*\r\n',
                encoding="utf-8",
            )
        else:
            target = bin_dir / name
            target.write_text(
                textwrap.dedent(
                    f"""\
                    #!/bin/sh
                    exec "{sys.executable}" "{payload}" "{record}" {exit_code} "$@"
                    """
                ),
                encoding="utf-8",
            )
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        return target

    return factory


# Guardas de isolamento --------------------------------------------------


def _signature(root: Path):
    if not root.exists():
        return None
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


#: Nomes que o Spyder usa para a config global: `.spyder-py3` numa versao
#: estavel, `.spyder-py3-dev` num checkout de desenvolvimento (o fork e
#: 5.6.0.dev0). Os dois tem de ficar intactos.
GLOBAL_CONF_DIRNAMES = (".spyder-py3", ".spyder-py3-dev")


def global_conf_dirs(home: Path) -> list[Path]:
    return [home / name for name in GLOBAL_CONF_DIRNAMES]


@pytest.fixture()
def global_conf_guard():
    """Falha se o teste tocar em ``~/.spyder-py3`` ou ``~/.spyder-py3-dev``.

    Criterio de aceitacao: "Nenhuma escrita na configuracao global".
    """
    roots = global_conf_dirs(Path.home())
    before = {root: _signature(root) for root in roots}
    yield roots
    for root in roots:
        after = _signature(root)
        if before[root] is None:
            assert after is None, f"o teste criou a config global do usuario: {root}"
        else:
            changed = sorted(set(after or {}).symmetric_difference(before[root]))
            assert after == before[root], (
                f"o teste alterou a config global do usuario em {root}: {changed}"
            )


@pytest.fixture()
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """HOME/USERPROFILE apontando para um diretorio descartavel."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return home


# Opt-ins ----------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_enabled():
    if not _flag("SETUP_SPYDER_E2E"):
        pytest.skip("defina SETUP_SPYDER_E2E=1 para abrir o Spyder de verdade")
    return True


def pytest_report_header(config):
    modes = ["strict" if STRICT else "tolerante (skips = entregas pendentes)"]
    if _flag("SETUP_SPYDER_E2E"):
        modes.append("e2e ligado")
    wheel = os.environ.get("SETUP_SPYDER_WHEEL")
    if wheel:
        modes.append(f"wheel={wheel}")
    return "setup-spyder plan suite: " + ", ".join(modes)

