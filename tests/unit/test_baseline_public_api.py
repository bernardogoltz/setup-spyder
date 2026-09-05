"""Fase 0 - congela os contratos publicos atuais de `setup_spyder`.

Estes testes rodam contra o pacote como ele esta hoje (`setup_spyder/` neste
checkout, versao 0.1.0) e **nao devem pular**. Eles existem para que a
refatoracao da Fase 2 (`cli.py` / `launcher.py` / `profile.py`) nao quebre quem
ja importa o pacote:

    from setup_spyder import launch
    launch()

O plano (secao 2.1) e explicito: "A evolucao deve manter esses contratos".

Onde o plano manda *acrescentar* opcao (`--agent`, `--profile`), o teste da
opcao nova mora em `test_cli_arguments.py`. Aqui so fica o que ja existe.
"""

from __future__ import annotations

import inspect
import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.phase0]


# Superficie importavel --------------------------------------------------


def test_exporta_launch_main_e_open_spyder(setup_spyder):
    for name in ("launch", "launch_fork", "main", "open_spyder", "__version__"):
        assert hasattr(setup_spyder, name), f"setup_spyder.{name} sumiu"
    assert set(setup_spyder.__all__) >= {
        "__version__",
        "launch",
        "launch_fork",
        "main",
        "open_spyder",
    }


def test_open_spyder_continua_sendo_alias_de_launch(setup_spyder):
    assert setup_spyder.open_spyder is setup_spyder.launch


def test_versao_e_uma_string_com_pontos(setup_spyder):
    assert isinstance(setup_spyder.__version__, str)
    assert setup_spyder.__version__.count(".") >= 2


# Assinatura de `launch` -------------------------------------------------

#: Opcoes que `launch()` aceita hoje, com o default de cada uma.
LAUNCH_KEYWORDS = {
    "no_launch": False,
    "keep_config": False,
    "ephemeral": False,
    "sem_estilo": False,
    "workdir": None,
    "conf_dir": None,
    "hide": (),
    "show": (),
}


def test_launch_mantem_o_primeiro_parametro_posicional(setup_spyder):
    parameters = list(inspect.signature(setup_spyder.launch).parameters.values())
    first = parameters[0]
    assert first.name == "spyder_args"
    assert first.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert first.default == ()


@pytest.mark.parametrize("name, default", sorted(LAUNCH_KEYWORDS.items()))
def test_launch_mantem_cada_opcao_atual(setup_spyder, name, default):
    parameters = inspect.signature(setup_spyder.launch).parameters
    assert name in parameters, f"launch() perdeu a opcao {name!r}"
    assert parameters[name].default == default


def test_parametros_novos_de_launch_sao_keyword_only_com_default(setup_spyder):
    """Qualquer opcao nova (`agent`, `profile`, `conf_dir`...) tem de ser
    opcional e nomeada, senao `launch()` sem argumentos deixa de funcionar."""
    parameters = list(inspect.signature(setup_spyder.launch).parameters.values())
    for parameter in parameters[1:]:
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{parameter.name} precisa ser keyword-only"
        )
        assert parameter.default is not inspect.Parameter.empty, (
            f"{parameter.name} precisa ter valor padrao"
        )


def test_main_aceita_argv_opcional_e_devolve_int(setup_spyder):
    parameters = inspect.signature(setup_spyder.main).parameters
    assert list(parameters) == ["argv"]
    assert parameters["argv"].default is None


def test_o_cli_delega_para_o_launcher(setup_spyder_cli):
    """Secao 9 (Fase 2): `cli.py` e `launcher.py` sao camadas separadas."""
    import setup_spyder.launcher as launcher

    assert setup_spyder_cli._launch is launcher.launch_native


def test_o_fork_delega_para_o_launcher(setup_spyder_fork):
    import setup_spyder.launcher as launcher

    assert setup_spyder_fork._launch is launcher.launch


# Camadas do pacote ------------------------------------------------------


@pytest.mark.parametrize(
    "modulo, funcao",
    [
        ("setup_spyder.launcher", "launch"),
        ("setup_spyder.launcher", "launch_native"),
        ("setup_spyder.perfil", "conf_dir_for"),
        ("setup_spyder.perfil", "resolve_hidden_paths"),
        ("setup_spyder.patches", "render_launcher"),
    ],
)
def test_as_camadas_atuais_continuam_no_lugar(modulo, funcao):
    import importlib

    assert callable(getattr(importlib.import_module(modulo), funcao))


# Ponto de entrada de console -------------------------------------------


def test_o_console_script_continua_registrado():
    found = {ep.name: ep.value for ep in entry_points(group="console_scripts")}
    assert "setup-spyder" in found, "o console_script setup-spyder sumiu"
    assert found["setup-spyder"] == "setup_spyder.cli:main"
    assert "setup-spyder-fork" in found, "o console_script setup-spyder-fork sumiu"
    assert found["setup-spyder-fork"] == "setup_spyder.fork:main"
