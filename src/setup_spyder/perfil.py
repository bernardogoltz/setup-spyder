"""Isolated Spyder profile: location, versioned seed and safe reset.

The profile is the ``SPYDER_CONFDIR`` handed to the child process. It lives in
``<project>/.spyproject/setup-spyder/`` by default, or in a throwaway temp
directory when the profile is ephemeral. The preferences are written once, as a
versioned seed, and never rewritten on later boots.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

ConfKey = tuple[str, str]
ConfMap = dict[ConfKey, object]

CONF_DIRNAME = os.path.join(".spyproject", "setup-spyder")
EPHEMERAL_PREFIX = "setup-spyder-conf-"
FONT_FAMILY = "JetBrains Mono"

#: Bump when the seeded values change; the profile is re-seeded on next boot.
SEED_VERSION: int = 2
SEED_MARKER = "setup-spyder-seed.json"

#: Names hidden from Spyder's Project pane, on top of the ones Spyder already
#: hides itself (``.spyproject``, ``__pycache__``, ``.git``, ...). Matched by
#: basename, at any depth in the tree.
HIDDEN_PATHS = (
    # Virtual environments
    ".venv",
    "venv",
    ".env",
    "env",
    ".tox",
    # Build and distribution artifacts
    "dist",
    "build",
    ".eggs",
    "node_modules",
    # Tool caches
    ".ruff_cache",
    ".mypy_cache",
    ".coverage",
    "htmlcov",
    # Repository and tooling metadata
    ".claude",
    ".docs",
    ".github",
    ".gitlab",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".dockerignore",
    ".python-version",
    ".pre-commit-config.yaml",
    "uv.lock",
    "poetry.lock",
    # Windows folder settings, the one bit of OS clutter Spyder does not hide
    "desktop.ini",
    CONF_DIRNAME,
)

#: Always seeded: silence the update, tour, DPI, missing-dependency and
#: internal-error dialogs and the kernel confirmations, and make Spyder use the
#: interpreter that started it.
#:
#: Internal error reports and the missing-dependency warning used to stay on
#: (plan, section 8). The owner of the fork revoked that: this is a personal
#: profile and both are boot noise. The tradeoff is real -- an internal Spyder
#: error now fails silently, with nothing offering to report it. Both are
#: reachable again in Preferences > Application > Advanced.
#:
#: Single-instance mode is left at Spyder's default so a project profile is not
#: opened twice (plan, section 5.3); the ephemeral profile passes
#: --new-instance instead.
POPUPS: ConfMap = {
    ("main", "check_updates_on_startup"): False,
    ("main", "show_dpi_message"): False,
    ("main", "prompt_on_exit"): False,
    ("main", "show_internal_errors"): False,
    # Gated by the fork; a Spyder without the key simply ignores it.
    ("main", "show_missing_dependencies"): False,
    ("tours", "show_tour_message"): False,
    ("ipython_console", "ask_before_restart"): False,
    ("ipython_console", "ask_before_closing"): False,
    ("ipython_console", "show_reset_namespace_warning"): False,
    ("main_interpreter", "default"): True,
    ("main_interpreter", "custom"): False,
}

#: Appearance and editor. Skipped with ``--sem-estilo``.
STYLE: ConfMap = {
    ("appearance", "ui_theme"): "dark",
    ("appearance", "selected"): "spyder/dark",
    ("editor", "wrap"): True,
    ("editor", "edge_line"): True,
    ("editor", "blank_spaces"): False,
    ("main", "panes_locked"): True,
    ("toolbar", "toolbars_visible"): True,
}


# Filesystem helpers -----------------------------------------------------


def force_writable(path: Path) -> None:
    """Clear the read-only bit Windows leaves on hardlinked cache files."""
    try:
        path.chmod(path.stat().st_mode | stat.S_IWRITE)
    except OSError:  # pragma: no cover - the file is about to be deleted anyway
        pass


def remove_tree(path: Path) -> None:
    """Delete a directory tree, retrying past files Windows marks read-only."""
    shutil.rmtree(path, ignore_errors=True)
    if not path.is_dir():
        return
    for item in path.rglob("*"):
        force_writable(item)
    force_writable(path)
    shutil.rmtree(path, ignore_errors=True)


# Project pane blocklist -------------------------------------------------


def split_names(entries: Sequence[str]) -> set[str]:
    """Split repeated, comma-separated `--hide`/`--show` values into names."""
    return {
        name.strip()
        for entry in entries
        for name in entry.split(",")
        if name.strip()
    }


def resolve_hidden_paths(
    hide: Sequence[str] = (), show: Sequence[str] = ()
) -> list[str]:
    """Build the Project pane blocklist: the defaults, plus `hide`, minus `show`."""
    names = set(HIDDEN_PATHS) | split_names(hide)
    return sorted(names - split_names(show))


# Profile location -------------------------------------------------------


def conf_dir_for(workdir: str | Path, ephemeral: bool = False) -> Path:
    """Spyder config directory: stable inside the project, or a fresh temp dir."""
    if ephemeral:
        return Path(tempfile.mkdtemp(prefix=EPHEMERAL_PREFIX))
    path = Path(workdir) / CONF_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_managed_profile(conf_dir: Path, project_root: Path | None = None) -> bool:
    """True when `conf_dir` is a location this package created and may wipe."""
    if conf_dir.is_symlink():
        return False
    resolved = conf_dir.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if resolved.parent == temp_root and resolved.name.startswith(EPHEMERAL_PREFIX):
        return True
    if project_root is None:
        return False
    return resolved == (Path(project_root).resolve() / CONF_DIRNAME)


def reset_profile(conf_dir: str | Path, *, project_root: str | Path | None = None) -> Path:
    """Wipe and recreate the resolved profile, after proving it is ours to wipe.

    Accepts only ``<project_root>/.spyproject/setup-spyder`` (when
    ``project_root`` is given) or an ephemeral ``setup-spyder-conf-*`` directory
    directly under the temp root. Symlinks and anything else raise ``ValueError``
    before a single file is touched.
    """
    candidate = Path(conf_dir)
    root = Path(project_root) if project_root is not None else None
    if not is_managed_profile(candidate, root):
        raise ValueError(
            f"refusing to reset {candidate}: not a setup-spyder profile "
            f"(expected <project>/{CONF_DIRNAME} or {EPHEMERAL_PREFIX}* under "
            f"{tempfile.gettempdir()})"
        )
    resolved = candidate.resolve()
    remove_tree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


# Fonts ------------------------------------------------------------------


def font_dirs() -> tuple[Path, ...]:
    """Directories the current platform installs fonts into (user first)."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        windir = os.environ.get("WINDIR") or r"C:\Windows"
        return (
            Path(local) / "Microsoft" / "Windows" / "Fonts",
            Path(windir) / "Fonts",
        )
    if sys.platform == "darwin":
        return (
            Path.home() / "Library" / "Fonts",
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
        )
    return (
        Path.home() / ".local" / "share" / "fonts",
        Path("/usr/local/share/fonts"),
        Path("/usr/share/fonts"),
    )


def jetbrains_mono_installed() -> list[Path]:
    hits: list[Path] = []
    for directory in font_dirs():
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
        return "Consolas" if os.name == "nt" else "Monospace"


def resolve_editor_font() -> tuple[str, list[Path]]:
    """Try JetBrains Mono; fall back to Spyder's default font when missing."""
    hits = jetbrains_mono_installed()
    if hits:
        return FONT_FAMILY, hits
    return spyder_default_font(), []


def font_family_value(family: str) -> list[str]:
    """Spyder stores font/family as a list of fallbacks."""
    try:
        from spyder.config.fonts import MONOSPACE

        rest = [name for name in MONOSPACE if name != family]
        return [family] + rest
    except Exception:
        return [family]


# Seed -------------------------------------------------------------------


def perfil_completo(font_family: str, com_estilo: bool = True) -> ConfMap:
    """The values seeded into a new profile."""
    valores = dict(POPUPS)
    if com_estilo:
        valores.update(STYLE)
        valores[("appearance", "font/family")] = font_family_value(font_family)
        valores[("appearance", "rich_font/family")] = font_family_value(
            font_family
        )
    return valores


def seed_marker(conf_dir: str | Path) -> Path:
    return Path(conf_dir) / SEED_MARKER


def seeded_version(conf_dir: str | Path) -> int | None:
    """Seed version recorded in the profile, or None for a fresh profile."""
    marker = seed_marker(conf_dir)
    if not marker.is_file():
        return None
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        return int(payload["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def seed_profile(
    conf_dir: str | Path,
    *,
    version: int = SEED_VERSION,
    font_family: str | None = None,
    com_estilo: bool = True,
) -> bool:
    """Write the preferences into `conf_dir` once; return True iff it wrote.

    Skips entirely when the marker already records `version` or newer, so a
    later boot never rewrites what the user changed. Imports Spyder's config
    only after pointing ``SPYDER_CONFDIR`` at the profile.
    """
    conf_dir = Path(conf_dir)
    current = seeded_version(conf_dir)
    if current is not None and current >= version:
        return False

    conf_dir.mkdir(parents=True, exist_ok=True)
    if font_family is None:
        font_family, _ = resolve_editor_font()
    values = perfil_completo(font_family, com_estilo=com_estilo)

    os.environ["SPYDER_CONFDIR"] = str(conf_dir)
    from spyder.config.manager import ConfigurationManager

    conf = ConfigurationManager()
    for (section, option), value in values.items():
        conf.set(section, option, value)

    seed_marker(conf_dir).write_text(
        json.dumps(
            {
                "version": version,
                "style": com_estilo,
                "keys": sorted(f"{section}/{option}" for section, option in values),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return True
