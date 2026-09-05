"""Descoberta de `codex`/`claude` e precedencia de `--agent` (secao 6.3).

Contrato exercitado (ver README.md, "Contrato alvo")::

    setup_spyder.plugin.providers
        AgentProvider(name, executable, argv)
        KNOWN_PROVIDERS: mapping nome -> AgentProvider
        available_providers() -> tuple[AgentProvider, ...]
        resolve_provider(requested=None, preference=None) -> AgentResolution
        AgentResolution(provider, reason, candidates, requested, autostart)

`reason` e um de: ``explicit``, ``preference``, ``single``, ``ambiguous``,
``missing``, ``disabled``.

Todos os testes isolam o PATH (fixture `bin_dir`), entao o resultado nao
depende de o desenvolvedor ter as CLIs instaladas.
"""

from __future__ import annotations

import dataclasses
import shutil

import pytest

from helpers.pending import require_attr, require_module

pytestmark = [pytest.mark.unit, pytest.mark.phase4]


@pytest.fixture()
def providers():
    return require_module(
        "setup_spyder.plugin.providers", "resolucao de provedores (Fase 4)"
    )


@pytest.fixture()
def resolve(providers):
    return require_attr(providers, "resolve_provider")


# Sanidade do proprio arranjo de teste -----------------------------------


def test_o_path_de_teste_esta_realmente_isolado(bin_dir, fake_bin):
    assert shutil.which("codex") is None
    fake_bin("codex")
    assert shutil.which("codex") is not None
    assert shutil.which("claude") is None


# Descoberta -------------------------------------------------------------


def test_conhece_exatamente_codex_e_claude(providers):
    known = require_attr(providers, "KNOWN_PROVIDERS")
    assert set(known) == {"codex", "claude"}


def test_provider_e_imutavel_e_carrega_argv_como_tupla(providers):
    known = require_attr(providers, "KNOWN_PROVIDERS")
    provider = known["codex"]
    assert dataclasses.is_dataclass(provider)
    with pytest.raises(dataclasses.FrozenInstanceError):
        provider.name = "outro"
    assert isinstance(provider.argv, tuple)


def test_descoberta_usa_o_path_e_nao_caminhos_chutados(providers, fake_bin):
    available = require_attr(providers, "available_providers")
    assert available() == ()
    fake_bin("claude")
    assert [p.name for p in available()] == ["claude"]


# Precedencia ------------------------------------------------------------


def test_1_agent_explicito_vence_a_preferencia_salva(resolve, fake_bin):
    fake_bin("codex")
    fake_bin("claude")
    resolution = resolve(requested="codex", preference="claude")
    assert resolution.provider.name == "codex"
    assert resolution.reason == "explicit"
    assert resolution.autostart is True


def test_2_preferencia_salva_vale_quando_nao_ha_agent(resolve, fake_bin):
    fake_bin("codex")
    fake_bin("claude")
    resolution = resolve(requested=None, preference="claude")
    assert resolution.provider.name == "claude"
    assert resolution.reason == "preference"


def test_3_cli_unica_no_path_e_escolhida_sem_ambiguidade(resolve, fake_bin):
    fake_bin("codex")
    resolution = resolve()
    assert resolution.provider.name == "codex"
    assert resolution.reason == "single"
    assert resolution.autostart is True


def test_4_duas_clis_sem_preferencia_nao_iniciam_nada(resolve, fake_bin):
    fake_bin("codex")
    fake_bin("claude")
    resolution = resolve()
    assert resolution.provider is None, "ambiguidade nao pode iniciar uma CLI"
    assert resolution.reason == "ambiguous"
    assert resolution.autostart is False, (
        "secao 7: autostart desativado quando a escolha e ambigua"
    )
    assert {p.name for p in resolution.candidates} == {"codex", "claude"}


def test_5_nenhuma_cli_disponivel_nao_e_excecao(resolve, bin_dir):
    resolution = resolve()
    assert resolution.provider is None
    assert resolution.reason == "missing"
    assert resolution.candidates == ()


def test_agent_none_desliga_o_agente_mesmo_com_cli_instalada(resolve, fake_bin):
    fake_bin("codex")
    resolution = resolve(requested="none")
    assert resolution.provider is None
    assert resolution.reason == "disabled"
    assert resolution.autostart is False


def test_agent_auto_se_comporta_como_ausencia_de_pedido(resolve, fake_bin):
    fake_bin("claude")
    assert resolve(requested="auto").provider.name == "claude"


def test_agent_explicito_mas_ausente_do_path_degrada_sem_estourar(resolve, bin_dir):
    resolution = resolve(requested="codex")
    assert resolution.provider is None
    assert resolution.reason == "missing"
    assert resolution.requested == "codex", (
        "o painel precisa saber qual CLI o usuario pediu para instruir a instalacao"
    )


def test_preferencia_invalida_nao_derruba_a_resolucao(resolve, fake_bin):
    """Preferencia salva de uma versao antiga nao pode quebrar o painel."""
    fake_bin("codex")
    resolution = resolve(preference="provedor-que-nao-existe-mais")
    assert resolution.provider.name == "codex"
    assert resolution.reason in {"single", "preference"}


def test_agent_explicito_desconhecido_e_erro_de_programacao(resolve):
    with pytest.raises(ValueError):
        resolve(requested="gpt-hipotetico")
