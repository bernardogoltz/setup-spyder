"""CLI falsa: registra como foi invocada e sai com o codigo pedido.

Uso::

    fake_cli.py <arquivo-de-registro> <exit-code> [args...]

Grava um JSON com ``argv``, ``cwd`` e um recorte do ambiente. Serve para
provar, do lado do teste, que o launcher montou uma *lista* de argumentos e
nao uma linha de comando concatenada para um shell.
"""

from __future__ import annotations

import json
import os
import sys

INTERESTING_ENV = (
    "SPYDER_CONFDIR",
    "SETUP_SPYDER_AGENT",
    "SETUP_SPYDER_WORKDIR",
    "SETUP_SPYDER_AUTOSTART",
    "TERM",
)


def main() -> int:
    record_path = sys.argv[1]
    exit_code = int(sys.argv[2])
    payload = {
        "argv": sys.argv[3:],
        "cwd": os.getcwd(),
        "env": {key: os.environ.get(key) for key in INTERESTING_ENV},
        "isatty": sys.stdin.isatty(),
    }
    with open(record_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
