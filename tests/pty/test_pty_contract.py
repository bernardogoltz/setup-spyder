"""Contrato do terminal real: ANSI, Unicode, entrada, resize, Ctrl+C, saida.

Secao 10, "PTY por plataforma". O mesmo roteiro roda no ConPTY do Windows e no
PTY POSIX; o que muda e so o backend por tras de `create_pty_worker()`.

Criterio de aceitacao coberto aqui: "O painel e um terminal TTY real, com
ANSI, resize e Ctrl+C" e "Nenhum processo do agente fica orfao apos o
encerramento".
"""

from __future__ import annotations

import re

import pytest

from helpers.procutil import listening_ports, pid_alive, wait_gone

pytestmark = [pytest.mark.pty, pytest.mark.phase1, pytest.mark.slow]


# TTY, ANSI e Unicode ----------------------------------------------------


def test_o_processo_filho_enxerga_um_tty(session):
    """Se nao fosse um TTY de verdade, a TUI nem chegaria a `<READY>`."""
    assert "<READY>" in session.text


def test_as_sequencias_ansi_chegam_cruas(session):
    assert "\x1b[1;32m" in session.text, "o SGR foi filtrado no caminho"
    assert "\x1b[0m" in session.text


def test_o_unicode_sobrevive_ao_transporte(session):
    assert "ção maçã ✓" in session.text
    assert "██" in session.text


# Entrada ----------------------------------------------------------------


def test_a_entrada_e_entregue_caractere_a_caractere(session):
    """Sem Enter: se houvesse buffer de linha, o eco nunca apareceria."""
    session.worker.write(b"s")
    session.wait_for("<ECHO 0x73")


def test_bytes_e_texto_sao_aceitos_na_escrita(session):
    session.worker.write(b"a")
    session.wait_for("<ECHO 0x61")
    session.worker.write("b")
    session.wait_for("<ECHO 0x62")


# Tamanho ----------------------------------------------------------------


def test_o_tamanho_inicial_chega_ao_filho(session):
    session.worker.write(b"s")
    texto = session.wait_for("<SIZE")
    linhas, colunas = re.search(r"<SIZE (\d+) (\d+)>", texto).groups()
    assert (int(linhas), int(colunas)) == (24, 80)


def test_resize_e_visto_pelo_filho(session):
    session.worker.resize(40, 100)
    texto = session.wait_for("<RESIZE")
    linhas, colunas = re.search(r"<RESIZE (\d+) (\d+)>", texto).groups()
    assert (int(linhas), int(colunas)) == (40, 100)


def test_resize_depois_do_encerramento_nao_estoura(session):
    session.worker.write(b"q")
    session.wait_exit()
    session.worker.resize(30, 90)  # nao pode levantar excecao


# Ctrl+C -----------------------------------------------------------------


def test_interrupt_entrega_sigint_de_verdade(session):
    session.worker.interrupt()
    session.wait_for("<INTERRUPT>")
    assert session.wait_exit() == 130


def test_ctrl_c_digitado_tem_o_mesmo_efeito(session):
    session.worker.write(b"\x03")
    session.wait_for("<INTERRUPT>")
    assert session.wait_exit() == 130


# Codigo de saida --------------------------------------------------------


def test_o_codigo_de_saida_do_filho_chega_intacto(session):
    session.worker.write(b"q")
    assert session.wait_exit() == 42
    assert session.errors == [], f"saida normal nao e erro: {session.errors}"


def test_is_alive_acompanha_o_processo(session):
    assert session.worker.is_alive() is True
    session.worker.write(b"q")
    session.wait_exit()
    assert session.worker.is_alive() is False


# Encerramento da arvore -------------------------------------------------


def test_terminate_leva_junto_os_netos(session):
    """Nenhum processo do agente pode sobreviver ao painel."""
    session.worker.write(b"c")
    session.wait_for("<CHILD")
    session.qtbot.waitUntil(session.pid_file.exists, timeout=10000)
    neto = int(session.pid_file.read_text(encoding="utf-8").strip())
    assert pid_alive(neto)

    session.worker.terminate(grace_period=2.0)
    session.wait_exit()
    assert wait_gone(neto, timeout=15.0), (
        f"o neto {neto} sobreviveu ao terminate() - processo orfao"
    )


def test_terminate_e_idempotente(session):
    session.worker.terminate(grace_period=1.0)
    session.wait_exit()
    session.worker.terminate(grace_period=1.0)  # nao pode levantar excecao


def test_write_depois_do_fim_nao_derruba_o_painel(session):
    session.worker.write(b"q")
    session.wait_exit()
    with pytest.raises((RuntimeError, OSError, BrokenPipeError)):
        session.worker.write(b"x")


# Sem servidor local -----------------------------------------------------


def test_o_transporte_nao_abre_porta_tcp(session):
    """Criterio de aceitacao: "Nenhum servidor local e necessario para o
    transporte do terminal"."""
    portas = listening_ports()
    if portas is None or session.baseline_ports is None:
        pytest.skip("instale psutil para checar portas em escuta")
    novas = portas - session.baseline_ports
    assert novas == set(), f"o transporte passou a escutar em {sorted(novas)}"
