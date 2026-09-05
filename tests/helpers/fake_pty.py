"""Transporte de mentira com o contrato de PTY da secao 6.2 do plano.

Importa `qtpy`, entao so deve ser importado depois de um
``pytest.importorskip("qtpy")``. Fica fora de `conftest.py` de proposito: os
testes de Qt precisam construir workers extras (para provar o `restart`), e um
modulo normal e mais facil de importar do que um conftest.
"""

from __future__ import annotations

from qtpy.QtCore import QObject, Signal


class FakePTYWorker(QObject):
    """Mesmo contrato do PTYWorker real, sem ConPTY, sem processo, sem CLI."""

    sig_output = Signal(bytes)
    sig_exited = Signal(int)
    sig_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.started_with = None
        self.written = []
        self.sizes = []
        self.interrupts = 0
        self.terminated = None
        self.alive = False

    # contrato -----------------------------------------------------------

    def start(self, argv, cwd=None, env=None):
        self.started_with = (list(argv), cwd, dict(env or {}))
        self.alive = True
        self.sig_output.emit("\x1b[1;32mfake\x1b[0m ção\r\n".encode("utf-8"))

    def write(self, data):
        if not self.alive:
            raise RuntimeError("write() em sessao encerrada")
        self.written.append(data if isinstance(data, bytes) else data.encode("utf-8"))

    def resize(self, rows, cols):
        self.sizes.append((rows, cols))

    def interrupt(self):
        self.interrupts += 1
        self.sig_output.emit(b"^C\r\n")

    def terminate(self, grace_period=2.0):
        self.terminated = grace_period
        self.alive = False
        self.sig_exited.emit(130)

    def is_alive(self):
        return self.alive

    # ajudas so para o teste ---------------------------------------------

    def finish(self, code=0):
        self.alive = False
        self.sig_exited.emit(code)

    def fail(self, message="backend indisponivel"):
        self.alive = False
        self.sig_error.emit(message)
