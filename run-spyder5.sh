#!/usr/bin/env bash
# Local shortcut: same verbose flow as the setup-spyder package.
set -euo pipefail
cd "$(dirname "$0")"
exec uv run setup-spyder "$@"
