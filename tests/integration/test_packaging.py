"""Fase 6: o que precisa estar *dentro* do artefato.

Roda contra a distribuicao instalada por padrao. Apontando
``SETUP_SPYDER_WHEEL`` para um `.whl` construido, os mesmos testes inspecionam
o arquivo - que e o cenario que o plano pede ("testar wheel e sdist em
ambientes limpos, nao apenas instalacao editavel").
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from helpers.pending import not_implemented, owning_distribution

pytestmark = [pytest.mark.integration, pytest.mark.phase6]

ASSETS = ("terminal.html", "terminal.js", "xterm.js", "xterm.css")
CDN = ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com", "//cdn.")


class Artefato:
    """Vista unificada sobre uma wheel ou sobre o pacote instalado."""

    def __init__(self):
        self.wheel = os.environ.get("SETUP_SPYDER_WHEEL")

    def nomes(self) -> list[str]:
        if self.wheel:
            with zipfile.ZipFile(self.wheel) as zf:
                return zf.namelist()
        import setup_spyder

        raiz = Path(setup_spyder.__file__).parent
        return [
            str(p.relative_to(raiz.parent)).replace("\\", "/")
            for p in raiz.rglob("*")
            if p.is_file()
        ]

    def ler(self, sufixo: str) -> str:
        for nome in self.nomes():
            if nome.endswith(sufixo):
                if self.wheel:
                    with zipfile.ZipFile(self.wheel) as zf:
                        return zf.read(nome).decode("utf-8", "replace")
                import setup_spyder

                raiz = Path(setup_spyder.__file__).parent.parent
                return (raiz / nome).read_text(encoding="utf-8", errors="replace")
        return ""


@pytest.fixture(scope="module")
def artefato():
    return Artefato()


@pytest.mark.parametrize("asset", ASSETS)
def test_os_assets_web_viajam_no_artefato(artefato, asset):
    nomes = artefato.nomes()
    if not any("plugin/assets" in nome for nome in nomes):
        not_implemented("assets web do painel (Fase 3/6)")
    assert any(nome.endswith(f"plugin/assets/{asset}") for nome in nomes), (
        f"{asset} ficou de fora: {[n for n in nomes if 'assets' in n]}"
    )


def test_o_terminal_nao_carrega_javascript_de_cdn(artefato):
    """Secao 6.2: apenas assets empacotados localmente."""
    html = artefato.ler("plugin/assets/terminal.html")
    if not html:
        not_implemented("assets web do painel (Fase 3/6)")
    for host in CDN:
        assert host not in html, f"terminal.html busca script em {host}"
    assert "https://" not in html.replace("https://www.w3.org", ""), (
        "o painel nao deve buscar nada pela rede em tempo de execucao"
    )


def test_o_entry_point_do_plugin_esta_no_artefato(artefato):
    if artefato.wheel:
        texto = artefato.ler("entry_points.txt")
    else:
        from importlib.metadata import distribution

        texto = distribution(owning_distribution()).read_text("entry_points.txt") or ""
    if "setup_spyder_ai" not in texto:
        not_implemented(
            "entry point spyder.plugins:setup_spyder_ai na distribuicao (Fase 6)"
        )
    assert "[spyder.plugins]" in texto
    assert "setup_spyder.plugin.plugin:AITerminalPlugin" in texto.replace(" ", "")


def test_as_dependencias_de_pty_sao_condicionais_por_plataforma():
    from importlib.metadata import requires

    declaradas = requires(owning_distribution()) or []
    texto = " ".join(declaradas).lower()
    if "pywinpty" not in texto and "ptyprocess" not in texto:
        not_implemented("dependencias de PTY declaradas (Fase 6)")

    windows = [d for d in declaradas if "pywinpty" in d.lower()]
    posix = [d for d in declaradas if "ptyprocess" in d.lower()]
    assert windows and "platform_system" in windows[0], (
        f"pywinpty tem de ser condicional: {windows}"
    )
    assert posix and "platform_system" in posix[0], (
        f"ptyprocess tem de ser condicional: {posix}"
    )


def test_o_spyder_declarado_e_o_fork_pinado_no_github():
    """Secao 2.5: a dependencia publicada e `spyder @ git+https://github.com/
    bernardogoltz/spyder.git@<tag-ou-commit>` - nunca o `spyder` do PyPI, nunca
    um path local, nunca um branch flutuante."""
    import re
    from importlib.metadata import requires

    declaradas = requires(owning_distribution()) or []
    spyder = [d for d in declaradas if d.lower().startswith("spyder")]
    assert spyder, "a dependencia de spyder sumiu"
    req = spyder[0].replace(" ", "")
    assert "git+https://github.com/bernardogoltz/spyder" in req, (
        f"secao 2.5: o Spyder tem de vir do fork no GitHub, nao de {req}"
    )
    pin = re.search(r"\.git@([^#;\s]+)", req)
    assert pin, f"secao 2.5: a URL Git precisa de tag ou commit pinado: {req}"
    ref = pin.group(1)
    assert ref not in {"main", "master", "5.x", "HEAD"}, (
        f"secao 2.5: nunca um branch flutuante ({ref})"
    )
    assert "PLACEHOLDER" not in ref, "o pin do fork ainda nao foi preenchido"
    assert ">=5.5" not in req and "<6" not in req, (
        "a faixa do PyPI foi substituida pela URL Git; nao misturar as duas"
    )


def test_o_artefato_nao_aponta_para_o_fork_local():
    """Criterio de aceitacao: "O pacote nao contem caminho absoluto para o
    fork local"."""
    from importlib.metadata import distribution

    dist = distribution(owning_distribution())
    direct_url = dist.read_text("direct_url.json")
    if direct_url:
        assert '"editable": true' not in direct_url.replace(" ", ""), (
            f"instalacao editavel apontando para o fork: {direct_url}"
        )

    metadata = dist.read_text("METADATA") or ""
    for pista in ("file://", "C:\\Users", "/home/", "projetos\\spyder", "projetos/spyder"):
        assert pista not in metadata, f"caminho local vazou no METADATA: {pista}"


def test_o_pacote_nao_exige_conda():
    """Criterio de aceitacao: "O projeto nao exige Conda"."""
    from importlib.metadata import requires

    declaradas = " ".join(requires(owning_distribution()) or []).lower()
    assert "conda" not in declaradas
