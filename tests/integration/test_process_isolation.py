"""O processo principal nao pode importar a config do Spyder (secao 5.2).

"O processo principal nao deve importar modulos de configuracao do Spyder
antes de preparar o ambiente. Ele deve iniciar um bootstrap filho usando o
mesmo `sys.executable`."

Se `setup_spyder.cli` importar `spyder.config.manager` no topo, o singleton
`CONF` nasce apontando para o diretorio errado - e o perfil isolado deixa de
ser isolado. O teste roda num subprocesso limpo justamente porque o pytest ja
pode ter importado o Spyder por outro caminho.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from helpers.pending import child_env

pytestmark = [pytest.mark.integration, pytest.mark.phase2, pytest.mark.slow]

SONDA = """
import json, sys
import setup_spyder
import setup_spyder.cli
print(json.dumps(sorted(m for m in sys.modules if m.startswith("spyder"))))
"""

PROIBIDOS = (
    "spyder.config.manager",
    "spyder.config.base",
    "spyder.app.start",
    "spyder.api",
)


@pytest.fixture()
def modulos_importados(isolated_home):
    saida = subprocess.run(
        [sys.executable, "-c", SONDA],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(isolated_home),
        timeout=180,
    )
    assert saida.returncode == 0, saida.stderr
    return set(json.loads(saida.stdout.strip().splitlines()[-1]))


@pytest.mark.parametrize("modulo", PROIBIDOS)
def test_importar_setup_spyder_nao_carrega_a_config_do_spyder(
    modulos_importados, modulo
):
    assert modulo not in modulos_importados, (
        f"{modulo} foi importado no processo pai; o CONF nasce com o "
        "diretorio errado (secao 5.2)"
    )


def test_importar_setup_spyder_nao_carrega_qt(isolated_home):
    """Importar o pacote nao pode custar um QApplication."""
    codigo = (
        "import sys, setup_spyder, setup_spyder.cli;"
        "print([m for m in ('PyQt5', 'PyQt6', 'PySide6', 'qtpy')"
        " if m in sys.modules])"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(isolated_home),
        timeout=180,
    )
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip().endswith("[]"), (
        f"Qt importado so por importar o pacote: {saida.stdout.strip()}"
    )


def test_a_ajuda_da_cli_nao_importa_o_spyder(isolated_home):
    """`setup-spyder --help` tem de responder rapido, sem subir o mundo."""
    codigo = (
        "import sys, setup_spyder.cli as cli\n"
        "try:\n"
        "    cli.parse_args(['--help'])\n"
        "except SystemExit:\n"
        "    pass\n"
        "print('SPYDER_IMPORTADO' if any("
        "m == 'spyder' or m.startswith('spyder.') for m in sys.modules) else 'LIMPO')\n"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(isolated_home),
        timeout=180,
    )
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip().endswith("LIMPO")
