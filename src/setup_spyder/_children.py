"""Keep a child process tree tied to the process that started it.

Used by the launcher (the Spyder child must not outlive ``setup-spyder``) and
by the AI Terminal's PTY worker (the CLI must not outlive the pane). No Qt and
no Spyder imports here: the launcher's parent process stays lightweight.

Windows: the child is placed in a Job Object created with
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``. Every descendant inherits the job, and
the whole tree is terminated when the job handle is closed or when this
process dies, whichever comes first.

POSIX: the child starts its own session (``start_new_session=True``) and the
launcher forwards ``SIGTERM``/``SIGINT``/``SIGHUP`` to the process group.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence

WINDOWS = sys.platform == "win32"

logger = logging.getLogger("setup_spyder.children")


# Windows Job Objects --------------------------------------------------------


def kernel32():
    import ctypes

    return ctypes.windll.kernel32


def assign_job(pid: int):
    """Put ``pid`` in a Job Object that kills every descendant when closed.

    Returns the job handle (keep it alive for as long as the tree should
    live) or ``None`` when the job could not be created or assigned; callers
    degrade to a plain terminate in that case.
    """
    import ctypes
    from ctypes import wintypes

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformation = 9
    PROCESS_SET_QUOTA = 0x0100
    PROCESS_TERMINATE = 0x0001

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    k32 = kernel32()
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    ]
    k32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p
    ]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    job = k32.CreateJobObjectW(None, None)
    if not job:
        logger.warning("CreateJobObject failed (%s); tree kill degraded", ctypes.GetLastError())
        return None
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
    ):
        logger.warning("SetInformationJobObject failed (%s)", ctypes.GetLastError())
        k32.CloseHandle(job)
        return None
    process = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, int(pid))
    if not process:
        logger.warning("OpenProcess(%s) failed (%s)", pid, ctypes.GetLastError())
        k32.CloseHandle(job)
        return None
    try:
        if not k32.AssignProcessToJobObject(job, process):
            logger.warning(
                "AssignProcessToJobObject failed (%s); tree kill degraded",
                ctypes.GetLastError(),
            )
            k32.CloseHandle(job)
            return None
    finally:
        k32.CloseHandle(process)
    return job


def terminate_job(job) -> None:
    """Kill everything in the job and release the handle. Idempotent."""
    if not job:
        return
    k32 = kernel32()
    k32.TerminateJobObject(job, 1)
    k32.CloseHandle(job)


# Launcher-side child runner ------------------------------------------------


class ChildTree:
    """A child process whose whole tree dies with this process."""

    def __init__(self, command: Sequence[str], env: Mapping[str, str] | None = None):
        self.command = list(command)
        self.env = dict(env) if env is not None else None
        self.process: subprocess.Popen | None = None
        self._job = None
        self._previous_handlers: dict[int, object] = {}

    def start(self) -> subprocess.Popen:
        kwargs: dict = {"env": self.env}
        if not WINDOWS:
            kwargs["start_new_session"] = True
        self.process = subprocess.Popen(self.command, **kwargs)
        if WINDOWS:
            self._job = assign_job(self.process.pid)
        self._install_signal_forwarding()
        return self.process

    def wait(self) -> int:
        assert self.process is not None
        try:
            return self.process.wait()
        except KeyboardInterrupt:
            self.terminate(grace_period=5.0)
            return 130

    def terminate(self, grace_period: float = 5.0) -> None:
        """Ask the tree to stop, then kill whatever is left after the grace."""
        process = self.process
        if process is None:
            return
        if process.poll() is None:
            try:
                if WINDOWS:
                    process.terminate()
                else:
                    os.killpg(process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            deadline = time.monotonic() + max(grace_period, 0.0)
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
        if WINDOWS:
            terminate_job(self._job)
            self._job = None
        elif process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - already killed
            pass

    def close(self) -> None:
        """Release the job handle (kills leftovers) and restore the handlers."""
        if WINDOWS:
            terminate_job(self._job)
            self._job = None
        for signum, handler in self._previous_handlers.items():
            try:
                signal.signal(signum, handler)  # type: ignore[arg-type]
            except (ValueError, OSError):  # pragma: no cover - not main thread
                pass
        self._previous_handlers.clear()

    # Signal forwarding ------------------------------------------------------

    def _install_signal_forwarding(self) -> None:
        names = ("SIGTERM", "SIGINT", "SIGHUP", "SIGBREAK")
        for name in names:
            signum = getattr(signal, name, None)
            if signum is None:
                continue
            try:
                previous = signal.signal(signum, self._forward)
            except (ValueError, OSError):  # pragma: no cover - not main thread
                continue
            self._previous_handlers[signum] = previous

    def _forward(self, signum, frame):  # noqa: ARG002
        self.terminate(grace_period=5.0)
        previous = self._previous_handlers.get(signum)
        if signum == getattr(signal, "SIGINT", None):
            raise KeyboardInterrupt
        if callable(previous) and previous not in (signal.SIG_IGN, signal.SIG_DFL):
            previous(signum, frame)
        else:
            raise SystemExit(128 + int(signum))


def run_child(command: Sequence[str], env: Mapping[str, str] | None = None) -> int:
    """Run ``command`` as a child tree tied to this process; return its exit code."""
    tree = ChildTree(command, env)
    tree.start()
    try:
        return tree.wait()
    finally:
        tree.close()
