#!/usr/bin/env bash
# Instala Spyder 5.x num venv isolado, abre a IDE e apaga o ambiente ao fechar.
set -euo pipefail

ENV_DIR="$(mktemp -d "${TMPDIR:-/tmp}/spyder5.XXXXXX")"

cleanup() {
  echo "Removendo ambiente isolado: $ENV_DIR"
  rm -rf "$ENV_DIR"
}
trap cleanup EXIT INT TERM

echo "Criando ambiente isolado em $ENV_DIR"
uv venv "$ENV_DIR" --python 3.11
uv pip install --python "$ENV_DIR/bin/python" "spyder>=5,<6"

echo "Abrindo Spyder $($ENV_DIR/bin/python -c 'import spyder; print(spyder.__version__)'). Feche a janela para apagar o ambiente."
"$ENV_DIR/bin/spyder" "$@"
