"""Nada de shell: argv como lista, executavel resolvido, sem concatenacao.

Secao 6.2 do plano ("O executavel deve ser iniciado com lista de argumentos,
nunca por concatenacao em um shell") e a linha de risco "Terminal incorporado
ampliar superficie de ataque -> sem shell e sem comandos concatenados".

A varredura estatica roda **hoje**, contra o codigo instalado, e cobre tambem
os modulos novos assim que eles existirem.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from helpers.pending import require_attr, require_module

pytestmark = [pytest.mark.unit]

SHELL_METACHARS = re.compile(r"[;&|><`$\n]")


def _sources(setup_spyder) -> list[Path]:
    root = Path(setup_spyder.__file__).parent
    return sorted(root.rglob("*.py"))


# Varredura estatica -----------------------------------------------------


@pytest.mark.phase0
def test_nenhum_modulo_usa_shell_true(setup_spyder):
    ofensores = []
    for path in _sources(setup_spyder):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "shell" and not (
                    isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                ):
                    ofensores.append(f"{path.name}:{node.lineno}")
    assert not ofensores, f"shell=True encontrado em {ofensores}"


@pytest.mark.phase0
@pytest.mark.parametrize("proibido", ["os.system", "os.popen", "subprocess.getoutput"])
def test_nenhum_modulo_chama_o_shell_do_sistema(setup_spyder, proibido):
    modulo, funcao = proibido.split(".")
    ofensores = []
    for path in _sources(setup_spyder):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == funcao
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == modulo
            ):
                ofensores.append(f"{path.name}:{node.lineno}")
    assert not ofensores, f"{proibido} encontrado em {ofensores}"


@pytest.mark.phase0
def test_subprocess_recebe_lista_e_nao_string(setup_spyder):
    """`subprocess.run("cmd " + arg)` e exatamente o que nao pode existir."""
    chamadas = {"run", "Popen", "call", "check_call", "check_output"}
    ofensores = []
    for path in _sources(setup_spyder):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in chamadas
                and node.args
            ):
                primeiro = node.args[0]
                if isinstance(primeiro, (ast.Constant, ast.JoinedStr, ast.BinOp)):
                    ofensores.append(f"{path.name}:{node.lineno}")
    assert not ofensores, f"comando montado como string em {ofensores}"


# A checagem de flags de bypass no codigo-fonte vive em
# `test_plan_divergences.py`: hoje `plugin/api.py` oferece
# `permission_mode="bypassPermissions"`, entao ela e uma divergencia conhecida
# (xfail) e nao uma falha nova a cada execucao.


# Argv construido em tempo de execucao -----------------------------------


@pytest.mark.phase4
def test_argv_do_provedor_nao_tem_metacaractere_de_shell():
    providers = require_module("setup_spyder.plugin.providers", "provedores (Fase 4)")
    known = require_attr(providers, "KNOWN_PROVIDERS")
    for name, provider in known.items():
        for part in provider.argv:
            assert not SHELL_METACHARS.search(part), (
                f"{name}: argumento {part!r} parece linha de shell"
            )


@pytest.mark.phase4
def test_o_comando_do_agente_comeca_pelo_executavel_resolvido(fake_bin):
    providers = require_module("setup_spyder.plugin.providers", "provedores (Fase 4)")
    build = require_attr(providers, "build_command")
    executavel = fake_bin("codex")
    resolution = require_attr(providers, "resolve_provider")(requested="codex")

    command = build(resolution.provider)
    assert isinstance(command, list)
    assert all(isinstance(part, str) for part in command)
    resolvidos = [Path(part).resolve() for part in command if Path(part).exists()]
    assert executavel.resolve() in resolvidos, (
        "o comando tem de conter o caminho resolvido por shutil.which, "
        f"e nao o nome cru: {command}"
    )


@pytest.mark.phase4
def test_o_agente_nao_e_iniciado_atraves_de_um_shell(fake_bin):
    """Nem `sh -c`, nem `powershell -Command`.

    Ha uma excecao conhecida e estreita: no Windows, `codex`/`claude` costumam
    ser shims `.cmd` do npm, que o CreateProcess nao executa direto. Nesse caso
    o unico formato aceito e ``[cmd.exe, /c, <caminho do .cmd>, ...]`` - com o
    caminho como *argumento separado*, nunca interpolado numa linha de comando.
    """
    providers = require_module("setup_spyder.plugin.providers", "provedores (Fase 4)")
    build = require_attr(providers, "build_command")
    fake_bin("claude")
    resolution = require_attr(providers, "resolve_provider")(requested="claude")

    command = build(resolution.provider)
    cabeca = Path(command[0]).name.lower()

    if cabeca in {"cmd.exe", "cmd"}:
        assert command[1].lower() == "/c"
        assert Path(command[2]).suffix.lower() in {".cmd", ".bat"}
        assert all(not SHELL_METACHARS.search(part) for part in command[2:])
    else:
        assert cabeca not in {"sh", "bash", "powershell.exe", "pwsh", "wsl.exe"}
        assert command[1:2] != ["-c"]
