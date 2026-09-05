"""Descobre, sem derrubar a sessao, se o QtWebEngine renderiza neste ambiente.

Um `QWebEngineView` que nao consegue subir o processo de renderizacao do
Chromium nao levanta excecao: ele *aborta*. O pytest inteiro morre junto - foi
o `exit code 134` (SIGABRT) do job `full (ubuntu-latest)`, assim que a suite
passou a esperar a pagina do terminal de fato carregar. Um `try/except` no
teste nao pega isso, porque nao ha excecao nenhuma: o processo acaba.

Entao a pergunta e feita antes, num subprocesso descartavel
(`_webengine_probe.py`). Se ele morrer, os testes que dependem da pagina viva
pulam com a razao - a mesma politica de `helpers.pending.requisitos` para um
import que falta, so que aplicada a uma falha que nao e um ImportError.
"""

from __future__ import annotations

import functools
import subprocess
import sys
from pathlib import Path

SONDA = Path(__file__).parent / "_webengine_probe.py"

#: A primeira partida do Chromium num runner sem GPU passa longe de ser
#: instantanea; o teto aqui e maior que o `LIMITE_MS` de dentro da sonda para
#: que ela consiga se explicar antes de ser morta de fora.
LIMITE_S = 120

DIAGNOSTICO = {
    2: "a pagina de teste nao carregou",
    3: "o JavaScript da pagina respondeu um valor inesperado",
    4: "a pagina nao terminou de carregar dentro do limite da sonda",
}


@functools.lru_cache(maxsize=None)
def motivo_indisponivel() -> "str | None":
    """`None` se o QtWebEngine renderiza mesmo; a razao do skip se nao.

    O resultado e memorizado: a sonda custa a partida de um Chromium e a
    resposta nao muda no meio de uma sessao.
    """
    try:
        sonda = subprocess.run(
            [sys.executable, str(SONDA)],
            timeout=LIMITE_S,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return (
            "o QtWebEngine nao renderiza neste ambiente - a sonda travou por "
            f"mais de {LIMITE_S}s"
        )
    except OSError as exc:  # pragma: no cover - interpretador sem subprocesso
        return f"a sonda do QtWebEngine nao pode ser executada ({exc})"

    if sonda.returncode == 0:
        return None

    detalhe = DIAGNOSTICO.get(sonda.returncode)
    if detalhe is None:
        # Negativo no POSIX e o sinal que matou o processo (-6 = SIGABRT).
        como = (
            f"sinal {-sonda.returncode}"
            if sonda.returncode < 0
            else f"codigo {sonda.returncode}"
        )
        detalhe = f"o processo do Chromium morreu ({como})"
    ultima = (sonda.stderr or "").strip().splitlines()
    return "o QtWebEngine nao renderiza neste ambiente - " + detalhe + (
        f": {ultima[-1]}" if ultima else ""
    )
