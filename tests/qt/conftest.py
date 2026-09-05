"""Arranjo dos testes de Qt: `pytest-qt`, um QApplication e um PTY falso.

O backend falso (`helpers.fake_pty.FakePTYWorker`) implementa o contrato
minimo da secao 6.2 do plano::

    start(argv, cwd, env)   write(data)   resize(rows, cols)
    interrupt()             terminate(grace_period)
    sinais de saida, termino e erro

Com ele os testes de widget nao dependem de ConPTY, de `codex` nem de
`claude`: exercitam so a ligacao entre a UI e o transporte.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers.pending import pular_diretorio, require_attr, require_module, requisitos

# `QtWebEngineWidgets` precisa ser importado antes de existir um QApplication
# (PyQt5 exige `Qt.AA_ShareOpenGLContexts` antes da criacao). O Spyder faz isso
# cedo em `mainwindow.py`; aqui o `qapp` do pytest-qt e criado tarde, entao o
# import fica no topo do conftest, antes de qualquer fixture.
#
# Nada de `pytest.importorskip` aqui: num conftest aninhado ele derruba a
# coleta da sessao inteira (veja `helpers.pending.pular_diretorio`). Se algo
# faltar, so os testes desta pasta sao pulados, com a razao.
FALTA = requisitos(
    ("pytestqt", "testes de Qt exigem pytest-qt"),
    ("qtpy", "testes de Qt exigem qtpy"),
    ("qtpy.QtWebEngineWidgets", "o painel exige QtWebEngine (PyQtWebEngine)"),
)

pytest_collection_modifyitems = pular_diretorio(Path(__file__).parent, FALTA)


@pytest.fixture(autouse=True)
def _silencia_registro_duplicado():
    """Cada teste constroi outro `AITerminalWidget` com o mesmo PLUGIN_NAME.

    O Spyder avisa que as acoes/toolbars de base (`dock_pane`, `options_menu`,
    ...) ja existem no registro global daquele nome - inerente a criar varios
    painéis do mesmo plugin num processo, e irrelevante para o que se testa.
    """
    import warnings

    warnings.filterwarnings(
        "ignore", message="There already exists a reference", category=UserWarning
    )
    yield


@pytest.fixture()
def fake_worker():
    from helpers.fake_pty import FakePTYWorker

    return FakePTYWorker()


@pytest.fixture()
def worker_factory():
    """Fabrica que registra cada worker criado, para provar o `restart`."""
    from helpers.fake_pty import FakePTYWorker

    criados: list[FakePTYWorker] = []

    def factory(*args, **kwargs):
        worker = FakePTYWorker()
        criados.append(worker)
        return worker

    factory.criados = criados
    return factory


@pytest.fixture()
def widget_module():
    return require_module(
        "setup_spyder.plugin.main_widget", "AITerminalWidget (Fase 3)"
    )


@pytest.fixture()
def patched_backend(widget_module, fake_worker, monkeypatch):
    """Injeta o PTY falso na fabrica que o widget usa.

    O contrato de testabilidade e um unico ponto de criacao,
    ``main_widget.create_pty_worker(...)``, com import tardio do backend de
    plataforma la dentro (secao 6.1).
    """
    require_attr(widget_module, "create_pty_worker")
    monkeypatch.setattr(
        widget_module, "create_pty_worker", lambda *a, **k: fake_worker
    )
    return fake_worker


@pytest.fixture()
def terminal(qtbot, widget_module, patched_backend, project_root):
    cls = require_attr(widget_module, "AITerminalWidget")
    widget = cls(name="setup_spyder_ai", plugin=None, parent=None)
    qtbot.addWidget(widget)
    widget.set_working_directory(str(project_root))
    return widget


@pytest.fixture(scope="session")
def live_page():
    """Exige um QtWebEngine que carrega a pagina e executa JavaScript.

    Montar o widget sobrevive a um QtWebEngine capenga: a view e criada e a
    pagina simplesmente nunca carrega. Esperar `_page_ready` ou chamar
    `runJavaScript`, nao - o Chromium aborta e leva a sessao inteira do pytest
    junto, sem excecao nenhuma para interceptar. A pergunta e feita antes, num
    subprocesso (`helpers.webengine`).
    """
    from helpers.webengine import motivo_indisponivel

    razao = motivo_indisponivel()
    if razao:
        pytest.skip(razao)
