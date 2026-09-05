"""Os dois modos da suite, e o ambiente dos subprocessos.

Mora aqui, e nao no `conftest.py` da raiz, por um detalhe do pytest: cada
`conftest.py` sem `__init__.py` ao lado e importado com o nome de modulo
`conftest`, entao `tests/qt/conftest.py` sombreia o da raiz e um
`from conftest import ...` de dentro dele importa a si mesmo. Um modulo normal
nao tem esse problema.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


def flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


#: Com ``SETUP_SPYDER_STRICT=1``, "entrega ainda nao feita" deixa de ser skip
#: e vira falha. E assim que se fecha uma fase do plano.
STRICT = flag("SETUP_SPYDER_STRICT")


def not_implemented(what: str):
    """Marca uma entrega do plano que ainda nao existe.

    Pula por padrao; falha sob ``SETUP_SPYDER_STRICT=1``.
    """
    message = "plano ainda nao entregue: " + what
    if STRICT:
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def require_module(dotted: str, what: str | None = None):
    """Importa um modulo do desenho alvo, ou marca a entrega como pendente."""
    try:
        return importlib.import_module(dotted)
    except Exception as exc:  # ImportError, mas tambem erro em tempo de import
        not_implemented(what or f"modulo {dotted} ({exc.__class__.__name__}: {exc})")


def require_attr(module, name: str, what: str | None = None):
    """Pega um atributo publico do desenho alvo, ou marca a entrega pendente."""
    obj = getattr(module, name, None)
    if obj is None:
        not_implemented(what or f"{module.__name__}.{name}")
    return obj


def child_env(home: Path, **extra: str) -> dict:
    """Ambiente para subprocessos: HOME isolado, sem herdar SPYDER_CONFDIR."""
    env = dict(os.environ)
    env.pop("SPYDER_CONFDIR", None)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra)
    return env


def owning_distribution(package: str = "setup_spyder") -> str:
    """Nome da distribuicao que publica `package`.

    Neste checkout `setup_spyder` viaja dentro da distribuicao `spyder`; num
    repositorio proprio ele seria `setup-spyder`. Os testes de empacotamento
    perguntam em vez de chutar.
    """
    from importlib.metadata import distributions, packages_distributions

    donos = packages_distributions().get(package) or []
    if donos:
        return donos[0]
    for dist in distributions():
        nome = dist.metadata["Name"]
        if nome and nome.replace("_", "-").lower() == package.replace("_", "-"):
            return nome
    not_implemented(f"nenhuma distribuicao instalada publica {package}")
