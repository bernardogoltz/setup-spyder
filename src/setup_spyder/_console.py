"""Rich console and the log helpers shared by the launcher layers."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.text import Text

WINDOWS = sys.platform == "win32"


def enable_utf8_output() -> None:
    """Let the Windows console print the ✓/◆ glyphs instead of crashing on cp1252."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower()
        if encoding.replace("-", "") == "utf8":
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):  # pragma: no cover - depends on the console
            pass


if WINDOWS:
    enable_utf8_output()

console = Console(highlight=False)


def _prefix() -> Text:
    return Text("setup-spyder", style="bold cyan")


def log(message: str) -> None:
    console.print(Text.assemble(_prefix(), "  ", (message, "white")), soft_wrap=True)


def log_ok(message: str) -> None:
    console.print(
        Text.assemble(_prefix(), "  ", ("✓ ", "bold green"), (message, "green")),
        soft_wrap=True,
    )


def log_warn(message: str) -> None:
    console.print(
        Text.assemble(_prefix(), "  ", ("! ", "bold yellow"), (message, "yellow")),
        soft_wrap=True,
    )


def log_error(message: str) -> None:
    console.print(
        Text.assemble(_prefix(), "  ", ("✗ ", "bold red"), (message, "red")),
        soft_wrap=True,
    )


def log_kv(key: str, value: object) -> None:
    console.print(
        Text.assemble(
            _prefix(),
            "    ",
            (f"{key}: ", "dim cyan"),
            (str(value), "bold white"),
        ),
        soft_wrap=True,
    )
