"""Arranjo dos testes de PTY por plataforma (secao 10).

Contrato exercitado::

    setup_spyder.plugin.pty_worker
        create_pty_worker() -> PTYWorker do sistema operacional corrente
        PTYWorker.start(argv, cwd=None, env=None, rows=24, cols=80)
        PTYWorker.write(data) / resize(rows, cols) / interrupt()
        PTYWorker.terminate(grace_period=...)
        sinais sig_output(bytes), sig_exited(int), sig_error(str)

Os testes falam com a TUI deterministica de `helpers/fake_tui.py`: nada de
rede, conta ou credencial, e o mesmo roteiro vale para ConPTY e para PTY
POSIX.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from helpers.pending import pular_diretorio, require_attr, require_module, requisitos

# Sem `pytest.importorskip` no topo: num conftest aninhado ele derruba a coleta
# da sessao inteira (veja `helpers.pending.pular_diretorio`).
FALTA = requisitos(("pytestqt", "o PTYWorker e um QObject; use pytest-qt"))

pytest_collection_modifyitems = pular_diretorio(Path(__file__).parent, FALTA)

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
FAKE_TUI = HELPERS / "fake_tui.py"

pytestmark = pytest.mark.pty


@pytest.fixture(scope="session")
def pty_module():
    return require_module("setup_spyder.plugin.pty_worker", "PTYWorker (Fase 1)")


@pytest.fixture(scope="session")
def backend_disponivel():
    """O backend de plataforma esta instalado? (matriz de compatibilidade)"""
    modulo = "winpty" if sys.platform == "win32" else "ptyprocess"
    return pytest.importorskip(
        modulo, reason=f"backend de PTY ausente: {modulo}"
    )


class Session:
    """Worker + acumulador de saida, para assercoes legiveis."""

    def __init__(self, worker, qtbot):
        self.worker = worker
        self.qtbot = qtbot
        self.output = bytearray()
        self.exit_code = None
        self.errors = []
        worker.sig_output.connect(self.output.extend)
        worker.sig_exited.connect(self._on_exit)
        worker.sig_error.connect(self.errors.append)

    def _on_exit(self, code):
        self.exit_code = code

    # leitura ------------------------------------------------------------

    @property
    def text(self) -> str:
        return self.output.decode("utf-8", "replace")

    def wait_for(self, trecho: str, timeout: int = 10000) -> str:
        self.qtbot.waitUntil(lambda: trecho in self.text, timeout=timeout)
        return self.text

    def wait_exit(self, timeout: int = 10000) -> int:
        self.qtbot.waitUntil(lambda: self.exit_code is not None, timeout=timeout)
        return self.exit_code


@pytest.fixture(scope="session")
def baseline_ports():
    """Portas em escuta antes de qualquer PTY subir."""
    from helpers.procutil import listening_ports

    return listening_ports()


@pytest.fixture()
def session(qtbot, pty_module, backend_disponivel, baseline_ports, tmp_path,
            project_root):
    """Sobe a TUI deterministica dentro de um PTY real e devolve a sessao."""
    create = require_attr(pty_module, "create_pty_worker")
    pid_file = tmp_path / "neto.pid"
    worker = create()
    sessao = Session(worker, qtbot)
    sessao.pid_file = pid_file
    sessao.baseline_ports = baseline_ports
    worker.start(
        [sys.executable, "-u", str(FAKE_TUI), str(pid_file)],
        cwd=str(project_root),
        rows=24,
        cols=80,
    )
    sessao.wait_for("<READY>")
    yield sessao
    if worker.is_alive():
        worker.terminate(grace_period=2.0)
