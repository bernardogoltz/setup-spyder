"""O entry point `spyder.plugins` e o `NAME` do plugin (secao 4).

`spyder/app/find_plugins.py` levanta `SpyderAPIError` quando o nome do entry
point difere de `plugin_class.NAME`, e engole `ImportError` imprimindo em
STDERR - ou seja, um plugin com import quebrado simplesmente *some*. Estes
testes reproduzem as duas verificacoes fora do Spyder.

Duas camadas:

* o invariante vale para **qualquer** plugin que este pacote publique - e o que
  protege o `claude_code` de hoje e protegera o `setup_spyder_ai` de amanha;
* os testes marcados `phase3` exigem o plugin do plano, e pulam ate ele existir.
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points

import pytest

from helpers.pending import not_implemented, require_attr, require_module

pytestmark = [pytest.mark.unit]

NOME_ALVO = "setup_spyder_ai"
CLASSE_ALVO = "setup_spyder.plugin.plugin:AITerminalPlugin"


def _entry_points_do_pacote():
    """Entry points `spyder.plugins` publicados por esta distribuicao."""
    achados = []
    for ep in entry_points(group="spyder.plugins"):
        modulo = ep.value.split(":")[0]
        if modulo.startswith("setup_spyder"):
            achados.append(ep)
    return achados


@pytest.fixture(scope="module")
def plugins_do_pacote():
    achados = _entry_points_do_pacote()
    if not achados:
        not_implemented(
            "nenhum entry point spyder.plugins publicado por setup_spyder"
        )
    return achados


# Invariante do Spyder, para qualquer plugin nosso ----------------------


@pytest.mark.phase0
def test_o_modulo_de_cada_plugin_importa(plugins_do_pacote):
    """Um ImportError aqui vira um plugin invisivel no Spyder, nao um erro."""
    for ep in plugins_do_pacote:
        modulo = importlib.import_module(ep.module)
        assert getattr(modulo, ep.attr, None) is not None, (
            f"{ep.value}: a classe nao existe no modulo"
        )


@pytest.mark.phase0
def test_o_nome_do_entry_point_e_igual_ao_name_da_classe(plugins_do_pacote):
    for ep in plugins_do_pacote:
        plugin_class = getattr(importlib.import_module(ep.module), ep.attr)
        assert plugin_class.NAME == ep.name, (
            "find_external_plugins() levanta SpyderAPIError quando o nome do "
            f"entry point ({ep.name!r}) e plugin.NAME ({plugin_class.NAME!r}) "
            "divergem"
        )


@pytest.mark.phase0
def test_o_name_nao_colide_com_plugin_interno_do_spyder(
    plugins_do_pacote, spyder_available
):
    if not spyder_available:
        pytest.skip("Spyder nao esta instalado neste ambiente")
    from spyder.api.plugins import Plugins
    from spyder.api.utils import get_class_values

    internos = get_class_values(Plugins)
    for ep in plugins_do_pacote:
        assert ep.name not in internos, (
            f"{ep.name!r} colide com um plugin interno: o Spyder trata o "
            "plugin como interno e ignora o externo"
        )


@pytest.mark.phase0
def test_cada_plugin_declara_config_propria(plugins_do_pacote):
    for ep in plugins_do_pacote:
        plugin_class = getattr(importlib.import_module(ep.module), ep.attr)
        assert plugin_class.CONF_FILE is True, f"{ep.name}: falta CONF_FILE"
        assert getattr(plugin_class, "CONF_DEFAULTS", None), (
            f"{ep.name}: falta CONF_DEFAULTS"
        )
        assert isinstance(getattr(plugin_class, "CONF_VERSION", None), str), (
            f"{ep.name}: falta CONF_VERSION"
        )


# O plugin do plano ------------------------------------------------------


@pytest.fixture()
def plugin_entry_point():
    achados = {ep.name: ep for ep in entry_points(group="spyder.plugins")}
    if NOME_ALVO not in achados:
        not_implemented(
            f"entry point spyder.plugins:{NOME_ALVO} "
            f"(publicados por setup_spyder: "
            f"{[ep.name for ep in _entry_points_do_pacote()]})"
        )
    return achados[NOME_ALVO]


@pytest.mark.phase3
def test_o_entry_point_aponta_para_a_classe_do_plano(plugin_entry_point):
    assert plugin_entry_point.value.replace(" ", "") == CLASSE_ALVO


@pytest.mark.phase3
def test_o_plugin_vem_da_distribuicao_deste_pacote(plugin_entry_point):
    """Secao 2.1: o plugin viaja na mesma wheel do `setup-spyder`."""
    assert "spyder" in plugin_entry_point.dist.name.lower()


@pytest.fixture()
def plugin_class():
    module = require_module("setup_spyder.plugin.plugin", "plugin do painel")
    return require_attr(module, "AITerminalPlugin", "AITerminalPlugin (Fase 3)")


@pytest.mark.phase3
def test_a_classe_declara_o_name_esperado(plugin_class):
    assert plugin_class.NAME == NOME_ALVO


@pytest.mark.phase3
def test_a_classe_declara_o_grafo_de_dependencias_do_plano(plugin_class):
    if not importlib.util.find_spec("spyder"):
        pytest.skip("Spyder nao esta instalado neste ambiente")
    from spyder.api.plugins import Plugins

    assert Plugins.Preferences in plugin_class.REQUIRES
    assert set(plugin_class.OPTIONAL) >= {
        Plugins.Editor,
        Plugins.Projects,
        Plugins.WorkingDirectory,
        Plugins.MainMenu,
    }
    assert Plugins.IPythonConsole in plugin_class.TABIFY


@pytest.mark.phase3
def test_o_plugin_pede_web_widgets(plugin_class):
    """Secao 6: o painel depende de QWebEngineView."""
    assert getattr(plugin_class, "REQUIRE_WEB_WIDGETS", False) is True


@pytest.mark.phase3
def test_importar_o_plugin_nao_importa_o_backend_de_pty(plugin_class):
    """Secao 6.1: import tardio, senao uma dependencia opcional ausente faz o
    plugin sumir durante a descoberta."""
    del plugin_class
    codigo = (
        "import sys;"
        "import setup_spyder.plugin.plugin;"
        "print([m for m in ('winpty', 'ptyprocess', 'pexpect') if m in sys.modules])"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, encoding="utf-8", errors="replace", timeout=300
    )
    assert saida.returncode == 0, saida.stderr
    assert saida.stdout.strip().endswith("[]"), (
        f"backend de PTY importado cedo demais: {saida.stdout.strip()}"
    )


# Frente nativa vs fork: o painel so carrega na instancia -----------------


@pytest.mark.phase3
def test_a_instancia_do_fork_fica_desligada_sem_a_env(monkeypatch):
    from setup_spyder.plugin.api import fork_instance_enabled

    monkeypatch.delenv("SETUP_SPYDER_FORK", raising=False)
    assert fork_instance_enabled() is False
    monkeypatch.setenv("SETUP_SPYDER_FORK", "0")
    assert fork_instance_enabled() is False


@pytest.mark.phase3
@pytest.mark.parametrize("valor", ["1", "true", "YES", "on"])
def test_a_instancia_do_fork_liga_com_a_env(monkeypatch, valor):
    from setup_spyder.plugin.api import fork_instance_enabled

    monkeypatch.setenv("SETUP_SPYDER_FORK", valor)
    assert fork_instance_enabled() is True


@pytest.mark.phase3
def test_check_compatibility_recusa_sem_a_env_do_fork(plugin_class, monkeypatch):
    monkeypatch.delenv("SETUP_SPYDER_FORK", raising=False)
    plugin = plugin_class.__new__(plugin_class)
    valid, message = plugin.check_compatibility()
    assert valid is False
    assert "setup-spyder-fork" in message


@pytest.mark.phase3
def test_check_compatibility_aceita_com_a_env_do_fork(plugin_class, monkeypatch):
    monkeypatch.setenv("SETUP_SPYDER_FORK", "1")
    plugin = plugin_class.__new__(plugin_class)
    valid, message = plugin.check_compatibility()
    assert valid is True
    assert message == ""
