"""Child bootstrap: seed the profile, filter the Project pane, start Spyder.

Run as ``python -m setup_spyder.bootstrap [--seed-only] <spyder argv...>`` by
the launcher, with ``SPYDER_CONFDIR`` and the ``SETUP_SPYDER_*`` variables
already in the environment. This is the only process that imports Spyder.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence

from setup_spyder._console import log, log_error, log_kv, log_ok, log_warn
from setup_spyder.patches import apply_project_pane_filter
from setup_spyder.perfil import SEED_VERSION, resolve_editor_font, seed_profile

SEED_ONLY_FLAG = "--seed-only"


def split_bootstrap_argv(argv: Sequence[str]) -> tuple[bool, str | None, list[str]]:
    """Separate the bootstrap's own flag from Spyder's argv.

    Returns ``(seed_only, conf_dir, spyder_argv)``. ``--conf-dir`` stays in
    ``spyder_argv`` because Spyder understands it too.
    """
    seed_only = False
    conf_dir: str | None = None
    spyder_argv: list[str] = []
    args = list(argv)
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == SEED_ONLY_FLAG:
            seed_only = True
        else:
            spyder_argv.append(arg)
            if arg == "--conf-dir" and index + 1 < len(args):
                conf_dir = args[index + 1]
                spyder_argv.append(conf_dir)
                index += 1
            elif arg.startswith("--conf-dir="):
                conf_dir = arg.split("=", 1)[1]
        index += 1
    return seed_only, conf_dir, spyder_argv


def flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def hidden_names() -> list[str]:
    raw = os.environ.get("SETUP_SPYDER_HIDDEN", "")
    return [name for name in raw.split(os.pathsep) if name]


def main(argv: Sequence[str] | None = None) -> int:
    seed_only, conf_dir, spyder_argv = split_bootstrap_argv(
        sys.argv[1:] if argv is None else argv
    )
    conf_dir = conf_dir or os.environ.get("SPYDER_CONFDIR")
    if not conf_dir:
        log_error("bootstrap: --conf-dir or SPYDER_CONFDIR is required")
        return 2
    os.environ["SPYDER_CONFDIR"] = conf_dir

    font_family, _ = resolve_editor_font()
    wrote = seed_profile(
        conf_dir,
        font_family=font_family,
        com_estilo=flag("SETUP_SPYDER_SEED_STYLE", True),
    )
    if wrote:
        log_ok(f"Profile seeded (version {SEED_VERSION}, font {font_family!r})")
    else:
        log("Profile already seeded; preferences left as they are")
    log_kv("SPYDER_CONFDIR", conf_dir)
    if seed_only:
        return 0

    if not apply_project_pane_filter(hidden_names()):
        log_warn("Project pane filter not applied on this Spyder version")

    # `spyder.app.start` parses the command line at import time, so argv comes first.
    sys.argv = ["spyder", *spyder_argv]
    from spyder.app.start import main as spyder_main

    return spyder_main() or 0


if __name__ == "__main__":
    raise SystemExit(main())
