"""Perfis: resolucao, seed versionado e reset seguro (secoes 5.1 e 5.3).

A primeira metade congela o que `setup_spyder.perfil` ja faz hoje. A segunda
exercita o que o plano acrescenta:

    setup_spyder.perfil (ou setup_spyder.profile)
        SEED_VERSION: int
        seed_profile(conf_dir, *, version=SEED_VERSION) -> bool
        reset_profile(conf_dir, *, project_root=None) -> Path

`seed_profile` devolve ``True`` quando escreveu o seed e ``False`` quando o
perfil ja estava na versao corrente - e o "nao regravar preferencias em toda
inicializacao" da secao 5.3.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from helpers.pending import not_implemented, require_attr

pytestmark = [pytest.mark.unit]


@pytest.fixture()
def perfil():
    import setup_spyder.perfil as modulo

    return modulo


@pytest.fixture()
def perfil_novo(perfil):
    """O modulo que carrega o seed versionado do plano, onde quer que ele more."""
    import importlib

    for nome in ("setup_spyder.profile", "setup_spyder.perfil"):
        try:
            modulo = importlib.import_module(nome)
        except ImportError:
            continue
        if hasattr(modulo, "seed_profile"):
            return modulo
    not_implemented("seed versionado do perfil (secao 5.3, Fase 2)")


# Resolucao do diretorio (hoje) -----------------------------------------


@pytest.mark.phase0
def test_o_perfil_padrao_mora_dentro_do_projeto(perfil, project_root):
    conf_dir = perfil.conf_dir_for(project_root, ephemeral=False)
    assert conf_dir == project_root / perfil.CONF_DIRNAME
    assert conf_dir.is_dir()


@pytest.mark.phase0
def test_o_perfil_padrao_e_estavel_entre_chamadas(perfil, project_root):
    primeiro = perfil.conf_dir_for(project_root, ephemeral=False)
    segundo = perfil.conf_dir_for(project_root, ephemeral=False)
    assert primeiro == segundo


@pytest.mark.phase0
def test_o_perfil_efemero_fica_em_area_temporaria(perfil, project_root):
    conf_dir = perfil.conf_dir_for(project_root, ephemeral=True)
    temp_root = Path(tempfile.gettempdir()).resolve()
    assert temp_root in conf_dir.resolve().parents
    assert conf_dir.name.startswith("setup-spyder-conf-")
    conf_dir.rmdir()


@pytest.mark.phase0
def test_o_perfil_efemero_e_novo_a_cada_chamada(perfil, project_root):
    primeiro = perfil.conf_dir_for(project_root, ephemeral=True)
    segundo = perfil.conf_dir_for(project_root, ephemeral=True)
    assert primeiro != segundo
    primeiro.rmdir()
    segundo.rmdir()


@pytest.mark.phase0
def test_nenhum_dos_modos_aponta_para_a_config_global(perfil, project_root):
    global_conf = Path.home() / ".spyder-py3"
    for ephemeral in (False, True):
        conf_dir = perfil.conf_dir_for(project_root, ephemeral=ephemeral)
        assert conf_dir.resolve() != global_conf.resolve()
        assert global_conf.resolve() not in conf_dir.resolve().parents


@pytest.mark.phase0
def test_a_resolucao_aguenta_espaco_e_acento(perfil, awkward_project_root):
    conf_dir = perfil.conf_dir_for(awkward_project_root, ephemeral=False)
    assert conf_dir.is_absolute() and conf_dir.is_dir()
    assert "análise maçã" in str(conf_dir)


# Conteudo do perfil (hoje) ---------------------------------------------


@pytest.mark.phase0
def test_as_chaves_que_matam_popup_valem_com_e_sem_estilo(perfil):
    com = perfil.perfil_completo("Consolas", com_estilo=True)
    sem = perfil.perfil_completo("Consolas", com_estilo=False)
    for chave in perfil.POPUPS:
        assert com[chave] == perfil.POPUPS[chave]
        assert sem[chave] == perfil.POPUPS[chave]


@pytest.mark.phase0
def test_sem_estilo_nao_mexe_em_aparencia(perfil):
    sem = perfil.perfil_completo("Consolas", com_estilo=False)
    assert not [chave for chave in sem if chave[0] == "appearance"]


@pytest.mark.phase0
def test_a_fonte_e_gravada_como_lista_de_fallbacks(perfil):
    com = perfil.perfil_completo("Consolas", com_estilo=True)
    familia = com[("appearance", "font/family")]
    assert isinstance(familia, list)
    assert familia[0] == "Consolas"


@pytest.mark.phase0
def test_o_perfil_nao_liga_nenhum_bypass_de_permissao(perfil):
    """Criterio de aceitacao: nenhuma flag de bypass e adicionada implicitamente."""
    valores = perfil.perfil_completo("Consolas", com_estilo=True)
    texto = repr(valores).lower()
    for suspeita in ("bypasspermissions", "--yolo", "skip-permissions"):
        assert suspeita not in texto


# Seed versionado (plano) ------------------------------------------------


@pytest.mark.phase2
def test_seed_escreve_na_primeira_vez_e_nao_na_segunda(perfil_novo, tmp_path):
    seed_profile = require_attr(perfil_novo, "seed_profile")
    conf_dir = tmp_path / "perfil"

    assert seed_profile(conf_dir) is True, "o primeiro seed precisa escrever"
    assinatura = {
        path: path.stat().st_mtime_ns
        for path in sorted(conf_dir.rglob("*"))
        if path.is_file()
    }
    assert assinatura, "o seed nao criou nenhum arquivo"

    assert seed_profile(conf_dir) is False, (
        "secao 5.3: nao regravar preferencias em toda inicializacao"
    )
    depois = {
        path: path.stat().st_mtime_ns
        for path in sorted(conf_dir.rglob("*"))
        if path.is_file()
    }
    assert depois == assinatura


@pytest.mark.phase2
def test_seed_e_reaplicado_quando_a_versao_sobe(perfil_novo, tmp_path):
    seed_profile = require_attr(perfil_novo, "seed_profile")
    version = require_attr(perfil_novo, "SEED_VERSION")
    conf_dir = tmp_path / "perfil"

    assert seed_profile(conf_dir, version=version) is True
    assert seed_profile(conf_dir, version=version) is False
    assert seed_profile(conf_dir, version=version + 1) is True


@pytest.mark.phase2
def test_seed_preserva_ajuste_manual_de_chave_nao_semeada(perfil_novo, tmp_path):
    """Migrar versao nao pode zerar o perfil inteiro do usuario."""
    seed_profile = require_attr(perfil_novo, "seed_profile")
    version = require_attr(perfil_novo, "SEED_VERSION")
    conf_dir = tmp_path / "perfil"
    seed_profile(conf_dir, version=version)

    marca = conf_dir / "config" / "marca-do-usuario.txt"
    marca.parent.mkdir(parents=True, exist_ok=True)
    marca.write_text("nao me apague", encoding="utf-8")

    seed_profile(conf_dir, version=version + 1)
    assert marca.read_text(encoding="utf-8") == "nao me apague"


# Reset seguro (plano) ---------------------------------------------------


@pytest.mark.phase2
def test_reset_aceita_o_perfil_efemero_na_area_temporaria(perfil_novo, perfil):
    reset_profile = require_attr(perfil_novo, "reset_profile")
    conf_dir = perfil.conf_dir_for(Path("."), ephemeral=True)
    (conf_dir / "config").mkdir()
    (conf_dir / "config" / "spyder.ini").write_text("[main]\n", encoding="utf-8")
    try:
        devolvido = reset_profile(conf_dir)
        assert devolvido == conf_dir.resolve()
        assert conf_dir.is_dir()
        assert not (conf_dir / "config").exists()
    finally:
        conf_dir.rmdir()


@pytest.mark.phase2
def test_reset_de_diretorio_temporario_qualquer_e_recusado(perfil_novo):
    """So `setup-spyder-conf-*` direto na raiz temporaria pode ser apagado."""
    reset_profile = require_attr(perfil_novo, "reset_profile")
    outro = Path(tempfile.mkdtemp(prefix="outra-coisa-"))
    try:
        (outro / "importante.txt").write_text("nao me apague", encoding="utf-8")
        with pytest.raises(ValueError):
            reset_profile(outro)
        assert (outro / "importante.txt").exists()
    finally:
        (outro / "importante.txt").unlink()
        outro.rmdir()


@pytest.mark.phase2
def test_reset_recria_o_perfil_resolvido(perfil_novo, perfil, tmp_path):
    reset_profile = require_attr(perfil_novo, "reset_profile")
    projeto = tmp_path / "projeto"
    conf_dir = projeto / perfil.CONF_DIRNAME
    (conf_dir / "config").mkdir(parents=True)
    lixo = conf_dir / "config" / "spyder.ini"
    lixo.write_text("[main]\n", encoding="utf-8")

    reset_profile(conf_dir, project_root=projeto)
    assert conf_dir.is_dir()
    assert not lixo.exists()


@pytest.mark.phase2
@pytest.mark.parametrize(
    "alvo", ["home", "home_spyder", "raiz_do_projeto", "temp_root", "fora_do_projeto"]
)
def test_reset_recusa_caminho_fora_do_perfil_esperado(
    perfil_novo, tmp_path, project_root, alvo
):
    """"--reset-profile so remove/recria o perfil resolvido depois de validar
    que o caminho esta dentro do diretorio esperado" (secao 5.1)."""
    reset_profile = require_attr(perfil_novo, "reset_profile")
    alvos = {
        "home": Path.home(),
        "home_spyder": Path.home() / ".spyder-py3",
        "raiz_do_projeto": project_root,
        "temp_root": Path(tempfile.gettempdir()),
        "fora_do_projeto": tmp_path / "outro-lugar",
    }
    caminho = alvos[alvo]
    testemunha = None
    if alvo == "fora_do_projeto":
        caminho.mkdir(parents=True, exist_ok=True)
        testemunha = caminho / "importante.txt"
        testemunha.write_text("nao me apague", encoding="utf-8")
    # `~/.spyder-py3` so existe onde o Spyder ja rodou; num runner limpo nao
    # existe, e a recusa nao pode nem apagar nem criar o caminho.
    existia = caminho.exists()

    with pytest.raises((ValueError, PermissionError)):
        reset_profile(caminho, project_root=project_root)

    if existia:
        assert caminho.exists(), f"reset_profile apagou {caminho}"
    else:
        assert not caminho.exists(), f"reset_profile criou {caminho}"
    if testemunha is not None:
        assert testemunha.read_text(encoding="utf-8") == "nao me apague"


@pytest.mark.phase2
def test_reset_nao_segue_link_para_fora_do_projeto(
    perfil_novo, perfil, tmp_path, project_root
):
    reset_profile = require_attr(perfil_novo, "reset_profile")
    alvo = tmp_path / "fora"
    alvo.mkdir()
    (alvo / "importante.txt").write_text("nao me apague", encoding="utf-8")

    link = project_root / perfil.CONF_DIRNAME
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists():
        link.rmdir()
    _link_directory(alvo, link)

    with pytest.raises((ValueError, PermissionError)):
        reset_profile(link, project_root=project_root)
    assert (alvo / "importante.txt").exists()
    assert link.exists(), "o proprio link tambem nao pode ser removido"


def _link_directory(target: Path, link: Path) -> None:
    """Symlink, ou junction no Windows (nao exige privilegio)."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("sem permissao para criar symlink nesta maquina")
    import _winapi

    _winapi.CreateJunction(str(target), str(link))


@pytest.mark.phase2
def test_seed_grava_as_chaves_no_spyder_ini(perfil_novo, perfil, tmp_path):
    """O que o seed escreve tem de chegar ao `spyder.ini` que o Spyder le."""
    import configparser

    seed_profile = require_attr(perfil_novo, "seed_profile")
    conf_dir = tmp_path / "perfil"
    assert seed_profile(conf_dir, font_family="Consolas") is True

    ini = configparser.ConfigParser()
    ini.read(conf_dir / "config" / "spyder.ini", encoding="utf-8")
    assert ini["main_interpreter"]["default"] == "True"
    assert ini["main"]["check_updates_on_startup"] == "False"
    assert "show_internal_errors" not in dict(perfil.POPUPS)
    assert ini["editor"]["wrap"] == "True"
    assert "Consolas" in ini["appearance"]["font/family"]


@pytest.mark.phase2
def test_seed_sem_estilo_nao_mexe_em_aparencia(perfil_novo, tmp_path):
    import configparser

    seed_profile = require_attr(perfil_novo, "seed_profile")
    conf_dir = tmp_path / "perfil"
    assert seed_profile(conf_dir, font_family="Fonte Inventada", com_estilo=False) is True

    ini = configparser.ConfigParser()
    ini.read(conf_dir / "config" / "spyder.ini", encoding="utf-8")
    assert "Fonte Inventada" not in ini["appearance"].get("font/family", "")
    assert ini["main"]["check_updates_on_startup"] == "False"


@pytest.mark.phase2
def test_o_marcador_do_seed_registra_a_versao(perfil_novo, tmp_path):
    import json

    seed_profile = require_attr(perfil_novo, "seed_profile")
    version = require_attr(perfil_novo, "SEED_VERSION")
    conf_dir = tmp_path / "perfil"
    seed_profile(conf_dir, version=version)
    marcadores = [p for p in conf_dir.iterdir() if p.suffix == ".json"]
    assert len(marcadores) == 1
    assert json.loads(marcadores[0].read_text(encoding="utf-8"))["version"] == version


@pytest.mark.phase2
def test_o_perfil_de_projeto_nao_toca_a_config_global(
    perfil_novo, perfil, project_root, global_conf_guard
):
    seed_profile = require_attr(perfil_novo, "seed_profile")
    seed_profile(perfil.conf_dir_for(project_root, ephemeral=False))
