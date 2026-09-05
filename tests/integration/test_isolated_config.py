"""Configuracao isolada de verdade: `--no-launch` num HOME descartavel.

Estes testes rodam o `setup-spyder` como subprocesso, sem abrir janela, e
verificam os criterios de aceitacao "nao gravar em `~/.spyder-py3`" e "o
perfil do projeto nao sobrescreve preferencias em toda inicializacao".

Sao lentos: cada execucao importa o Spyder inteiro.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from helpers.pending import child_env, not_implemented

pytestmark = [pytest.mark.integration, pytest.mark.slow]

#: `.spyder-py3` numa versao estavel, `.spyder-py3-dev` no fork (5.6.0.dev0).
GLOBAL_CONF_DIRNAMES = (".spyder-py3", ".spyder-py3-dev")


def global_conf_created(home) -> list:
    return [name for name in GLOBAL_CONF_DIRNAMES if (home / name).exists()]


def rodar(argv, *, home, cwd=None, timeout=600):
    return subprocess.run(
        [sys.executable, "-m", "setup_spyder", *argv],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(home),
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
    )


@pytest.fixture(autouse=True)
def _exige_spyder(spyder_available):
    if not spyder_available:
        pytest.skip("Spyder nao esta instalado neste ambiente")


@pytest.mark.phase0
def test_no_launch_configura_e_sai_com_zero(isolated_home, project_root):
    resultado = rodar(["--no-launch", "-w", str(project_root)], home=isolated_home)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


@pytest.mark.phase0
def test_no_launch_nao_cria_a_config_global(isolated_home, project_root):
    rodar(["--no-launch", "-w", str(project_root)], home=isolated_home)
    assert not global_conf_created(isolated_home), (
        "criterio de aceitacao: a config global do usuario fica intacta"
    )


@pytest.mark.phase0
def test_no_launch_cria_o_spyproject_no_repositorio(isolated_home, project_root):
    rodar(["--no-launch", "-w", str(project_root)], home=isolated_home)
    assert (project_root / ".spyproject").is_dir()


@pytest.mark.phase0
def test_o_perfil_padrao_fica_dentro_do_projeto(isolated_home, project_root):
    from setup_spyder.perfil import CONF_DIRNAME

    rodar(["--no-launch", "-w", str(project_root)], home=isolated_home)
    assert (project_root / CONF_DIRNAME / "config" / "spyder.ini").is_file()


@pytest.mark.phase0
def test_ephemeral_nao_escreve_no_projeto(isolated_home, project_root):
    """Secao 5.1: o perfil efemero vive num diretorio temporario exclusivo."""
    from setup_spyder.perfil import CONF_DIRNAME

    resultado = rodar(
        ["--no-launch", "--ephemeral", "-w", str(project_root)], home=isolated_home
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert not (project_root / CONF_DIRNAME).exists()


@pytest.mark.phase0
def test_conf_dir_explicito_tem_precedencia(isolated_home, project_root, tmp_path):
    """Secao 5.1: "--conf-dir tem precedencia explicita sobre os dois modos"."""
    from setup_spyder.perfil import CONF_DIRNAME

    escolhido = tmp_path / "perfil escolhido"
    resultado = rodar(
        ["--no-launch", "--conf-dir", str(escolhido), "-w", str(project_root)],
        home=isolated_home,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert (escolhido / "config" / "spyder.ini").is_file()
    assert not (project_root / CONF_DIRNAME).exists()


@pytest.mark.phase0
def test_o_perfil_manda_o_spyder_usar_o_interpretador_corrente(
    isolated_home, project_root
):
    """E assim que o kernel acaba no Python do projeto: `main_interpreter/default`
    ligado faz o Spyder usar o interpretador que o iniciou, em vez de um env
    escolhido a parte."""
    import configparser

    from setup_spyder.perfil import CONF_DIRNAME

    rodar(["--no-launch", "-w", str(project_root)], home=isolated_home)
    ini = configparser.ConfigParser()
    ini.read(project_root / CONF_DIRNAME / "config" / "spyder.ini", encoding="utf-8")
    assert ini["main_interpreter"]["default"] == "True"
    assert ini["main_interpreter"]["custom"] == "False"


@pytest.mark.phase0
def test_funciona_com_espaco_e_acento_no_caminho(isolated_home, awkward_project_root):
    resultado = rodar(
        ["--no-launch", "-w", str(awkward_project_root)], home=isolated_home
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert (awkward_project_root / ".spyproject").is_dir()




# Perfil de projeto (Fase 2) --------------------------------------------


def _rodar_perfil_projeto(home, project_root):
    resultado = rodar(
        ["--no-launch", "--profile", "project", "-w", str(project_root)], home=home
    )
    if resultado.returncode != 0 and "--profile" in resultado.stderr:
        not_implemented("--profile project (Fase 2)")
    return resultado


@pytest.mark.phase2
def test_o_perfil_de_projeto_persiste_entre_execucoes(isolated_home, project_root):
    _rodar_perfil_projeto(isolated_home, project_root)
    perfil = project_root / ".spyproject" / "setup-spyder"
    assert perfil.is_dir(), "o perfil de projeto nao foi criado"

    assinatura = {
        p.name: p.stat().st_mtime_ns for p in sorted(perfil.rglob("*")) if p.is_file()
    }
    _rodar_perfil_projeto(isolated_home, project_root)
    depois = {
        p.name: p.stat().st_mtime_ns for p in sorted(perfil.rglob("*")) if p.is_file()
    }
    assert depois == assinatura, (
        "criterio de aceitacao: o perfil do projeto nao sobrescreve "
        f"preferencias em toda inicializacao. Mudou: "
        f"{sorted(set(depois.items()) ^ set(assinatura.items()))}"
    )


@pytest.mark.phase2
def test_dois_projetos_tem_perfis_distintos(
    isolated_home, project_root, awkward_project_root
):
    _rodar_perfil_projeto(isolated_home, project_root)
    _rodar_perfil_projeto(isolated_home, awkward_project_root)
    primeiro = project_root / ".spyproject" / "setup-spyder"
    segundo = awkward_project_root / ".spyproject" / "setup-spyder"
    assert primeiro.is_dir() and segundo.is_dir()
    assert primeiro != segundo


@pytest.mark.phase2
def test_o_perfil_de_projeto_tambem_nao_toca_o_home(isolated_home, project_root):
    _rodar_perfil_projeto(isolated_home, project_root)
    assert not global_conf_created(isolated_home)


@pytest.mark.phase2
def test_reset_profile_recria_o_perfil_de_projeto(isolated_home, project_root):
    from setup_spyder.perfil import CONF_DIRNAME

    _rodar_perfil_projeto(isolated_home, project_root)
    lixo = project_root / CONF_DIRNAME / "config" / "lixo.txt"
    lixo.write_text("apague-me", encoding="utf-8")

    resultado = rodar(
        ["--no-launch", "--profile", "project", "--reset-profile", "-w",
         str(project_root)],
        home=isolated_home,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert not lixo.exists()
    assert (project_root / CONF_DIRNAME / "config" / "spyder.ini").is_file()


@pytest.mark.phase2
def test_reset_profile_recusa_conf_dir_arbitrario(isolated_home, project_root, tmp_path):
    escolhido = tmp_path / "perfil escolhido"
    (escolhido / "config").mkdir(parents=True)
    testemunha = escolhido / "config" / "importante.txt"
    testemunha.write_text("nao me apague", encoding="utf-8")

    resultado = rodar(
        ["--no-launch", "--conf-dir", str(escolhido), "--reset-profile", "-w",
         str(project_root)],
        home=isolated_home,
    )
    assert resultado.returncode == 1
    assert testemunha.read_text(encoding="utf-8") == "nao me apague"


@pytest.mark.phase2
def test_ephemeral_e_apagado_ao_sair_salvo_keep_config(isolated_home, project_root):
    import re

    padrao = re.compile(r"Profile \(ephemeral\): (.+)")
    resultado = rodar(
        ["--no-launch", "--ephemeral", "-w", str(project_root)], home=isolated_home
    )
    caminho = padrao.search(resultado.stdout)
    assert caminho, resultado.stdout
    assert not Path(caminho.group(1).strip()).exists()

    resultado = rodar(
        ["--no-launch", "--ephemeral", "--keep-config", "-w", str(project_root)],
        home=isolated_home,
    )
    caminho = padrao.search(resultado.stdout)
    assert caminho, resultado.stdout
    mantido = Path(caminho.group(1).strip())
    assert (mantido / "config" / "spyder.ini").is_file()
    shutil.rmtree(mantido, ignore_errors=True)
