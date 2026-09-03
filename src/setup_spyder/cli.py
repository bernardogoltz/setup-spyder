"""Configure and open Spyder 5.x in an isolated, verbose way."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

FONT_FAMILY = "JetBrains Mono"
FONT_DIRS = (
    Path.home() / "Library" / "Fonts",
    Path("/Library/Fonts"),
    Path.home() / ".local" / "share" / "fonts",
    Path("/usr/share/fonts"),
)
REPO_URL = "https://github.com/bernardogoltz/setup-spyder"

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


def print_banner(version: str, workdir: Path) -> None:
    body = Text()
    body.append("setup-spyder", style="bold white")
    body.append(f"  v{version}\n", style="dim")
    body.append("isolated Spyder 5.x", style="cyan")
    body.append("  ·  ", style="dim")
    body.append(FONT_FAMILY, style="magenta")
    body.append("  ·  ", style="dim")
    body.append("wrap lines\n\n", style="green")
    body.append("Hello — opening the project ", style="white")
    body.append(workdir.name, style="bold bright_cyan")
    body.append("\n")
    body.append(str(workdir), style="dim")
    console.print()
    console.print(
        Panel(
            body,
            title="[bold cyan]◆ setup-spyder[/]",
            subtitle="[dim]isolated environment · leaves ~/.spyder-py3 untouched[/]",
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


def jetbrains_mono_installed() -> list[Path]:
    hits: list[Path] = []
    for directory in FONT_DIRS:
        if not directory.is_dir():
            continue
        hits.extend(sorted(directory.glob("JetBrainsMono*")))
        hits.extend(sorted(directory.glob("JetBrainsMonoNerdFont*")))
    return hits


def spyder_default_font() -> str:
    """Spyder's default monospace font (Menlo on macOS, Ubuntu Mono, etc.)."""
    try:
        from spyder.config.fonts import MONOSPACE

        return MONOSPACE[0]
    except Exception:
        return "Monospace"


def resolve_editor_font() -> tuple[str, list[Path]]:
    """Try JetBrains Mono; fall back to Spyder's default font when missing."""
    try:
        hits = jetbrains_mono_installed()
        if not hits:
            raise FileNotFoundError(FONT_FAMILY)
        return FONT_FAMILY, hits
    except Exception:
        default = spyder_default_font()
        log_warn(
            f"{FONT_FAMILY} unavailable; using Spyder's default font ({default})"
        )
        return default, []


def ensure_spyproject(root: Path) -> Path:
    """Create `.spyproject` in the opened repository, if it is not there yet."""
    spyproject = root / ".spyproject"
    if spyproject.is_dir():
        log_ok(f".spyproject already exists: {spyproject}")
        return spyproject

    log(f"Creating .spyproject in {root}")
    (spyproject / "config").mkdir(parents=True, exist_ok=True)
    from spyder.plugins.projects.api import EmptyProject

    EmptyProject(root_path=str(root))

    files = sorted(
        path.relative_to(root) for path in spyproject.rglob("*") if path.is_file()
    )
    if files:
        log_ok(f".spyproject ready ({len(files)} file(s)):")
        for relative in files:
            log_kv("file", relative)
    else:
        log_warn(".spyproject created, but no config file showed up")
    return spyproject


def apply_spyder_config(
    conf_dir: Path, font_family: str | None = None
) -> tuple[object, object]:
    os.environ["SPYDER_CONFDIR"] = str(conf_dir)
    from spyder.config.manager import CONF

    if font_family is None:
        font_family, _ = resolve_editor_font()

    log(f"Applying font {font_family!r}")
    CONF.set("appearance", "font/family", [font_family])
    log("Turning on wrap lines in the editor (editor.wrap = True)")
    CONF.set("editor", "wrap", True)

    font = CONF.get("appearance", "font/family")
    wrap = CONF.get("editor", "wrap")
    return font, wrap


def launch(
    spyder_args: Sequence[str] = (),
    *,
    no_launch: bool = False,
    keep_config: bool = False,
    workdir: str | Path | None = None,
) -> int:
    """Configure Spyder 5.x, create `.spyproject` in the repository and open the IDE.

    From another repository::

        from setup_spyder import launch
        launch()
    """
    from setup_spyder import __version__

    workdir = Path(workdir).resolve() if workdir else Path.cwd().resolve()
    extra_args = [a for a in spyder_args if a != "--"]

    print_banner(__version__, workdir)
    print_env(workdir)

    try:
        import spyder
        import spyder_kernels
    except ImportError as exc:
        log_error(f"missing dependency ({exc}).")
        log("In the other repository, add this package:")
        log_kv("install", f"uv add git+{REPO_URL}")
        log("Or run it without installing into the project:")
        log_kv("oneshot", f"uvx --from git+{REPO_URL} setup-spyder")
        return 1

    log_ok(f"Spyder {spyder.__version__}  ·  spyder-kernels {spyder_kernels.__version__}")
    if not spyder.__version__.startswith("5."):
        log_warn(f"expected Spyder 5.x, got {spyder.__version__}")

    try:
        import pandas as pd
    except ImportError:
        log_warn("pandas is not installed in this environment")
    else:
        log_ok(f"pandas {pd.__version__}")

    font_family, fonts = resolve_editor_font()
    if fonts:
        log_ok(f"Font {font_family} found ({len(fonts)} file(s))")
        for path in fonts[:8]:
            log_kv("file", path)
        if len(fonts) > 8:
            log_kv("...", f"{len(fonts) - 8} more file(s)")

    spyproject = ensure_spyproject(workdir)

    conf_dir = Path(tempfile.mkdtemp(prefix="setup-spyder-conf-"))
    log(f"Isolated config at: {conf_dir}")
    log("(the user's ~/.spyder-py3 is left untouched)")

    try:
        font, wrap = apply_spyder_config(conf_dir, font_family=font_family)
        log_ok("Config written. Checking the values:")
        log_kv("appearance.font/family", font)
        log_kv("editor.wrap", wrap)

        ini_path = conf_dir / "config" / "spyder.ini"
        if ini_path.is_file():
            log(f"Config file: {ini_path}")
            log_kv("size", f"{ini_path.stat().st_size} bytes")
        else:
            log_warn(f"expected {ini_path}, but the file does not exist yet")

        if no_launch:
            log_ok("no_launch=True: setup finished without opening Spyder.")
            log(f"The Spyder project stays at {spyproject}")
            return 0

        spyder_bin = shutil.which("spyder")
        if spyder_bin is None:
            log_error("the 'spyder' executable is not on this environment's PATH.")
            return 1

        cmd = [
            spyder_bin,
            "--conf-dir",
            str(conf_dir),
            "--new-instance",
            "-w",
            str(workdir),
            "-p",
            str(workdir),
            *extra_args,
        ]
        log_ok("Opening Spyder now...")
        log_kv("command", " ".join(cmd))
        log("Close the Spyder window to finish (and delete the isolated config).")
        completed = subprocess.run(cmd, check=False)
        if completed.returncode == 0:
            log_ok(f"Spyder exited with code {completed.returncode}")
        else:
            log_warn(f"Spyder exited with code {completed.returncode}")
        return completed.returncode
    finally:
        if keep_config:
            log_warn(f"keep_config=True: keeping {conf_dir}")
        else:
            log(f"Removing isolated config: {conf_dir}")
            shutil.rmtree(conf_dir, ignore_errors=True)
            log_ok("Cleanup done.")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="setup-spyder",
        description=(
            "Install/use Spyder 5.x in an isolated environment, configure "
            f"{FONT_FAMILY} + wrap lines and open the IDE. "
            "Every step is printed to the terminal."
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
        help="Do not delete the isolated config directory on exit.",
    )
    parser.add_argument(
        "-w",
        "--workdir",
        default=None,
        help="Spyder working directory (default: current directory).",
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
        workdir=args.workdir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
