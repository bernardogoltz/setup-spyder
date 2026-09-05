"""Pseudo-terminal transport for the AI Terminal: ConPTY on Windows, PTY elsewhere.

Contract (plan section 6.2)::

    worker = create_pty_worker()
    worker.start(argv, cwd=None, env=None, rows=24, cols=80)
    worker.write(data)            # bytes or str
    worker.resize(rows, cols)
    worker.interrupt()            # Ctrl+C, the session keeps running
    worker.is_alive()
    worker.terminate(grace_period=2.0)
    worker.sig_output(bytes) / sig_exited(int) / sig_error(str)

Backends are imported lazily inside :func:`create_pty_worker`, so importing
this module never imports ``winpty`` or ``ptyprocess``; a missing dependency
surfaces as an ``ImportError`` at session start, inside the panel, instead of
making the plugin disappear during discovery (plan section 6.1).

The child is always started from an argv list: no shell, no concatenation. The
whole process tree is terminated with the session (Windows Job Object, POSIX
process group), so nothing outlives the panel.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence

from qtpy.QtCore import QObject, QThread, QTimer, Signal

logger = logging.getLogger("setup_spyder.plugin.pty")

#: Additions to the inherited environment; the only ones the terminal needs.
TERMINAL_ENV = {"TERM": "xterm-256color", "COLORTERM": "truecolor"}

#: How often the worker checks that the child is still alive (milliseconds).
WATCHDOG_INTERVAL_MS = 200

#: How long ``terminate()`` waits for the tree to die after the forced kill.
KILL_TIMEOUT = 3.0


class _ReaderThread(QThread):
    """Runs the blocking read loop of a worker outside the GUI thread."""

    def __init__(self, loop, parent=None):
        super().__init__(parent)
        self._loop = loop

    def run(self):
        try:
            self._loop()
        except Exception:  # pragma: no cover - defensive; reported by the worker
            logger.exception("PTY reader thread crashed")


class PTYWorker(QObject):
    """Platform-independent life cycle; subclasses implement the transport."""

    sig_output = Signal(bytes)
    sig_exited = Signal(int)
    sig_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._started = False
        self._exited = False
        self._stop_reading = False
        self._lock = threading.Lock()
        self._reader: _ReaderThread | None = None
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(WATCHDOG_INTERVAL_MS)
        self._watchdog.timeout.connect(self._poll)
        self.argv: list[str] = []
        self.pid: int | None = None

    # Public contract ---------------------------------------------------------

    def start(
        self,
        argv: Sequence[str],
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        rows: int = 24,
        cols: int = 80,
    ) -> None:
        """Spawn ``argv`` in a fresh pseudo-terminal of ``rows`` x ``cols``."""
        if self._started:
            raise RuntimeError("PTYWorker.start() can only be called once per worker")
        command = [str(part) for part in argv]
        if not command:
            raise ValueError("argv must not be empty")
        directory = os.fspath(cwd) if cwd else os.getcwd()
        environment = dict(os.environ)
        environment.update(TERMINAL_ENV)
        if env:
            environment.update({str(key): str(value) for key, value in env.items()})

        self._started = True
        self.argv = command
        try:
            self._spawn(command, directory, environment, max(int(rows), 1), max(int(cols), 1))
        except Exception:
            self._exited = True
            raise
        self._reader = _ReaderThread(self._read_loop, self)
        self._reader.finished.connect(self._on_reader_finished)
        self._reader.start()
        self._watchdog.start()
        logger.debug("PTY session started: pid=%s argv=%s cwd=%s", self.pid, command, directory)

    def write(self, data: bytes | str) -> None:
        """Send keystrokes to the child; raises once the session has ended."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not self.is_alive():
            raise RuntimeError("the terminal session has ended; nothing to write to")
        self._write_bytes(bytes(data))

    def resize(self, rows: int, cols: int) -> None:
        """Change the terminal size; silently ignored once the child is gone."""
        if not self.is_alive():
            return
        try:
            self._set_size(max(int(rows), 1), max(int(cols), 1))
        except Exception as exc:
            logger.debug("resize ignored: %s", exc)

    def interrupt(self) -> None:
        """Deliver Ctrl+C to the child; the session keeps running."""
        if self.is_alive():
            self._send_interrupt()

    def is_alive(self) -> bool:
        return self._started and not self._exited and self._backend_alive()

    def terminate(self, grace_period: float = 2.0) -> None:
        """Politely stop the child, then kill the whole tree. Idempotent."""
        if not self._started or self._exited:
            return
        if self._backend_alive():
            try:
                self._send_interrupt()
            except Exception as exc:
                logger.debug("polite interrupt failed: %s", exc)
            self._wait_dead(max(float(grace_period), 0.0))
        if self._backend_alive():
            self._kill_tree()
            self._wait_dead(KILL_TIMEOUT)
        self._finish()

    # Internal life cycle -----------------------------------------------------

    def _wait_dead(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while self._backend_alive() and time.monotonic() < deadline:
            time.sleep(0.02)

    def _poll(self) -> None:
        if self._started and not self._exited and not self._backend_alive():
            self._finish()

    def _on_reader_finished(self) -> None:
        if self._started and not self._exited and not self._backend_alive():
            self._finish()

    def _finish(self) -> None:
        """Move to the exited state exactly once and reap the tree."""
        with self._lock:
            if self._exited or not self._started:
                return
            self._exited = True
        self._watchdog.stop()
        self._stop_reading = True
        code = self._exit_status()
        self._kill_tree()
        self._close_backend()
        if self._reader is not None and self._reader.isRunning():
            self._reader.wait(2000)
        logger.debug("PTY session ended: pid=%s code=%s", self.pid, code)
        self.sig_exited.emit(int(code))

    def _report_error(self, message: str) -> None:
        logger.error("PTY transport error: %s", message)
        self.sig_error.emit(message)

    # Backend hooks -----------------------------------------------------------

    def _spawn(self, argv, cwd, env, rows, cols) -> None:  # pragma: no cover
        raise NotImplementedError

    def _read_loop(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def _write_bytes(self, data: bytes) -> None:  # pragma: no cover
        raise NotImplementedError

    def _set_size(self, rows: int, cols: int) -> None:  # pragma: no cover
        raise NotImplementedError

    def _send_interrupt(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def _backend_alive(self) -> bool:  # pragma: no cover
        raise NotImplementedError

    def _exit_status(self) -> int:  # pragma: no cover
        raise NotImplementedError

    def _kill_tree(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def _close_backend(self) -> None:  # pragma: no cover
        raise NotImplementedError


# Windows: ConPTY through pywinpty + a Job Object for the tree ----------------


class WindowsPTYWorker(PTYWorker):
    """ConPTY backend on top of ``winpty.PTY`` (the low-level class).

    ``winpty.PtyProcess`` is not used on purpose: it relays output through a
    loopback TCP socket, and the plan forbids any listener for the transport.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pty = None
        self._job = None

    def _spawn(self, argv, cwd, env, rows, cols):
        import winpty

        kernel32 = _kernel32()
        # A process created with "ignore Ctrl+C" passes that state on to its
        # children. Re-enable it here so the child receives CTRL_C_EVENT when
        # the terminal sends \x03 (otherwise Ctrl+C would never reach it).
        kernel32.SetConsoleCtrlHandler(None, False)

        program = argv[0]
        if not os.path.isfile(program):
            program = shutil.which(program, path=env.get("PATH")) or program
        cmdline = " " + subprocess.list2cmdline(argv[1:]) if len(argv) > 1 else None
        env_block = "\0".join(f"{key}={value}" for key, value in env.items()) + "\0"

        pty = winpty.PTY(cols, rows)
        if not pty.spawn(program, cmdline=cmdline, cwd=cwd, env=env_block):
            raise RuntimeError(f"ConPTY could not start {program!r}")
        self._pty = pty
        self.pid = pty.pid
        self._job = _assign_job(self.pid)

    def _read_loop(self):
        pty = self._pty
        while not self._stop_reading and pty is not None:
            try:
                data = pty.read(blocking=True)
            except Exception as exc:
                if self._backend_alive() and not self._stop_reading:
                    logger.debug("ConPTY read ended while alive: %s", exc)
                break
            if data:
                self.sig_output.emit(data.encode("utf-8", "replace"))
                continue
            if not self._backend_alive():
                break
            time.sleep(0.01)

    def _write_bytes(self, data):
        self._pty.write(data.decode("utf-8", "replace"))

    def _set_size(self, rows, cols):
        self._pty.set_size(cols, rows)

    def _send_interrupt(self):
        self._pty.write("\x03")

    def _backend_alive(self):
        pty = self._pty
        if pty is None:
            return False
        try:
            return bool(pty.isalive())
        except Exception:
            return False

    def _exit_status(self):
        try:
            code = self._pty.get_exitstatus()
        except Exception:
            code = None
        return int(code) if code is not None else 0

    def _kill_tree(self):
        job, self._job = self._job, None
        if job is not None:
            kernel32 = _kernel32()
            pids = _job_pids(job)
            kernel32.TerminateJobObject(job, 1)
            # TerminateJobObject is asynchronous: wait until the job reports
            # no active process and the process objects are gone, so callers
            # can rely on the tree having disappeared when this returns.
            _wait_job_empty(job, KILL_TIMEOUT)
            _wait_pids_deleted(pids, KILL_TIMEOUT)
            kernel32.CloseHandle(job)
        elif self.pid and self._backend_alive():
            _terminate_pid(self.pid)

    def _close_backend(self):
        pty = self._pty
        if pty is None:
            return
        try:
            pty.cancel_io()
        except Exception:
            pass


def _kernel32():
    import ctypes

    return ctypes.windll.kernel32


def _assign_job(pid: int):
    """Job Object with KILL_ON_JOB_CLOSE; shared with the launcher."""
    from setup_spyder._children import assign_job

    return assign_job(pid)


def _wait_job_empty(job, timeout: float) -> bool:
    """Poll the job's accounting until every process in it has terminated."""
    import ctypes
    from ctypes import wintypes

    JobObjectBasicAccountingInformation = 1

    class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    kernel32 = _kernel32()
    info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
    deadline = time.monotonic() + timeout
    while True:
        ok = kernel32.QueryInformationJobObject(
            job,
            JobObjectBasicAccountingInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
            None,
        )
        if not ok or info.ActiveProcesses == 0:
            return bool(ok)
        if time.monotonic() >= deadline:
            logger.warning("%s process(es) of the job still active", info.ActiveProcesses)
            return False
        time.sleep(0.02)


def _job_pids(job) -> list[int]:
    """Pids currently assigned to the job (best effort, bounded list)."""
    import ctypes
    from ctypes import wintypes

    JobObjectBasicProcessIdList = 3
    capacity = 512

    class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
        _fields_ = [
            ("NumberOfAssignedProcesses", wintypes.DWORD),
            ("NumberOfProcessIdsInList", wintypes.DWORD),
            ("ProcessIdList", ctypes.c_size_t * capacity),
        ]

    info = JOBOBJECT_BASIC_PROCESS_ID_LIST()
    info.NumberOfAssignedProcesses = capacity
    _kernel32().QueryInformationJobObject(
        job, JobObjectBasicProcessIdList, ctypes.byref(info), ctypes.sizeof(info), None
    )
    count = min(int(info.NumberOfProcessIdsInList), capacity)
    return [int(info.ProcessIdList[index]) for index in range(count)]


def _wait_pids_deleted(pids: list[int], timeout: float) -> None:
    """Wait until the process objects behind ``pids`` no longer exist."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    import ctypes
    from ctypes import wintypes

    kernel32 = _kernel32()
    pending = set(pids)
    deadline = time.monotonic() + timeout
    while pending and time.monotonic() < deadline:
        for pid in list(pending):
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                pending.discard(pid)
                continue
            code = wintypes.DWORD()
            try:
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    if code.value == STILL_ACTIVE:
                        continue
            finally:
                kernel32.CloseHandle(handle)
        if pending:
            time.sleep(0.005)


def _terminate_pid(pid: int) -> None:
    PROCESS_TERMINATE = 0x0001
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, int(pid))
    if not handle:
        return
    try:
        kernel32.TerminateProcess(handle, 1)
    finally:
        kernel32.CloseHandle(handle)


# POSIX: ptyprocess + process group --------------------------------------------


class PosixPTYWorker(PTYWorker):
    """PTY backend on top of ``ptyprocess.PtyProcess`` (bytes interface).

    ``PtyProcess.spawn`` calls ``setsid`` in the child, so the child's pid is
    also its process group: ``os.killpg`` reaches the whole tree.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None

    def _spawn(self, argv, cwd, env, rows, cols):
        import ptyprocess

        self._proc = ptyprocess.PtyProcess.spawn(
            list(argv), cwd=cwd, env=env, dimensions=(rows, cols)
        )
        self.pid = self._proc.pid

    def _read_loop(self):
        proc = self._proc
        while not self._stop_reading and proc is not None:
            try:
                data = proc.read(4096)
            except EOFError:
                break
            except OSError as exc:
                if self._backend_alive() and not self._stop_reading:
                    logger.debug("PTY read ended while alive: %s", exc)
                break
            if data:
                self.sig_output.emit(bytes(data))
            elif not self._backend_alive():
                break

    def _write_bytes(self, data):
        self._proc.write(data)

    def _set_size(self, rows, cols):
        self._proc.setwinsize(rows, cols)

    def _send_interrupt(self):
        self._proc.sendintr()

    def _backend_alive(self):
        proc = self._proc
        if proc is None:
            return False
        try:
            return bool(proc.isalive())
        except Exception:
            return False

    def _exit_status(self):
        proc = self._proc
        if proc is None:
            return 0
        try:
            proc.isalive()
        except Exception:
            pass
        if proc.exitstatus is not None:
            return int(proc.exitstatus)
        if proc.signalstatus is not None:
            return 128 + int(proc.signalstatus)
        return 0

    def _kill_tree(self):
        if not self.pid:
            return
        for sig, pause in ((signal.SIGTERM, 0.5), (signal.SIGKILL, 0.0)):
            try:
                os.killpg(self.pid, sig)
            except ProcessLookupError:
                return
            except OSError as exc:
                logger.debug("killpg(%s, %s) failed: %s", self.pid, sig, exc)
            deadline = time.monotonic() + pause
            while self._backend_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            if not self._backend_alive():
                return

    def _close_backend(self):
        proc = self._proc
        if proc is None:
            return
        try:
            proc.close(force=True)
        except Exception as exc:
            logger.debug("PTY close: %s", exc)


# Factory -----------------------------------------------------------------------


def create_pty_worker(parent=None, **_unused) -> PTYWorker:
    """Return the worker for this OS, importing its backend only now.

    An ``ImportError`` here names the missing package (``winpty`` on Windows,
    ``ptyprocess`` elsewhere) so the panel can show the install hint.
    """
    if sys.platform == "win32":
        import winpty  # noqa: F401  (fail early, with the real message)

        return WindowsPTYWorker(parent)
    import ptyprocess  # noqa: F401

    return PosixPTYWorker(parent)
