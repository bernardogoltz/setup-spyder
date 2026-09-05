"""Configure and open the fork instance: isolated profile and AI Terminal."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.text import Text

from setup_spyder.cli import (
    AUTHOR,
    FONT_FAMILY,
    REPO_URL,
    console,
    log_ok,
    log_warn,
    print_env,
)
from setup_spyder.launcher import (
    AGENTS,
    PROFILES,
    launch as _launch,
    resolve_workdir,
)
from setup_spyder.perfil import HIDDEN_PATHS

__all__ = [
    "AUTHOR",
    "FONT_FAMILY",
    "REPO_URL",
    "launch",
    "main",
    "parse_args",
]


def print_banner(version: str, workdir: Path) -> None:
    body = Text()
    body.append("setup-spyder-fork", style="bold white")
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
            title="[bold cyan]◆ setup-spyder-fork[/]",
            subtitle="[dim]isolated profile · AI Terminal · leaves ~/.spyder-py3 untouched[/]",
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()


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
    """Open the fork instance: isolated profile, pane filter and AI Terminal.

    From another repository::

        from setup_spyder import launch_fork
        launch_fork(agent="codex", profile="ephemeral")

    Prints the banner and environment, then delegates to
    ``setup_spyder.launcher.launch``.
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
        log_warn(f"setup-spyder-fork finished with code {code}")
    return code


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="setup-spyder-fork",
        description=(
            "Open the bernardogoltz/spyder fork (Spyder 5.x) from this "
            f"environment with an isolated profile, {FONT_FAMILY} + wrap lines "
            "and the AI Terminal pane. For the native module only, use "
            "setup-spyder. Every step is printed to the terminal."
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
