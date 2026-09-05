"""Sobe um `QWebEngineView` de verdade e roda um JavaScript nele.

Roda sempre num subprocesso, chamado por `helpers.webengine`. Nunca e coletado
pelo pytest (`python_files = ["test_*.py"]`).

Codigos de saida: 0 ok, 2 a pagina nao carregou, 3 o JavaScript respondeu
errado, 4 estourou o tempo. Um abort do Chromium nao devolve codigo nenhum - o
processo morre por sinal, e e justamente isso que a sonda existe para detectar.
"""

from __future__ import annotations

import sys

# Antes de existir um QApplication: o PyQt5 exige `Qt.AA_ShareOpenGLContexts`,
# que o import de `QtWebEngineWidgets` liga sozinho. Mesmo motivo do topo de
# `tests/qt/conftest.py`.
from qtpy.QtWebEngineWidgets import QWebEngineView

from qtpy.QtCore import Qt, QTimer
from qtpy.QtWidgets import QApplication

#: Um teto interno, menor que o do processo pai, para a sonda conseguir
#: devolver o codigo 4 em vez de ser morta de fora.
LIMITE_MS = 45_000


def main() -> int:
    app = QApplication([])
    view = QWebEngineView()
    # O mesmo que os testes fazem: a view e mostrada, mas sem janela nenhuma.
    view.setAttribute(Qt.WA_DontShowOnScreen)
    view.resize(320, 200)
    view.show()

    def on_javascript(valor):
        app.exit(0 if valor == 2 else 3)

    def on_load(ok):
        if not ok:
            app.exit(2)
            return
        view.page().runJavaScript("1 + 1", on_javascript)

    view.loadFinished.connect(on_load)
    view.setHtml("<!doctype html><title>probe</title><body>probe</body>")
    QTimer.singleShot(LIMITE_MS, lambda: app.exit(4))
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
