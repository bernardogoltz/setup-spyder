"""Consultas de processo usadas pelos testes de encerramento e de rede.

`os.kill(pid, 0)` **nao** serve como "esta vivo?" no Windows: a implementacao
do CPython chama `TerminateProcess` para qualquer sinal que nao seja
CTRL_C_EVENT/CTRL_BREAK_EVENT, ou seja, mataria o processo consultado. Por
isso a checagem passa por `psutil`, quando disponivel, ou por `OpenProcess`.
"""

from __future__ import annotations

import os
import time

try:  # opcional: deixa as checagens mais precisas
    import psutil
except ImportError:  # pragma: no cover - ambiente sem psutil
    psutil = None

_STILL_ACTIVE = 259


def pid_alive(pid: int) -> bool:
    if psutil is not None:
        try:
            processo = psutil.Process(pid)
            # `status()` raises too when the process dies between the two
            # calls (Windows tears a tree down asynchronously).
            return processo.is_running() and processo.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == _STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_gone(pid: int, timeout: float = 10.0, interval: float = 0.05) -> bool:
    """Espera o processo sumir. Devolve False se ele sobreviveu ao timeout."""
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if not pid_alive(pid):
            return True
        time.sleep(interval)
    return not pid_alive(pid)


def listening_ports(pid: int | None = None) -> set[int] | None:
    """Portas TCP em LISTEN do processo (e dos filhos). None sem `psutil`."""
    if psutil is None:
        return None
    pid = pid or os.getpid()
    try:
        raiz = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return set()
    portas: set[int] = set()
    for processo in [raiz, *raiz.children(recursive=True)]:
        try:
            conexoes = processo.net_connections(kind="tcp")
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        for conexao in conexoes:
            if conexao.status == psutil.CONN_LISTEN and conexao.laddr:
                portas.add(conexao.laddr.port)
    return portas
