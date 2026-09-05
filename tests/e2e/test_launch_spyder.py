"""E2E: abre o Spyder de verdade. Opt-in com ``SETUP_SPYDER_E2E=1``.

Cobre os criterios que so aparecem com a janela no ar:

* o Spyder abre mesmo sem CLI e sem backend de PTY;
* nenhum processo do agente fica orfao depois de fechar;
* o plugin nao abre porta TCP.

Cada teste sobe o processo, espera a janela existir e encerra. Precisa de uma
sessao grafica (no Linux, ``xvfb-run`` serve).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from helpers.pending import child_env
from helpers.procutil import listening_ports, wait_gone

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.phase6]

ESPERA_JANELA = 120.0


@pytest.fixture(autouse=True)
def _opt_in(e2e_enabled, spyder_available):
    if not spyder_available:
        pytest.skip("Spyder nao esta instalado neste ambiente")


@pytest.fixture()
def spyder(isolated_home, project_root):
    """Sobe o `setup-spyder`, entrega o processo e garante o encerramento."""
    processos = []

    def subir(*argv, timeout=ESPERA_JANELA):
        processo = subprocess.Popen(
            [sys.executable, "-m", "setup_spyder", "-w", str(project_root), *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
        errors="replace",
            env=child_env(isolated_home),
        )
        processos.append(processo)
        # Sem um sinal melhor, espera-se o processo *sobreviver* a subida:
        # uma falha de import derruba o launcher em poucos segundos.
        limite = time.monotonic() + min(30.0, timeout)
        while time.monotonic() < limite:
            if processo.poll() is not None:
                saida = processo.stdout.read() if processo.stdout else ""
                pytest.fail(
                    f"o Spyder morreu na subida (codigo {processo.returncode}):\n{saida}"
                )
            time.sleep(0.5)
        return processo

    yield subir

    for processo in processos:
        if processo.poll() is None:
            processo.terminate()
            try:
                processo.wait(timeout=60)
            except subprocess.TimeoutExpired:  # pragma: no cover
                processo.kill()


def test_o_spyder_abre_sem_nenhuma_cli_instalada(spyder, bin_dir):
    """Definicao de pronto: "continuar abrindo o Spyder normalmente quando
    nenhuma CLI estiver instalada"."""
    processo = spyder("--agent", "none")
    assert processo.poll() is None


def test_o_spyder_abre_com_agent_auto(spyder):
    processo = spyder("--agent", "auto")
    assert processo.poll() is None


def test_nenhum_processo_fica_orfao_depois_de_fechar(spyder):
    processo = spyder("--agent", "none")
    filhos = []
    try:
        import psutil

        filhos = [p.pid for p in psutil.Process(processo.pid).children(recursive=True)]
    except ImportError:
        pytest.skip("instale psutil para rastrear a arvore de processos")

    processo.terminate()
    processo.wait(timeout=120)
    sobreviventes = [pid for pid in filhos if not wait_gone(pid, timeout=30.0)]
    assert not sobreviventes, f"processos orfaos: {sobreviventes}"


def test_o_plugin_nao_abre_porta_tcp(spyder):
    """Criterio de aceitacao: nenhum servidor local para o transporte."""
    if listening_ports() is None:
        pytest.skip("instale psutil para checar portas em escuta")
    processo = spyder("--agent", "none")
    antes = listening_ports(os.getpid()) or set()
    time.sleep(5)
    depois = listening_ports(processo.pid) or set()
    assert depois - antes == set(), (
        f"o Spyder do setup-spyder passou a escutar em {sorted(depois - antes)}"
    )


def test_a_config_global_continua_intacta_depois_de_abrir(spyder, isolated_home):
    processo = spyder("--agent", "none")
    processo.terminate()
    processo.wait(timeout=120)
    assert not (isolated_home / ".spyder-py3").exists()
