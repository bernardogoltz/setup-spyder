"""O Spyder acha o plugin - e continua abrindo quando o backend falha.

Secao 9 (Fase 0: "entry point descoberto no Spyder 5.5.6 e no fork local") e
secao 6.1 ("Plugin sumir por ImportError no carregamento" na tabela de riscos).

`find_external_plugins()` engole `ImportError` e so imprime em STDERR, entao a
diferenca entre "plugin degradado" e "plugin invisivel" e exatamente o que
estes testes medem.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from helpers.pending import child_env, not_implemented

pytestmark = [pytest.mark.integration, pytest.mark.slow]

NOME = "setup_spyder_ai"

DESCOBRIR = """
import json, sys
from spyder.app.find_plugins import find_external_plugins
achados = find_external_plugins()
print("RESULTADO " + json.dumps(sorted(achados)))
"""

# Mesmo teste, mas com o backend de PTY sabotado antes de qualquer import.
DESCOBRIR_SEM_BACKEND = """
import builtins, json, sys

_real = builtins.__import__
BLOQUEADOS = {"winpty", "ptyprocess", "pexpect"}

def bloqueia(name, *args, **kwargs):
    if name.split(".")[0] in BLOQUEADOS:
        raise ImportError("No module named %r (bloqueado pelo teste)" % name)
    return _real(name, *args, **kwargs)

builtins.__import__ = bloqueia

from spyder.app.find_plugins import find_external_plugins
achados = find_external_plugins()
print("RESULTADO " + json.dumps(sorted(achados)))
"""


def _descobrir(codigo, isolated_home):
    saida = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(isolated_home),
        timeout=300,
    )
    linhas = [
        linha for linha in saida.stdout.splitlines() if linha.startswith("RESULTADO ")
    ]
    assert linhas, f"a sonda nao respondeu.\nstdout={saida.stdout}\nstderr={saida.stderr}"
    return json.loads(linhas[-1][len("RESULTADO ") :]), saida.stderr


@pytest.fixture(autouse=True)
def _exige_spyder(spyder_available):
    if not spyder_available:
        pytest.skip("Spyder nao esta instalado neste ambiente")


def _plugins_do_pacote():
    """Nomes de entry point `spyder.plugins` publicados por este pacote."""
    import sys

    if sys.version_info < (3, 10):
        from importlib_metadata import entry_points
    else:
        from importlib.metadata import entry_points

    return sorted(
        ep.name
        for ep in entry_points(group="spyder.plugins")
        if ep.value.split(":")[0].startswith("setup_spyder")
    )


@pytest.mark.phase0
def test_o_spyder_descobre_os_plugins_do_pacote(isolated_home):
    publicados = _plugins_do_pacote()
    if not publicados:
        not_implemented("nenhum plugin externo publicado por setup_spyder")
    achados, stderr = _descobrir(DESCOBRIR, isolated_home)
    faltando = [nome for nome in publicados if nome not in achados]
    assert not faltando, (
        f"o Spyder nao achou {faltando} (achou {achados}). "
        f"stderr={stderr.strip()[:400]}"
    )


@pytest.mark.phase0
def test_a_descoberta_nao_levanta_spyder_api_error(isolated_home):
    """`SpyderAPIError` aqui significa entry point != PluginClass.NAME."""
    _, stderr = _descobrir(DESCOBRIR, isolated_home)
    assert "SpyderAPIError" not in stderr, stderr


@pytest.mark.phase0
def test_os_plugins_sobrevivem_a_ausencia_do_backend_de_pty(isolated_home):
    """Secao 6.1: import tardio, para o plugin degradar em vez de sumir.

    O mesmo vale para qualquer dependencia opcional: com `winpty`,
    `ptyprocess` e `pexpect` bloqueados, o painel pode ficar inutilizavel, mas
    o plugin tem de continuar aparecendo na descoberta.
    """
    publicados = _plugins_do_pacote()
    if not publicados:
        not_implemented("nenhum plugin externo publicado por setup_spyder")
    achados, stderr = _descobrir(DESCOBRIR_SEM_BACKEND, isolated_home)
    faltando = [nome for nome in publicados if nome not in achados]
    assert not faltando, (
        f"sem backend de PTY, {faltando} sumiu da descoberta em vez de "
        f"aparecer degradado. stderr={stderr.strip()[:400]}"
    )


@pytest.mark.phase3
def test_o_plugin_do_plano_esta_publicado(isolated_home):
    """Fase 3: o entry point `setup_spyder_ai` do AI Terminal."""
    if NOME not in _plugins_do_pacote():
        not_implemented(
            f"plugin externo {NOME} (publicados hoje: {_plugins_do_pacote()})"
        )
    achados, stderr = _descobrir(DESCOBRIR, isolated_home)
    assert NOME in achados, stderr


@pytest.mark.phase3
def test_a_falha_de_import_nao_e_silenciosa(isolated_home):
    """Secao 10: "capturar stderr/logs para que falhas de descoberta do plugin
    nao sejam silenciosas"."""
    publicados = _plugins_do_pacote()
    achados, stderr = _descobrir(DESCOBRIR_SEM_BACKEND, isolated_home)
    if publicados and any(nome not in achados for nome in publicados):
        assert stderr.strip(), (
            "um plugin sumiu e nada foi escrito em stderr - falha invisivel"
        )
