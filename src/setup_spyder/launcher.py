"""Resolve project and profile, then start Spyder in a clean child process.

The parent never imports Spyder. The native front seeds the profile (when
needed) and runs ``python -m spyder.app.start``. The fork front prepares
``SPYDER_CONFDIR`` and the ``SETUP_SPYDER_*`` context, then runs
``python -m setup_spyder.bootstrap`` on the same interpreter.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version as dist_version
from importlib.util import find_spec
from pathlib import Path
from typing import NamedTuple

from setup_spyder._children import run_child
from setup_spyder._console import log, log_error, log_kv, log_ok, log_warn
from setup_spyder.patches import render_launcher
from setup_spyder.perfil import (
    FONT_FAMILY,
    SEED_VERSION,
    conf_dir_for,
    force_writable,
    jetbrains_mono_installed,
    remove_tree,
    reset_profile as wipe_profile,
    resolve_hidden_paths,
    seeded_version,
)

AGENTS = ("auto", "codex", "claude", "none")
PROFILES = ("ephemeral", "project")
BOOTSTRAP_MODULE = "setup_spyder.bootstrap"
SPYDER_MODULE = "spyder.app.start"
FORK_ENV = "SETUP_SPYDER_FORK"
NATIVE_ENV_TO_DROP = (
    "SETUP_SPYDER_AGENT",
    "SETUP_SPYDER_AUTOSTART",
    FORK_ENV,
    "SETUP_SPYDER_HIDDEN",
    "SETUP_SPYDER_WORKDIR",
)

#: Spyder's own project layout (``spyder.plugins.projects.utils.config``),
#: written here without importing Spyder so the parent stays Qt-free.
PROJECT_CONF_VERSION = "0.2.0"
PROJECT_CONFIG_FILES: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "workspace.ini",
        "workspace",
        (
            ("restore_data_on_startup", "True"),
            ("save_data_on_exit", "True"),
            ("save_history", "True"),
            ("save_non_project_files", "False"),
            ("project_type", "'empty-project-type'"),
        ),
    ),
    (
        "codestyle.ini",
        "codestyle",
        (
            ("indentation", "True"),
            ("edge_line", "True"),
            ("edge_line_columns", "79"),
        ),
    ),
    (
        "vcs.ini",
        "vcs",
        (
            ("use_version_control", "False"),
            ("version_control_system", ""),
        ),
    ),
    ("encoding.ini", "encoding", (("text_encoding", "utf-8"),)),
)

__all__ = [
    "Profile",
    "build_child_command",
    "build_native_command",
    "ensure_spyproject",
    "force_writable",
    "launch",
    "launch_native",
    "remove_tree",
    "resolve_profile",
    "resolve_workdir",
    "write_launcher",
]


class Profile(NamedTuple):
    """The resolved ``SPYDER_CONFDIR`` and what to do with it on exit."""

    kind: str
    path: Path
    delete_at_exit: bool


def resolve_workdir(
    workdir: str | Path | None = None, cwd: str | Path | None = None
) -> Path:
    """Absolute, normalized project root: `workdir` against `cwd` (default cwd)."""
    base = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
    if workdir is None:
        return base
    return (base / Path(workdir)).resolve()


def render_project_ini(section: str, options: Sequence[tuple[str, str]]) -> str:
    lines = [f"[{section}]"]
    lines.extend(f"{key} = {value}" for key, value in options)
    lines += ["", "[main]", f"version = {PROJECT_CONF_VERSION}", "", ""]
    return "\n".join(lines)


def ensure_spyproject(root: Path) -> Path:
    """Create `.spyproject` in the opened repository, if it is not there yet."""
    spyproject = root / ".spyproject"
    config = spyproject / "config"
    config.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for filename, section, options in PROJECT_CONFIG_FILES:
        target = config / filename
        if target.is_file():
            continue
        target.write_text(render_project_ini(section, options), encoding="utf-8")
        created.append(target)
    if created:
        log_ok(f".spyproject ready ({len(created)} file(s) created):")
        for path in created:
            log_kv("file", path.relative_to(root))
    else:
        log_ok(f".spyproject already exists: {spyproject}")
    return spyproject


def write_launcher(conf_dir: Path, argv: Sequence[str], hidden: Sequence[str]) -> Path:
    """Write the standalone launcher script (not used by the child flow)."""
    launcher = conf_dir / "launch_spyder.py"
    launcher.write_text(render_launcher(argv, hidden), encoding="utf-8")
    return launcher


def spyder_ini(conf_dir: Path) -> Path:
    return Path(conf_dir) / "config" / "spyder.ini"


def is_installed(name: str) -> bool:
    """Import-availability check without importing the package."""
    try:
        return find_spec(name) is not None
    except ValueError:
        return name in sys.modules


def installed_version(name: str) -> str:
    try:
        return dist_version(name)
    except PackageNotFoundError:
        return "unknown version"


def resolve_profile(
    workdir: Path,
    *,
    conf_dir: str | Path | None = None,
    ephemeral: bool = False,
    profile: str | None = None,
    keep_config: bool = False,
) -> Profile:
    """Explicit `conf_dir` > ephemeral > project (the default)."""
    if profile is not None and profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; expected one of {PROFILES}")
    if conf_dir is not None:
        chosen = Path(conf_dir).resolve()
        chosen.mkdir(parents=True, exist_ok=True)
        return Profile("custom", chosen, False)
    if ephemeral or profile == "ephemeral":
        return Profile("ephemeral", conf_dir_for(workdir, ephemeral=True), not keep_config)
    return Profile("project", conf_dir_for(workdir, ephemeral=False), False)


def build_child_command(
    *,
    conf_dir: str | Path,
    workdir: str | Path,
    agent: str | None,
    autostart: bool,
    spyder_args: Sequence[str] = (),
    profile: str = "ephemeral",
    hidden: Sequence[str] = (),
    sem_estilo: bool = False,
    seed_only: bool = False,
) -> tuple[list[str], dict[str, str]]:
    """Command and environment for the child bootstrap. Pure: touches no file.

    ``--new-instance`` is passed only for ephemeral profiles; a project profile
    respects Spyder's single-instance mechanism. Extra Spyder arguments keep
    their order and ``--no-web-widgets`` is never added.
    """
    agent = agent or "auto"
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}; expected one of {AGENTS}")
    if agent == "none":
        autostart = False

    command = [sys.executable, "-m", BOOTSTRAP_MODULE]
    if seed_only:
        command.append("--seed-only")
    command += ["--conf-dir", str(conf_dir)]
    if profile == "ephemeral":
        command.append("--new-instance")
    command += ["-w", str(workdir), "-p", str(workdir), *spyder_args]

    env = dict(os.environ)
    env["SPYDER_CONFDIR"] = str(conf_dir)
    env["SETUP_SPYDER_AGENT"] = agent
    env["SETUP_SPYDER_WORKDIR"] = str(workdir)
    env["SETUP_SPYDER_AUTOSTART"] = "1" if autostart else "0"
    env["SETUP_SPYDER_HIDDEN"] = os.pathsep.join(hidden)
    env["SETUP_SPYDER_SEED_STYLE"] = "0" if sem_estilo else "1"
    env[FORK_ENV] = "1"
    return command, env


def build_native_command(
    *,
    conf_dir: str | Path,
    workdir: str | Path,
    spyder_args: Sequence[str] = (),
    sem_estilo: bool = False,
    seed_only: bool = False,
) -> tuple[list[str], dict[str, str]]:
    """Command and environment for the native front. Pure: touches no file.

    ``seed_only`` runs the bootstrap just to write the profile. Otherwise the
    child is Spyder's own module (``python -m spyder.app.start``), with no
    agent, pane filter or fork flag.
    """
    env = dict(os.environ)
    env["SPYDER_CONFDIR"] = str(conf_dir)
    env["SETUP_SPYDER_SEED_STYLE"] = "0" if sem_estilo else "1"
    for name in NATIVE_ENV_TO_DROP:
        env.pop(name, None)

    if seed_only:
        command = [
            sys.executable,
            "-m",
            BOOTSTRAP_MODULE,
            "--seed-only",
            "--conf-dir",
            str(conf_dir),
            "-w",
            str(workdir),
            "-p",
            str(workdir),
        ]
        return command, env

    command = [
        sys.executable,
        "-m",
        SPYDER_MODULE,
        "-w",
        str(workdir),
        "-p",
        str(workdir),
        *spyder_args,
    ]
    return command, env


def log_runtime() -> bool:
    """Log Spyder, pandas and font availability. False when Spyder is missing."""
    missing = [name for name in ("spyder", "spyder_kernels") if not is_installed(name)]
    if missing:
        log_error(f"missing dependency: {', '.join(missing)}")
        log("In the other repository, add this package:")
        log_kv("install", "uv add --dev git+https://github.com/bernardogoltz/setup-spyder")
        return False
    log_ok(
        f"Spyder {installed_version('spyder')}  ·  "
        f"spyder-kernels {installed_version('spyder-kernels')}"
    )
    if is_installed("pandas"):
        log_ok(f"pandas {installed_version('pandas')}")
    else:
        log_warn("pandas is not installed in this environment")

    fonts = jetbrains_mono_installed()
    if fonts:
        log_ok(f"Font {FONT_FAMILY} found ({len(fonts)} file(s))")
    else:
        log_warn(f"{FONT_FAMILY} not installed; the child falls back to Spyder's font")
    return True


def needs_seed(conf_dir: str | Path) -> bool:
    """True when the profile has no seed, or an older seed version."""
    current = seeded_version(conf_dir)
    return current is None or current < SEED_VERSION


def _run_spyder_child(
    command: list[str],
    env: dict[str, str],
    chosen: Profile,
    *,
    no_launch: bool,
) -> int:
    try:
        # The child tree (Spyder, its kernels, pylsp, QtWebEngine) dies with
        # this process: Job Object on Windows, session + signal forwarding on
        # POSIX. No shell in between.
        code = run_child(command, env=env)
        ini = spyder_ini(chosen.path)
        if ini.is_file():
            log_kv("config", ini)
        if code == 0:
            log_ok(f"Spyder exited with code {code}" if not no_launch else "Profile ready.")
        else:
            log_warn(f"child exited with code {code}")
        return code
    finally:
        if chosen.delete_at_exit:
            log(f"Removing ephemeral profile: {chosen.path}")
            remove_tree(chosen.path)
        elif chosen.kind == "ephemeral":
            log_warn(f"keep_config=True: keeping {chosen.path}")


def launch_native(
    spyder_args: Sequence[str] = (),
    *,
    no_launch: bool = False,
    sem_estilo: bool = False,
    workdir: str | Path | None = None,
    reset_profile: bool = False,
) -> int:
    """Prepare `.spyproject` and the project profile, then run Spyder as a module.

    The IDE child is ``python -m spyder.app.start``. Seeding (fonts, popups,
    style) happens in a short bootstrap child only when the profile is missing
    or ``no_launch`` is set. No AI Terminal, no project-pane filter.
    """
    workdir = resolve_workdir(workdir)
    extra_args = [arg for arg in spyder_args if arg != "--"]

    if not log_runtime():
        return 1

    ensure_spyproject(workdir)
    chosen = resolve_profile(workdir)
    log(f"Profile ({chosen.kind}): {chosen.path}")
    log("(the user's ~/.spyder-py3 is left untouched)")

    if reset_profile:
        try:
            wipe_profile(chosen.path, project_root=workdir)
        except ValueError as exc:
            log_error(str(exc))
            return 1
        log_ok(f"Profile reset: {chosen.path}")

    seed_first = no_launch or needs_seed(chosen.path)
    if seed_first:
        seed_command, seed_env = build_native_command(
            conf_dir=chosen.path,
            workdir=workdir,
            sem_estilo=sem_estilo,
            seed_only=True,
        )
        log_kv("command", " ".join(seed_command))
        if no_launch:
            log("no_launch: seeding the profile without opening Spyder.")
        code = _run_spyder_child(
            seed_command, seed_env, chosen, no_launch=True,
        )
        if no_launch or code != 0:
            return code

    command, env = build_native_command(
        conf_dir=chosen.path,
        workdir=workdir,
        spyder_args=extra_args,
        sem_estilo=sem_estilo,
        seed_only=False,
    )
    log_kv("command", " ".join(command))
    log_ok("Opening Spyder now...")
    log("Close the Spyder window to finish.")
    return _run_spyder_child(command, env, chosen, no_launch=False)


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
    """Prepare the project and profile, then run the fork instance in a child.

    Returns the child's exit code (``0`` for ``no_launch``), or ``1`` when
    Spyder is not installed in this environment.
    """
    workdir = resolve_workdir(workdir)
    extra_args = [arg for arg in spyder_args if arg != "--"]

    if not log_runtime():
        return 1

    ensure_spyproject(workdir)

    try:
        chosen = resolve_profile(
            workdir,
            conf_dir=conf_dir,
            ephemeral=ephemeral,
            profile=profile,
            keep_config=keep_config,
        )
    except ValueError as exc:
        log_error(str(exc))
        return 1
    log(f"Profile ({chosen.kind}): {chosen.path}")
    log("(the user's ~/.spyder-py3 is left untouched)")

    if reset_profile:
        if chosen.kind == "ephemeral":
            log("reset_profile: the ephemeral profile is already fresh")
        else:
            try:
                wipe_profile(chosen.path, project_root=workdir)
            except ValueError as exc:
                log_error(str(exc))
                return 1
            log_ok(f"Profile reset: {chosen.path}")

    hidden = resolve_hidden_paths(hide, show)
    log_ok(f"Hiding {len(hidden)} name(s) from the Project pane:")
    log_kv("hidden", ", ".join(hidden))

    command, env = build_child_command(
        conf_dir=chosen.path,
        workdir=workdir,
        agent=agent,
        autostart=agent != "none",
        spyder_args=extra_args,
        profile=chosen.kind,
        hidden=hidden,
        sem_estilo=sem_estilo,
        seed_only=no_launch,
    )
    log_kv("agent", env["SETUP_SPYDER_AGENT"])
    log_kv("command", " ".join(command))
    if no_launch:
        log("no_launch: seeding the profile without opening Spyder.")
    else:
        log_ok("Opening Spyder now...")
        log("Close the Spyder window to finish.")

    return _run_spyder_child(command, env, chosen, no_launch=no_launch)
