#!/usr/bin/env bash
# Atalho local: mesmo fluxo verboso do pacote setup-spyder.
set -euo pipefail
cd "$(dirname "$0")"
exec uv run setup-spyder "$@"
