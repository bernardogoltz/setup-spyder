"""Onde o codigo contrariava o plano, ponto a ponto - agora resolvido.

Ate a Fase 2 estes testes eram `xfail`: decisoes ja tomadas no codigo que o
plano revisado desfazia. A migracao aconteceu (SDK fora, sem bypass, sem
monkeypatch global, sem limpar CONDA_*, seed versionado), entao hoje sao
asserts simples. Voltar a falhar aqui e regressao, nao divergencia.

Rode `pytest -m divergencia` para ver a lista com a secao do plano de cada um.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from helpers.pending import owning_distribution

pytestmark = [pytest.mark.unit, pytest.mark.divergencia]


@pytest.fixture(scope="module")
def fontes(setup_spyder):
    raiz = Path(setup_spyder.__file__).parent
    return sorted(p for p in raiz.rglob("*.py") if "tests" not in p.parts)


def _texto(fontes) -> str:
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in fontes)


# Secao 1 / 2.2 - o MVP nao e uma interface de chat sobre SDK ------------


def test_o_painel_nao_conversa_com_um_sdk_de_provedor(fontes):
    """Secao 2.2: 'SDK + widget de chat -> Nao usar no MVP'."""
    texto = _texto(fontes).lower()
    for sdk in ("claude_agent_sdk", "claudesdkclient", "claudeagentoptions"):
        assert sdk not in texto, f"{sdk} aparece no codigo do painel"


def test_a_selecao_do_editor_nao_e_enviada_sem_acao_do_usuario(fontes):
    """Secao 1 (fora do MVP): nada de enviar selecao do editor sozinho."""
    texto = _texto(fontes)
    assert "sig_editor_focus_changed" not in texto
    assert "set_editor_context" not in texto


def test_o_pacote_nao_depende_de_sdk_de_provedor():
    """Secao 4: 'Nao adicionar claude-agent-sdk nem SDK da OpenAI ao MVP'."""
    from importlib.metadata import requires

    declaradas = requires(owning_distribution()) or []
    texto = " ".join(declaradas).lower()
    for proibido in ("claude-agent-sdk", "anthropic", "openai"):
        assert proibido not in texto, f"o MVP nao deve depender de {proibido}"


# Secao 1 / 11 - nada de bypass implicito -------------------------------


def test_nenhum_modo_de_bypass_de_permissao_e_oferecido(fontes):
    """Criterio de aceitacao: 'Nenhuma flag de bypass e adicionada implicitamente'."""
    texto = _texto(fontes)
    for suspeita in ("bypassPermissions", "--dangerously-skip-permissions", "--yolo"):
        assert suspeita not in texto, f"{suspeita} aparece no codigo"


# Secao 7 - a campainha e preferencia, nao monkeypatch global -----------


def _reatribui_beep(node: ast.AST) -> bool:
    """`QApplication.beep = ...` ou `setattr(QApplication, "beep", ...)`.

    Chamar `QApplication.beep()` e a campainha legitima da secao 7; o que o
    plano proibe e trocar o metodo no processo inteiro.
    """
    alvos: list[ast.AST] = []
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        alvos = node.targets if isinstance(node, ast.Assign) else [node.target]
    for alvo in alvos:
        if isinstance(alvo, ast.Attribute) and alvo.attr == "beep":
            return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "setattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value == "beep"
    ):
        return True
    return False


def test_nao_ha_monkeypatch_global_de_qapplication_beep(fontes):
    """Secao 7: sem monkeypatch global de `QApplication.beep`."""
    ofensores = []
    for path in fontes:
        arvore = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        ofensores += [
            f"{path.name}:{node.lineno}"
            for node in ast.walk(arvore)
            if _reatribui_beep(node)
        ]
    assert not ofensores, f"QApplication.beep reatribuido em {ofensores}"


# Secao 8 - nao desabilitar avisos criticos globalmente -----------------


def test_erros_internos_e_avisos_de_dependencia_continuam_ligados(fontes):
    """Secao 8: 'Nao desabilitar globalmente caixas de erro, avisos de
    dependencia ou mensagens criticas'."""
    from setup_spyder.perfil import POPUPS

    assert POPUPS.get(("main", "show_internal_errors")) is not False
    assert "compute_dependencies" not in _texto(fontes)


# Secao 5.3 - nao mexer na descoberta de ambientes sem prova ------------


def test_o_launcher_nao_desmonta_a_descoberta_de_ambientes(fontes):
    """Secao 5.3: nao limpar `CONDA_*` nem anular a descoberta de conda."""
    texto = _texto(fontes)
    assert "strip_conda_env" not in texto
    assert "find_conda" not in texto
    assert "CONDA_ENV_VARS" not in texto


# Secao 5.3 - seed versionado, nao regravacao a cada boot ---------------


def test_o_perfil_nao_e_regravado_em_toda_inicializacao(setup_spyder):
    """Secao 5.3: seed versionado; o launcher nao grava o perfil a cada boot."""
    fonte = (Path(setup_spyder.__file__).parent / "launcher.py").read_text(
        encoding="utf-8"
    )
    arvore = ast.parse(fonte)
    chamadas = [
        node
        for node in ast.walk(arvore)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"apply_perfil", "seed_profile"}
    ]
    assert not chamadas, (
        "o launcher (processo pai) nao grava o perfil; isso e do bootstrap filho, "
        "que so escreve quando o seed esta ausente ou desatualizado"
    )


# Secao 2.4 - a faixa publicada e Spyder 5.x ----------------------------


def test_o_pacote_roda_sobre_spyder_5(spyder_available):
    """Este nao e divergencia: e o baseline da secao 2.4."""
    if not spyder_available:
        pytest.skip("Spyder nao esta instalado neste ambiente")
    import spyder

    assert spyder.__version__.startswith("5."), (
        f"a baseline de integracao e Spyder 5.x, nao {spyder.__version__}"
    )
