"""Configure and open Spyder 5.x in an isolated, verbose way."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from setup_spyder._console import (
    WINDOWS,
    _prefix,
    console,
    enable_utf8_output,
    log,
    log_error,
    log_kv,
    log_ok,
    log_warn,
)
from setup_spyder.launcher import (
    AGENTS,
    PROFILES,
    ensure_spyproject,
    force_writable,
    launch as _launch,
    remove_tree,
    resolve_workdir,
)
from setup_spyder.perfil import (
    FONT_FAMILY,
    HIDDEN_PATHS,
    font_dirs,
    jetbrains_mono_installed,
    resolve_editor_font,
    resolve_hidden_paths,
    split_names,
)

REPO_URL = "https://github.com/bernardogoltz/setup-spyder"
AUTHOR = "@bernardogoltz"

__all__ = [
    "AUTHOR",
    "FONT_FAMILY",
    "HIDDEN_PATHS",
    "REPO_URL",
    "WINDOWS",
    "console",
    "enable_utf8_output",
    "ensure_spyproject",
    "font_dirs",
    "force_writable",
    "jetbrains_mono_installed",
    "launch",
    "log",
    "log_error",
    "log_kv",
    "log_ok",
    "log_warn",
    "main",
    "parse_args",
    "remove_tree",
    "resolve_editor_font",
    "resolve_hidden_paths",
    "split_names",
]


def print_banner(version: str, workdir: Path) -> None:
    body = Text()
    body.append("setup-spyder", style="bold white")
    body.append(f"  v{version}", style="dim")
    body.append("  ·  ", style="dim")
    body.append(f"{AUTHOR}\n", style="bold bright_magenta")
    body.append("isolated Spyder 5.x", style="cyan")
    body.append("  ·  ", style="dim")
    body.append(FONT_FAMILY, style="magenta")
    body.append("  ·  ", style="dim")
    body.append("AI Terminal\n\n", style="green")
    body.append("Hello — opening the project ", style="white")
    body.append(workdir.name, style="bold bright_cyan")
    body.append("\n")
    body.append(str(workdir), style="dim")
    console.print()
    console.print(
        Panel(
            body,
            title="[bold cyan]◆ setup-spyder[/]",
            subtitle="[dim]isolated profile · leaves ~/.spyder-py3 untouched[/]",
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()


def print_env(workdir: Path) -> None:
    table = Table(
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 2),
        expand=False,
    )
    table.add_column(style="dim cyan")
    table.add_column(style="bold white")
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Executable", sys.executable)
    table.add_row("Environment", sys.prefix)
    table.add_row("Workdir", str(workdir))
    console.print(table)


def launch(
    spyder_args: Sequence[str] = (),
    *,
    no_launch: bool = False,
    keep_config: bool = False,
    ephemeral: bool = False,
    sem_estilo: bool = False,
    workdir: str | Path | None = None,
    conf_dir: str | Path | None = None,
    hide: Sequence[str] = (),
    show: Sequence[str] = (),
    agent: str | None = None,
    profile: str | None = None,
    reset_profile: bool = False,
) -> int:
    """Configure Spyder 5.x, create `.spyproject` in the repository and open the IDE.

    From another repository::

        from setup_spyder import launch
        launch()
        launch(agent="codex", profile="ephemeral")

    Prints the banner and environment, then delegates to
    ``setup_spyder.launcher.launch``, which starts Spyder in a child process.
    """
    from setup_spyder import __version__

    target = resolve_workdir(workdir)
    print_banner(__version__, target)
    print_env(target)

    code = _launch(
        spyder_args,
        no_launch=no_launch,
        keep_config=keep_config,
        ephemeral=ephemeral,
        sem_estilo=sem_estilo,
        workdir=target,
        conf_dir=conf_dir,
        hide=hide,
        show=show,
        agent=agent,
        profile=profile,
        reset_profile=reset_profile,
    )
    if code == 0:
        log_ok("Setup finished without opening Spyder." if no_launch else "Spyder closed.")
    else:
        log_warn(f"setup-spyder finished with code {code}")
    return code


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="setup-spyder",
        description=(
            "Open the bernardogoltz/spyder fork (Spyder 5.x) from this "
            f"environment with an isolated profile, {FONT_FAMILY} + wrap lines "
            "and the AI Terminal pane. Every step is printed to the terminal."
        ),
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Only configure; do not open the Spyder window.",
    )
    parser.add_argument(
        "--keep-config",
        action="store_true",
        help="With an ephemeral profile, do not delete the config directory on exit.",
    )
    parser.add_argument(
        "--ephemeral",
        action="store_true",
        help="Same as --profile ephemeral: a throwaway temp profile.",
    )
    parser.add_argument(
        "--sem-estilo",
        action="store_true",
        help="Do not seed theme/font; only the keys that silence popups.",
    )
    parser.add_argument(
        "-w",
        "--workdir",
        default=None,
        help="Spyder working directory and project root (default: current directory).",
    )
    parser.add_argument(
        "--conf-dir",
        default=None,
        help="Explicit Spyder config directory; wins over --profile/--ephemeral.",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        default=None,
        help=(
            "Where the profile lives: 'project' (<root>/.spyproject/setup-spyder, "
            "the default) or 'ephemeral' (temp directory)."
        ),
    )
    parser.add_argument(
        "--reset-profile",
        action="store_true",
        help="Wipe and recreate the resolved profile before starting.",
    )
    parser.add_argument(
        "--agent",
        choices=AGENTS,
        default=None,
        help=(
            "CLI to start in the AI Terminal pane for this run "
            "(default: the saved preference, or auto)."
        ),
    )
    parser.add_argument(
        "--hide",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help=(
            "Extra file/folder names to hide from the Project pane, on top of "
            f"the {len(HIDDEN_PATHS)} hidden by default. Repeatable."
        ),
    )
    parser.add_argument(
        "--show",
        action="append",
        default=[],
        metavar="NAME[,NAME...]",
        help="Names to keep visible, undoing a default (e.g. --show .github).",
    )
    parser.add_argument(
        "spyder_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments forwarded to Spyder (after --).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return launch(
        args.spyder_args,
        no_launch=args.no_launch,
        keep_config=args.keep_config,
        ephemeral=args.ephemeral,
        sem_estilo=args.sem_estilo,
        workdir=args.workdir,
        conf_dir=args.conf_dir,
        hide=args.hide,
        show=args.show,
        agent=args.agent,
        profile=args.profile,
        reset_profile=args.reset_profile,
    )


if __name__ == "__main__":
    raise SystemExit(main())
