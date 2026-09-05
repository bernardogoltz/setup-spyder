"""Degradar so o painel, nunca o Spyder (secoes 6.1 e 8).

"Falhas de compatibilidade devem aparecer no proprio painel, com acao
sugerida; no log/stderr do launcher; sem ocultar excecoes de importacao."
"""

from __future__ import annotations

import pytest

from helpers.pending import require_attr

pytestmark = [pytest.mark.qt, pytest.mark.phase3]


@pytest.fixture()
def terminal_sem_backend(qtbot, widget_module, monkeypatch, project_root):
    """Widget cujo backend de PTY levanta ImportError na criacao."""

    def explode(*args, **kwargs):
        raise ImportError("No module named 'winpty'")

    require_attr(widget_module, "create_pty_worker")
    monkeypatch.setattr(widget_module, "create_pty_worker", explode)
    cls = require_attr(widget_module, "AITerminalWidget")
    widget = cls(name="setup_spyder_ai", plugin=None, parent=None)
    qtbot.addWidget(widget)
    widget.set_working_directory(str(project_root))
    return widget


def test_construir_o_painel_sem_backend_nao_estoura(terminal_sem_backend):
    assert terminal_sem_backend is not None


def test_start_session_sem_backend_vira_estado_de_erro(qtbot, terminal_sem_backend):
    with qtbot.waitSignal(terminal_sem_backend.sig_state_changed, timeout=2000):
        terminal_sem_backend.start_session()
    assert terminal_sem_backend.state == "error"


def test_a_mensagem_de_erro_aparece_no_painel_com_acao_sugerida(
    qtbot, terminal_sem_backend
):
    terminal_sem_backend.start_session()
    qtbot.waitUntil(lambda: terminal_sem_backend.state == "error", timeout=2000)
    mensagem = terminal_sem_backend.get_error_message()
    assert mensagem, "o painel precisa dizer o que aconteceu"
    assert "winpty" in mensagem.lower(), "a causa original nao pode ser engolida"
    assert any(
        pista in mensagem.lower() for pista in ("install", "instale", "pip", "uv")
    ), "secao 6.1: a mensagem precisa trazer a acao sugerida"


def test_o_erro_tambem_vai_para_o_log(qtbot, terminal_sem_backend, caplog):
    import logging

    with caplog.at_level(logging.ERROR):
        terminal_sem_backend.start_session()
        qtbot.waitUntil(lambda: terminal_sem_backend.state == "error", timeout=2000)
    assert any("winpty" in registro.getMessage() for registro in caplog.records), (
        "secao 6.1: a falha tambem precisa aparecer no log/stderr"
    )


def test_sem_cli_instalada_o_painel_continua_utilizavel(
    qtbot, terminal, patched_backend, bin_dir
):
    """Definicao de pronto: "continuar abrindo o Spyder normalmente quando
    nenhuma CLI estiver instalada". No painel, isso e uma instrucao curta."""
    terminal.refresh_providers()
    mensagem = terminal.get_error_message() or terminal.get_hint_message()
    assert mensagem, "sem codex nem claude, o painel precisa instruir o usuario"
    assert patched_backend.started_with is None, (
        "sem CLI disponivel nada pode ser iniciado"
    )


def test_ambiguidade_nao_inicia_sessao_sozinha(
    qtbot, terminal, patched_backend, fake_bin
):
    fake_bin("codex")
    fake_bin("claude")
    terminal.refresh_providers()
    assert patched_backend.started_with is None
    assert terminal.get_provider_selector().isEnabled() is True
