"""TUI deterministica para provar o contrato do PTY.

O plano (secao 10, "PTY por plataforma") pede um programa pequeno e previsivel
para verificar ANSI, Unicode, entrada caractere a caractere, resize, ``Ctrl+C``,
codigo de saida e encerramento da arvore de processos - sem rede, conta ou
credencial. Este e esse programa.

Protocolo de saida (uma linha por evento, sempre com ``\\n``)::

    <BANNER>            escrito com SGR + acentos + emoji, prova ANSI/Unicode
    <READY>             o programa entrou no laco de leitura
    <ECHO 0x61 a>       recebeu *um* byte; prova que nao ha buffer de linha
    <SIZE rows cols>    resposta ao comando "s"
    <RESIZE rows cols>  o terminal mudou de tamanho (detectado por polling,
                        o que funciona tanto com SIGWINCH quanto com ConPTY)
    <CHILD pid>         resposta ao comando "c": criou um neto que dorme
    <INTERRUPT>         recebeu SIGINT / CTRL_C_EVENT

Comandos de entrada (um caractere cada):

    ``s`` tamanho    ``c`` cria neto    ``q`` sai com 42    ``Ctrl+C`` sai com 130
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time

BANNER = "\x1b[1;32mfake-tui\x1b[0m ção maçã ✓ ██"
EXIT_QUIT = 42
EXIT_INTERRUPT = 130

CHILD_SOURCE = (
    "import sys, time\n"
    "open(sys.argv[1], 'w').write(str(__import__('os').getpid()))\n"
    "time.sleep(600)\n"
)


def force_utf8() -> None:
    """O console do Windows e cp1252 por padrao e engasgaria no banner."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):  # pragma: no cover
                pass


def emit(line: str) -> None:
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def current_size() -> tuple[int, int]:
    size = shutil.get_terminal_size(fallback=(0, 0))
    return size.lines, size.columns


def watch_size(stop: threading.Event) -> None:
    """Emite ``<RESIZE r c>`` quando o terminal muda de tamanho.

    Polling em vez de SIGWINCH: o ConPTY do Windows nao entrega SIGWINCH, e o
    contrato que interessa ao painel e "o programa enxerga o novo tamanho".
    """
    last = current_size()
    while not stop.wait(0.05):
        size = current_size()
        if size != last and size != (0, 0):
            last = size
            emit(f"<RESIZE {size[0]} {size[1]}>")


def spawn_grandchild(pid_file: str) -> int:
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = False  # fica no mesmo process group
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD_SOURCE, pid_file],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )
    return child.pid


def read_one_byte():
    """Le exatamente um byte, sem esperar por Enter.

    No Windows so o console (ConPTY) responde a `msvcrt`; num pipe comum ele
    nunca acorda. O fallback existe para que o proprio programa possa ser
    testado fora de um PTY - sob PTY, o caminho exercitado e o primeiro.
    """
    if os.name == "nt" and sys.stdin.isatty():
        import msvcrt

        while not msvcrt.kbhit():
            time.sleep(0.01)
        return msvcrt.getch()
    return sys.stdin.buffer.read(1)


def enter_cbreak():
    if os.name == "nt":
        return None
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    # cbreak, nao raw: ISIG segue ligado, entao \x03 vira SIGINT de verdade.
    tty.setcbreak(fd)
    return (fd, saved)


def restore(state) -> None:
    if state is None:
        return
    import termios

    fd, saved = state
    termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def on_interrupt(signum, frame):  # noqa: ARG001
    emit("<INTERRUPT>")
    raise SystemExit(EXIT_INTERRUPT)


def main() -> int:
    force_utf8()
    signal.signal(signal.SIGINT, on_interrupt)
    pid_file = sys.argv[1] if len(sys.argv) > 1 else ""

    emit(BANNER)
    state = enter_cbreak()
    stop = threading.Event()
    watcher = threading.Thread(target=watch_size, args=(stop,), daemon=True)
    watcher.start()
    emit("<READY>")

    try:
        while True:
            data = read_one_byte()
            if not data:
                return 0
            char = data.decode("utf-8", "replace")
            if char == "\x03":  # ConPTY pode entregar o byte cru
                on_interrupt(signal.SIGINT, None)
            emit(f"<ECHO 0x{data[0]:02x} {char!r}>")
            if char == "s":
                rows, cols = current_size()
                emit(f"<SIZE {rows} {cols}>")
            elif char == "c" and pid_file:
                emit(f"<CHILD {spawn_grandchild(pid_file)}>")
            elif char == "q":
                return EXIT_QUIT
    except KeyboardInterrupt:
        emit("<INTERRUPT>")
        return EXIT_INTERRUPT
    finally:
        stop.set()
        restore(state)


if __name__ == "__main__":
    raise SystemExit(main())
