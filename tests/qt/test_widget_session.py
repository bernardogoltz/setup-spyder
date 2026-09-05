"""Ciclo de vida da sessao no painel, com backend falso (secao 10, "Qt/plugin").

Contrato exercitado::

    setup_spyder.plugin.main_widget
        create_pty_worker(...) -> objeto com o contrato da secao 6.2
        AITerminalWidget
            sig_state_changed(str)   estados: starting|running|exited|error
            state -> str
            set_working_directory(path)
            start_session(provider=None)
            send_input(text)
            resize_terminal(rows, cols)
            interrupt() / restart() / clear() / close_session()
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.qt, pytest.mark.phase3]


def test_o_painel_comeca_sem_sessao(terminal):
    assert terminal.state in {"idle", "exited"}


def test_start_session_passa_por_starting_e_running(qtbot, terminal, patched_backend):
    estados = []
    terminal.sig_state_changed.connect(estados.append)
    with qtbot.waitSignal(terminal.sig_state_changed, timeout=2000):
        terminal.start_session()
    qtbot.waitUntil(lambda: terminal.state == "running", timeout=2000)
    assert estados[0] == "starting"
    assert patched_backend.started_with is not None


def test_a_sessao_nasce_na_raiz_do_projeto(terminal, patched_backend, project_root):
    """Definicao de pronto: "usar a raiz do projeto como diretorio de trabalho"."""
    terminal.start_session()
    _, cwd, _ = patched_backend.started_with
    assert str(cwd) == str(project_root)


def test_o_argv_chega_como_lista(terminal, patched_backend):
    terminal.start_session()
    argv, _, _ = patched_backend.started_with
    assert isinstance(argv, list) and argv
    assert all(isinstance(part, str) for part in argv)


def test_entrada_do_usuario_chega_ao_transporte(terminal, patched_backend):
    terminal.start_session()
    terminal.send_input("olá ✓\r")
    assert b"".join(patched_backend.written).decode("utf-8") == "olá ✓\r"


def test_resize_e_repassado_ao_transporte(terminal, patched_backend):
    terminal.start_session()
    terminal.resize_terminal(24, 80)
    terminal.resize_terminal(40, 120)
    assert patched_backend.sizes[-2:] == [(24, 80), (40, 120)]


def test_interrupt_manda_ctrl_c_e_nao_mata_o_painel(terminal, patched_backend):
    terminal.start_session()
    terminal.interrupt()
    assert patched_backend.interrupts == 1
    assert terminal.state == "running"


def test_saida_do_processo_leva_ao_estado_exited(qtbot, terminal, patched_backend):
    terminal.start_session()
    with qtbot.waitSignal(terminal.sig_state_changed, timeout=2000):
        patched_backend.finish(0)
    assert terminal.state == "exited"


def test_erro_do_transporte_leva_ao_estado_error(qtbot, terminal, patched_backend):
    terminal.start_session()
    with qtbot.waitSignal(terminal.sig_state_changed, timeout=2000):
        patched_backend.fail("ConPTY indisponivel")
    assert terminal.state == "error"


def test_close_session_encerra_com_periodo_de_graca(terminal, patched_backend):
    terminal.start_session()
    terminal.close_session()
    assert patched_backend.terminated is not None
    assert patched_backend.terminated > 0, (
        "secao 6.2: encerramento escalonado, nao kill imediato"
    )


def test_restart_encerra_a_sessao_anterior_antes_de_abrir_outra(
    qtbot, terminal, widget_module, worker_factory, monkeypatch
):
    monkeypatch.setattr(widget_module, "create_pty_worker", worker_factory)
    criados = worker_factory.criados
    terminal.start_session()
    terminal.restart()
    qtbot.waitUntil(lambda: len(criados) == 2, timeout=2000)
    assert criados[0].terminated is not None, "a sessao antiga ficou viva"
    assert criados[1].started_with is not None


def test_clear_limpa_a_tela_sem_encerrar_o_processo(terminal, patched_backend):
    terminal.start_session()
    terminal.clear()
    assert patched_backend.alive is True
    assert terminal.state == "running"


def test_fechar_o_widget_encerra_o_processo_filho(qtbot, terminal, patched_backend):
    """Definicao de pronto: "encerrar o processo-filho quando o painel ou o
    Spyder forem fechados"."""
    terminal.start_session()
    terminal.close()
    qtbot.waitUntil(lambda: patched_backend.alive is False, timeout=2000)
