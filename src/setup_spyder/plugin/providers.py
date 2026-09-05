"""Resolve which agent CLI (codex or claude) the AI Terminal starts, and how.

The plugin knows executable profiles, not AI APIs (plan section 2.3): each
provider is the bare interactive command found on ``PATH`` with
``shutil.which``. No model, permission or approval flags are ever added; those
stay the responsibility of the CLI itself.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

AGENT_AUTO = "auto"
AGENT_NONE = "none"

REASON_EXPLICIT = "explicit"
REASON_PREFERENCE = "preference"
REASON_SINGLE = "single"
REASON_AMBIGUOUS = "ambiguous"
REASON_MISSING = "missing"
REASON_DISABLED = "disabled"

WINDOWS_SCRIPT_SUFFIXES = (".cmd", ".bat")


@dataclass(frozen=True)
class AgentProvider:
    """An interactive CLI the panel can start: a name, an executable, its argv."""

    name: str
    executable: str
    argv: tuple[str, ...] = ()


KNOWN_PROVIDERS: Mapping[str, AgentProvider] = {
    "codex": AgentProvider(name="codex", executable="codex", argv=()),
    "claude": AgentProvider(name="claude", executable="claude", argv=()),
}

#: Deterministic order used for discovery and for the panel selector.
PROVIDER_ORDER: tuple[str, ...] = ("codex", "claude")

#: Every value accepted by ``--agent`` / ``SETUP_SPYDER_AGENT``.
AGENT_CHOICES: tuple[str, ...] = (AGENT_AUTO, *PROVIDER_ORDER, AGENT_NONE)


@dataclass(frozen=True)
class AgentResolution:
    """Outcome of :func:`resolve_provider`.

    ``reason`` is one of ``explicit``, ``preference``, ``single``,
    ``ambiguous``, ``missing`` or ``disabled``. ``autostart`` is True only when
    a provider was chosen without ambiguity.
    """

    provider: AgentProvider | None
    reason: str
    candidates: tuple[AgentProvider, ...]
    requested: str | None
    autostart: bool


def normalize_request(requested: str | None) -> str | None:
    """Return ``None`` for auto, ``"none"``, or a known provider name.

    Raises ``ValueError`` for any other value: an unknown ``--agent`` is a
    programming error, not something to degrade silently.
    """
    if requested is None:
        return None
    value = str(requested).strip().lower()
    if value in ("", AGENT_AUTO):
        return None
    if value == AGENT_NONE or value in KNOWN_PROVIDERS:
        return value
    raise ValueError(
        f"unknown agent {requested!r}; expected one of {', '.join(AGENT_CHOICES)}"
    )


def find_executable(provider: AgentProvider) -> str | None:
    """Locate the provider on ``PATH`` (never a guessed install directory)."""
    return shutil.which(provider.executable)


def available_providers() -> tuple[AgentProvider, ...]:
    """Known providers whose executable is on ``PATH``, in a stable order."""
    return tuple(
        KNOWN_PROVIDERS[name]
        for name in PROVIDER_ORDER
        if find_executable(KNOWN_PROVIDERS[name]) is not None
    )


def resolve_provider(
    requested: str | None = None, preference: str | None = None
) -> AgentResolution:
    """Apply the precedence of plan section 6.3.

    1. an explicit request (``--agent``) wins over everything;
    2. otherwise the saved preference, when that CLI is installed;
    3. otherwise the single CLI found on ``PATH``;
    4. two CLIs and no preference is ambiguous: nothing starts;
    5. no CLI at all is ``missing``, never an exception.
    """
    wanted = normalize_request(requested)
    if wanted == AGENT_NONE:
        return AgentResolution(None, REASON_DISABLED, (), AGENT_NONE, False)

    candidates = available_providers()
    names = {provider.name for provider in candidates}

    if wanted is not None:
        if wanted in names:
            return AgentResolution(
                KNOWN_PROVIDERS[wanted], REASON_EXPLICIT, candidates, wanted, True
            )
        return AgentResolution(None, REASON_MISSING, candidates, wanted, False)

    saved = str(preference or "").strip().lower()
    if saved == AGENT_NONE:
        return AgentResolution(None, REASON_DISABLED, candidates, None, False)
    if saved in names:
        return AgentResolution(
            KNOWN_PROVIDERS[saved], REASON_PREFERENCE, candidates, None, True
        )

    if len(candidates) == 1:
        return AgentResolution(candidates[0], REASON_SINGLE, candidates, None, True)
    if len(candidates) > 1:
        return AgentResolution(None, REASON_AMBIGUOUS, candidates, None, False)
    return AgentResolution(None, REASON_MISSING, candidates, None, False)


def build_command(provider: AgentProvider) -> list[str]:
    """Argv list for the provider, starting with the path ``shutil.which`` found.

    On Windows, ``codex``/``claude`` are usually npm ``.cmd`` shims, which
    ``CreateProcess`` cannot start directly. The only accepted shape then is
    ``[cmd.exe, "/c", <path to the .cmd>, *argv]``: the path is a separate
    argument, never interpolated into a command line.
    """
    path = find_executable(provider)
    if path is None:
        raise FileNotFoundError(
            f"{provider.executable!r} was not found on PATH for provider {provider.name}"
        )
    command = [path, *provider.argv]
    if sys.platform == "win32" and Path(path).suffix.lower() in WINDOWS_SCRIPT_SUFFIXES:
        comspec = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
        command = [comspec, "/c", path, *provider.argv]
    return command


def default_shell() -> list[str]:
    """The user's interactive shell as a one-element argv (fallback session)."""
    if sys.platform == "win32":
        shell = os.environ.get("COMSPEC") or shutil.which("cmd.exe") or "cmd.exe"
    else:
        shell = os.environ.get("SHELL") or shutil.which("sh") or "/bin/sh"
    return [shell]
