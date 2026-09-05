"""Registro do dock, barra de acoes e indicador de estado (secoes 6 e 7)."""

from __future__ import annotations

import pytest

from helpers.pending import require_attr, require_module

pytestmark = [pytest.mark.qt, pytest.mark.phase3]

ACOES_ESPERADAS = {
    "new_session",
    "restart",
    "interrupt",
    "clear",
    "close_session",
}


@pytest.fixture()
def plugin_module():
    return require_module("setup_spyder.plugin.plugin", "AITerminalPlugin (Fase 3)")


def test_o_plugin_declara_o_widget_como_container(plugin_module):
    plugin_class = require_attr(plugin_module, "AITerminalPlugin")
    widget_class = plugin_class.WIDGET_CLASS
    assert widget_class.__name__ == "AITerminalWidget"


def test_o_dock_tem_titulo_e_icone(qtbot, terminal):
    assert terminal.get_title(), "o dock precisa de um titulo legivel"
    assert terminal.get_focus_widget() is not None


@pytest.mark.parametrize("acao", sorted(ACOES_ESPERADAS))
def test_a_barra_tem_as_acoes_da_secao_7(terminal, acao):
    assert terminal.get_action(acao) is not None, f"acao {acao!r} nao existe"


def test_o_seletor_de_provedor_esta_na_barra(terminal):
    seletor = terminal.get_provider_selector()
    assert seletor is not None
    nomes = {seletor.itemText(i) for i in range(seletor.count())}
    assert {"codex", "claude"} <= {nome.lower() for nome in nomes}


def test_o_indicador_reflete_o_estado_do_processo(qtbot, terminal, patched_backend):
    assert terminal.get_state_label().text().lower().startswith(("idle", "sem sess"))
    terminal.start_session()
    qtbot.waitUntil(
        lambda: "running" in terminal.get_state_label().text().lower(), timeout=2000
    )
    patched_backend.finish(0)
    qtbot.waitUntil(
        lambda: "exited" in terminal.get_state_label().text().lower(), timeout=2000
    )


def test_acoes_de_sessao_ficam_desabilitadas_sem_processo(terminal):
    for acao in ("interrupt", "close_session"):
        assert terminal.get_action(acao).isEnabled() is False


def test_acoes_de_sessao_habilitam_com_processo_vivo(qtbot, terminal):
    terminal.start_session()
    qtbot.waitUntil(lambda: terminal.state == "running", timeout=2000)
    for acao in ("interrupt", "close_session"):
        assert terminal.get_action(acao).isEnabled() is True


def test_trocar_de_provedor_com_sessao_viva_pede_confirmacao(
    qtbot, terminal, patched_backend, monkeypatch
):
    """Secao 7: "troca de provedor: encerra a sessao atual com confirmacao
    quando houver processo ativo"."""
    perguntou = []
    monkeypatch.setattr(
        terminal, "confirm_replace_session", lambda *a, **k: perguntou.append(True)
    )
    terminal.start_session()
    terminal.set_provider("claude")
    assert perguntou, "trocou de provedor sem confirmar com o usuario"


def test_trocar_de_diretorio_nao_move_sessao_em_execucao(
    terminal, patched_backend, tmp_path
):
    """Secao 7: a troca vale para novas sessoes."""
    terminal.start_session()
    _, cwd_original, _ = patched_backend.started_with
    terminal.set_working_directory(str(tmp_path / "outro"))
    assert patched_backend.started_with[1] == cwd_original
    assert patched_backend.alive is True


def test_a_campainha_e_uma_preferencia_e_nao_um_monkeypatch_global(terminal):
    """Secao 7: sem monkeypatch global de `QApplication.beep`.

    Compara com ``==`` e nao com ``is``: no PyQt5 cada acesso a um metodo
    estatico devolve um wrapper novo do sip, entao ate
    ``QApplication.beep is QApplication.beep`` e False. A igualdade de
    ``builtin_function_or_method`` continua distinguindo o original de um
    monkeypatch (uma funcao Python nunca e igual ao builtin).
    """
    from qtpy.QtWidgets import QApplication

    original = QApplication.beep
    terminal.set_conf("terminal_bell", False)
    assert QApplication.beep == original
    assert type(QApplication.beep) is type(original)
