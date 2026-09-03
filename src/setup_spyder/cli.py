"""Configura e abre o Spyder 5.x de forma isolada e verbosa."""

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
    body.append("Spyder 5.x isolado", style="cyan")
    body.append("  ·  ", style="dim")
    body.append(FONT_FAMILY, style="magenta")
    body.append("  ·  ", style="dim")
    body.append("wrap lines\n\n", style="green")
    body.append("Olá — abrindo o projeto ", style="white")
    body.append(workdir.name, style="bold bright_cyan")
    body.append("\n")
    body.append(str(workdir), style="dim")
    console.print()
    console.print(
        Panel(
            body,
            title="[bold cyan]◆ setup-spyder[/]",
            subtitle="[dim]ambiente isolado · não mexe no ~/.spyder-py3[/]",
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
    table.add_row("Executável", sys.executable)
    table.add_row("Ambiente", sys.prefix)
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
    """Fonte monoespaçada padrão do Spyder (Menlo no macOS, Ubuntu Mono, etc.)."""
    try:
        from spyder.config.fonts import MONOSPACE

        return MONOSPACE[0]
    except Exception:
        return "Monospace"


def resolve_editor_font() -> tuple[str, list[Path]]:
    """Tenta JetBrains Mono; se não estiver instalada, usa a fonte padrão do Spyder."""
    try:
        hits = jetbrains_mono_installed()
        if not hits:
            raise FileNotFoundError(FONT_FAMILY)
        return FONT_FAMILY, hits
    except Exception:
        default = spyder_default_font()
        log_warn(
            f"{FONT_FAMILY} indisponível; usando a fonte padrão do Spyder ({default})"
        )
        return default, []


def ensure_spyproject(root: Path) -> Path:
    """Cria `.spyproject` no repositório aberto, se ainda não existir."""
    spyproject = root / ".spyproject"
    if spyproject.is_dir():
        log_ok(f".spyproject já existe: {spyproject}")
        return spyproject

    log(f"Criando .spyproject em {root}")
    (spyproject / "config").mkdir(parents=True, exist_ok=True)
    from spyder.plugins.projects.api import EmptyProject

    EmptyProject(root_path=str(root))

    files = sorted(
        path.relative_to(root) for path in spyproject.rglob("*") if path.is_file()
    )
    if files:
        log_ok(f".spyproject pronto ({len(files)} arquivo(s)):")
        for relative in files:
            log_kv("arquivo", relative)
    else:
        log_warn(".spyproject criado, mas nenhum arquivo de config apareceu")
    return spyproject


def apply_spyder_config(
    conf_dir: Path, font_family: str | None = None
) -> tuple[object, object]:
    os.environ["SPYDER_CONFDIR"] = str(conf_dir)
    from spyder.config.manager import CONF

    if font_family is None:
        font_family, _ = resolve_editor_font()

    log(f"Aplicando fonte {font_family!r}")
    CONF.set("appearance", "font/family", [font_family])
    log("Ligando wrap lines no editor (editor.wrap = True)")
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
    """Configura o Spyder 5.x, cria `.spyproject` no repositório e abre a IDE.

    Em outro repositório::

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
        log_error(f"dependência ausente ({exc}).")
        log("No outro repositório, adicione este pacote:")
        log_kv("instalar", f"uv add git+{REPO_URL}")
        log("Ou rode sem instalar no projeto:")
        log_kv("oneshot", f"uvx --from git+{REPO_URL} setup-spyder")
        return 1

    log_ok(f"Spyder {spyder.__version__}  ·  spyder-kernels {spyder_kernels.__version__}")
    if not spyder.__version__.startswith("5."):
        log_warn(f"esperado Spyder 5.x, veio {spyder.__version__}")

    try:
        import pandas as pd
    except ImportError:
        log_warn("pandas não instalado neste ambiente")
    else:
        log_ok(f"pandas {pd.__version__}")

    font_family, fonts = resolve_editor_font()
    if fonts:
        log_ok(f"Fonte {font_family} encontrada ({len(fonts)} arquivo(s))")
        for path in fonts[:8]:
            log_kv("arquivo", path)
        if len(fonts) > 8:
            log_kv("...", f"mais {len(fonts) - 8} arquivo(s)")

    spyproject = ensure_spyproject(workdir)

    conf_dir = Path(tempfile.mkdtemp(prefix="setup-spyder-conf-"))
    log(f"Config isolada em: {conf_dir}")
    log("(não mexe no ~/.spyder-py3 do usuário)")

    try:
        font, wrap = apply_spyder_config(conf_dir, font_family=font_family)
        log_ok("Config gravada. Conferindo valores:")
        log_kv("appearance.font/family", font)
        log_kv("editor.wrap", wrap)

        ini_path = conf_dir / "config" / "spyder.ini"
        if ini_path.is_file():
            log(f"Arquivo de config: {ini_path}")
            log_kv("tamanho", f"{ini_path.stat().st_size} bytes")
        else:
            log_warn(f"esperado {ini_path}, mas o arquivo ainda não existe")

        if no_launch:
            log_ok("no_launch=True: setup concluído sem abrir o Spyder.")
            log(f"Projeto Spyder permanece em {spyproject}")
            return 0

        spyder_bin = shutil.which("spyder")
        if spyder_bin is None:
            log_error("executável 'spyder' não está no PATH deste ambiente.")
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
        log_ok("Abrindo o Spyder agora...")
        log_kv("comando", " ".join(cmd))
        log("Feche a janela do Spyder para encerrar (e apagar a config isolada).")
        completed = subprocess.run(cmd, check=False)
        if completed.returncode == 0:
            log_ok(f"Spyder encerrou com código {completed.returncode}")
        else:
            log_warn(f"Spyder encerrou com código {completed.returncode}")
        return completed.returncode
    finally:
        if keep_config:
            log_warn(f"keep_config=True: mantendo {conf_dir}")
        else:
            log(f"Removendo config isolada: {conf_dir}")
            shutil.rmtree(conf_dir, ignore_errors=True)
            log_ok("Cleanup concluído.")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="setup-spyder",
        description=(
            "Instala/usa Spyder 5.x num ambiente isolado, configura "
            f"{FONT_FAMILY} + wrap lines e abre a IDE. "
            "Cada passo é impresso no terminal."
        ),
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Só configura; não abre a janela do Spyder.",
    )
    parser.add_argument(
        "--keep-config",
        action="store_true",
        help="Não apaga o diretório de config isolado ao sair.",
    )
    parser.add_argument(
        "-w",
        "--workdir",
        default=None,
        help="Diretório de trabalho do Spyder (padrão: diretório atual).",
    )
    parser.add_argument(
        "spyder_args",
        nargs=argparse.REMAINDER,
        help="Argumentos extras passados ao Spyder (depois de --).",
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
