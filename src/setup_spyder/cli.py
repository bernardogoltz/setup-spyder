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

FONT_FAMILY = "JetBrains Mono"
FONT_DIRS = (
    Path.home() / "Library" / "Fonts",
    Path("/Library/Fonts"),
    Path.home() / ".local" / "share" / "fonts",
    Path("/usr/share/fonts"),
)
REPO_URL = "https://github.com/bernardogoltz/setup-spyder"


def log(message: str) -> None:
    print(f"[setup-spyder] {message}", flush=True)


def log_kv(key: str, value: object) -> None:
    log(f"  {key}: {value}")


def jetbrains_mono_installed() -> list[Path]:
    hits: list[Path] = []
    for directory in FONT_DIRS:
        if not directory.is_dir():
            continue
        hits.extend(sorted(directory.glob("JetBrainsMono*")))
        hits.extend(sorted(directory.glob("JetBrainsMonoNerdFont*")))
    return hits


def ensure_spyproject(root: Path) -> Path:
    """Cria `.spyproject` no repositório aberto, se ainda não existir."""
    spyproject = root / ".spyproject"
    if spyproject.is_dir():
        log(f".spyproject já existe: {spyproject}")
        return spyproject

    log(f"Criando .spyproject em {root}")
    (spyproject / "config").mkdir(parents=True, exist_ok=True)
    from spyder.plugins.projects.api import EmptyProject

    EmptyProject(root_path=str(root))

    files = sorted(
        path.relative_to(root) for path in spyproject.rglob("*") if path.is_file()
    )
    if files:
        log(f".spyproject pronto ({len(files)} arquivo(s)):")
        for relative in files:
            log_kv("arquivo", relative)
    else:
        log("AVISO: .spyproject criado, mas nenhum arquivo de config apareceu")
    return spyproject


def apply_spyder_config(conf_dir: Path) -> tuple[object, object]:
    os.environ["SPYDER_CONFDIR"] = str(conf_dir)
    from spyder.config.manager import CONF

    log(f"Aplicando fonte padrão {FONT_FAMILY!r}")
    CONF.set("appearance", "font/family", [FONT_FAMILY])
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

    log("=" * 60)
    log(f"setup-spyder {__version__}")
    log("Spyder 5.x isolado + JetBrains Mono + wrap lines")
    log("=" * 60)

    log(f"Python executável: {sys.executable}")
    log(f"Python versão: {sys.version.split()[0]}")
    log(f"Ambiente isolado: {sys.prefix}")
    log(f"Repositório atual (workdir): {workdir}")

    try:
        import spyder
        import spyder_kernels
    except ImportError as exc:
        log(f"ERRO: dependência ausente ({exc}).")
        log("No outro repositório, adicione este pacote:")
        log(f"  uv add git+{REPO_URL}")
        log("Ou rode sem instalar no projeto:")
        log(f"  uvx --from git+{REPO_URL} setup-spyder")
        return 1

    log(f"Spyder encontrado: {spyder.__version__}")
    log(f"spyder-kernels: {spyder_kernels.__version__}")
    if not spyder.__version__.startswith("5."):
        log(f"AVISO: esperado Spyder 5.x, veio {spyder.__version__}")

    try:
        import pandas as pd
    except ImportError:
        log("pandas: não instalado neste ambiente")
    else:
        log(f"pandas: {pd.__version__}")

    fonts = jetbrains_mono_installed()
    if fonts:
        log(f"Fonte {FONT_FAMILY} encontrada no sistema ({len(fonts)} arquivo(s)):")
        for path in fonts[:8]:
            log_kv("arquivo", path)
        if len(fonts) > 8:
            log_kv("...", f"mais {len(fonts) - 8} arquivo(s)")
    else:
        log(
            f"AVISO: não achei arquivos de {FONT_FAMILY} nas pastas de fontes. "
            "O Spyder pode cair na fonte fallback."
        )

    spyproject = ensure_spyproject(workdir)

    conf_dir = Path(tempfile.mkdtemp(prefix="setup-spyder-conf-"))
    log(f"Config isolada em: {conf_dir}")
    log("(não mexe no ~/.spyder-py3 do usuário)")

    try:
        font, wrap = apply_spyder_config(conf_dir)
        log("Config gravada. Conferindo valores:")
        log_kv("appearance.font/family", font)
        log_kv("editor.wrap", wrap)

        ini_path = conf_dir / "config" / "spyder.ini"
        if ini_path.is_file():
            log(f"Arquivo de config: {ini_path}")
            log(f"Tamanho: {ini_path.stat().st_size} bytes")
        else:
            log(f"AVISO: esperado {ini_path}, mas o arquivo ainda não existe")

        if no_launch:
            log("no_launch=True: setup concluído sem abrir o Spyder.")
            log(f"Projeto Spyder permanece em {spyproject}")
            return 0

        spyder_bin = shutil.which("spyder")
        if spyder_bin is None:
            log("ERRO: executável 'spyder' não está no PATH deste ambiente.")
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
        log("Abrindo Spyder:")
        log("  " + " ".join(cmd))
        log("Feche a janela do Spyder para encerrar (e apagar a config isolada).")
        completed = subprocess.run(cmd, check=False)
        log(f"Spyder encerrou com código {completed.returncode}")
        return completed.returncode
    finally:
        if keep_config:
            log(f"keep_config=True: mantendo {conf_dir}")
        else:
            log(f"Removendo config isolada: {conf_dir}")
            shutil.rmtree(conf_dir, ignore_errors=True)
            log("Cleanup concluído.")


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
