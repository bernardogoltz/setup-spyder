"""Resolucao de projeto/workdir e o processo-filho limpo (secoes 5.1 e 5.2).

Contrato exercitado::

    setup_spyder.launcher
        resolve_workdir(workdir=None, cwd=None) -> Path
        build_child_command(*, conf_dir, workdir, agent, autostart,
                            spyder_args=(), profile="ephemeral", hidden=(),
                            sem_estilo=False, seed_only=False
                            ) -> tuple[list[str], dict[str, str]]
        resolve_profile(workdir, *, conf_dir=None, ephemeral=False,
                        profile=None, keep_config=False) -> Profile
        ensure_spyproject(root) -> Path        # sem importar o Spyder

    setup_spyder.bootstrap
        split_bootstrap_argv(argv) -> (seed_only, conf_dir, spyder_argv)

`build_child_command` devolve o comando do bootstrap filho e o ambiente que
ele recebe. O plano exige que o processo principal *nao* importe a config do
Spyder: quem define ``SPYDER_CONFDIR`` e o pai, quem importa o Spyder e o
filho.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from helpers.pending import require_attr, require_module

pytestmark = [pytest.mark.unit, pytest.mark.phase2]


@pytest.fixture()
def launcher():
    return require_module("setup_spyder.launcher", "launcher separado (Fase 2)")


@pytest.fixture()
def resolve_workdir(launcher):
    return require_attr(launcher, "resolve_workdir")


@pytest.fixture()
def build_child_command(launcher):
    return require_attr(launcher, "build_child_command")


# Workdir ----------------------------------------------------------------


def test_sem_workdir_usa_o_diretorio_corrente(resolve_workdir, project_root):
    assert Path(resolve_workdir(cwd=project_root)) == project_root.resolve()


def test_workdir_relativo_e_resolvido_contra_o_cwd(resolve_workdir, project_root):
    resolved = resolve_workdir(workdir="src", cwd=project_root)
    assert Path(resolved) == (project_root / "src").resolve()


def test_workdir_sempre_absoluto_e_normalizado(resolve_workdir, project_root):
    resolved = Path(resolve_workdir(workdir="src/../src", cwd=project_root))
    assert resolved.is_absolute()
    assert ".." not in resolved.parts


def test_workdir_com_espaco_e_acento_sobrevive_intacto(
    resolve_workdir, awkward_project_root
):
    resolved = Path(resolve_workdir(workdir=awkward_project_root))
    assert resolved == awkward_project_root.resolve()
    assert resolved.is_dir()


def test_workdir_aceita_str_e_path(resolve_workdir, project_root):
    assert Path(resolve_workdir(workdir=str(project_root))) == Path(
        resolve_workdir(workdir=project_root)
    )


# Processo-filho ---------------------------------------------------------


@pytest.fixture()
def child(build_child_command, tmp_path, project_root):
    command, env = build_child_command(
        conf_dir=tmp_path / "perfil",
        workdir=project_root,
        agent="codex",
        autostart=True,
        spyder_args=["--debug-info", "verbose", "--multithread"],
    )
    return command, env


def test_o_filho_usa_o_mesmo_interpretador(child):
    command, _ = child
    assert command[0] == sys.executable, (
        "o Spyder tem de subir com o Python do .venv do projeto"
    )


def test_o_comando_e_uma_lista_de_argumentos(child):
    command, _ = child
    assert isinstance(command, list)
    assert all(isinstance(part, str) for part in command)


def test_o_ambiente_carrega_o_contexto_antes_de_importar_o_spyder(child, tmp_path):
    _, env = child
    assert env["SPYDER_CONFDIR"] == str(tmp_path / "perfil")
    assert env["SETUP_SPYDER_AGENT"] == "codex"
    assert "SETUP_SPYDER_WORKDIR" in env
    assert env["SETUP_SPYDER_AUTOSTART"] in {"0", "1"}


def test_o_ambiente_do_usuario_e_herdado(child):
    _, env = child
    herdadas = [k for k in os.environ if k in env and k.isupper()]
    assert herdadas, "o ambiente do usuario nao pode ser descartado"


def test_o_launcher_nao_limpa_as_variaveis_conda(build_child_command, tmp_path,
                                                 project_root, monkeypatch):
    """Secao 5.3: nao mexer na descoberta de ambientes sem um caso comprovado."""
    monkeypatch.setenv("CONDA_PREFIX", "/opt/conda/envs/demo")
    monkeypatch.setenv("CONDA_DEFAULT_ENV", "demo")
    _, env = build_child_command(
        conf_dir=tmp_path / "perfil", workdir=project_root, agent="none",
        autostart=False,
    )
    assert env.get("CONDA_PREFIX") == "/opt/conda/envs/demo"
    assert env.get("CONDA_DEFAULT_ENV") == "demo"


def test_os_argumentos_extras_chegam_na_ordem(child):
    command, _ = child
    posicoes = [
        command.index(arg)
        for arg in ("--debug-info", "verbose", "--multithread")
        if arg in command
    ]
    assert len(posicoes) == 3, f"argumentos extras sumiram de {command}"
    assert posicoes == sorted(posicoes)


def test_o_launcher_nao_desliga_os_web_widgets(child):
    command, _ = child
    assert "--no-web-widgets" not in command, (
        "secao 6: o painel depende de QWebEngineView"
    )


def test_perfil_efemero_pode_forcar_nova_instancia(build_child_command, tmp_path,
                                                   project_root):
    command, _ = build_child_command(
        conf_dir=tmp_path / "perfil", workdir=project_root, agent="none",
        autostart=False, profile="ephemeral",
    )
    assert "--new-instance" in command


def test_perfil_de_projeto_respeita_a_instancia_unica(build_child_command, tmp_path,
                                                      project_root):
    """Secao 5.3: nao forcar --new-instance sobre o mesmo diretorio de perfil."""
    command, _ = build_child_command(
        conf_dir=tmp_path / "perfil", workdir=project_root, agent="none",
        autostart=False, profile="project",
    )
    assert "--new-instance" not in command


def test_agente_desligado_nao_vaza_provedor_para_o_filho(build_child_command,
                                                         tmp_path, project_root):
    _, env = build_child_command(
        conf_dir=tmp_path / "perfil", workdir=project_root, agent="none",
        autostart=False,
    )
    assert env["SETUP_SPYDER_AGENT"] == "none"
    assert env["SETUP_SPYDER_AUTOSTART"] == "0"


def test_o_filho_roda_o_bootstrap_do_pacote(child):
    command, _ = child
    assert command[1:3] == ["-m", "setup_spyder.bootstrap"]


def test_o_filho_recebe_conf_dir_workdir_e_projeto(child, tmp_path, project_root):
    command, _ = child
    assert command[command.index("--conf-dir") + 1] == str(tmp_path / "perfil")
    assert command[command.index("-w") + 1] == str(project_root)
    assert command[command.index("-p") + 1] == str(project_root)


def test_o_filho_recebe_a_blocklist_do_painel_projetos(build_child_command, tmp_path,
                                                        project_root):
    _, env = build_child_command(
        conf_dir=tmp_path / "perfil", workdir=project_root, agent="none",
        autostart=False, hidden=[".venv", "dist"],
    )
    assert env["SETUP_SPYDER_HIDDEN"].split(os.pathsep) == [".venv", "dist"]


@pytest.mark.parametrize("sem_estilo, esperado", [(False, "1"), (True, "0")])
def test_o_filho_sabe_se_deve_semear_o_estilo(build_child_command, tmp_path,
                                              project_root, sem_estilo, esperado):
    _, env = build_child_command(
        conf_dir=tmp_path / "perfil", workdir=project_root, agent="none",
        autostart=False, sem_estilo=sem_estilo,
    )
    assert env["SETUP_SPYDER_SEED_STYLE"] == esperado


def test_agente_ausente_vira_auto_no_filho(build_child_command, tmp_path,
                                           project_root):
    _, env = build_child_command(
        conf_dir=tmp_path / "perfil", workdir=project_root, agent=None,
        autostart=True,
    )
    assert env["SETUP_SPYDER_AGENT"] == "auto"
    assert env["SETUP_SPYDER_AUTOSTART"] == "1"


def test_agente_desconhecido_e_recusado(build_child_command, tmp_path, project_root):
    with pytest.raises(ValueError):
        build_child_command(
            conf_dir=tmp_path / "perfil", workdir=project_root,
            agent="gpt-hipotetico", autostart=True,
        )


def test_no_launch_passa_pelo_filho_so_para_semear(build_child_command, tmp_path,
                                                   project_root):
    command, _ = build_child_command(
        conf_dir=tmp_path / "perfil", workdir=project_root, agent="none",
        autostart=False, seed_only=True,
    )
    assert "--seed-only" in command


def test_build_child_command_nao_toca_o_disco(build_child_command, tmp_path,
                                              project_root):
    conf_dir = tmp_path / "perfil-que-nao-existe"
    build_child_command(
        conf_dir=conf_dir, workdir=project_root, agent="codex", autostart=True,
    )
    assert not conf_dir.exists()


# Bootstrap (o lado do filho) ----------------------------------------------


@pytest.fixture()
def bootstrap():
    return require_module("setup_spyder.bootstrap", "bootstrap filho (Fase 2)")


def test_bootstrap_separa_a_propria_flag_do_argv_do_spyder(bootstrap):
    split = require_attr(bootstrap, "split_bootstrap_argv")
    seed_only, conf_dir, spyder_argv = split(
        ["--seed-only", "--conf-dir", "C:/perfil x", "--new-instance", "-w", "d",
         "-p", "d", "--debug-info", "verbose"]
    )
    assert seed_only is True
    assert conf_dir == "C:/perfil x"
    assert "--seed-only" not in spyder_argv
    assert spyder_argv == ["--conf-dir", "C:/perfil x", "--new-instance", "-w", "d",
                           "-p", "d", "--debug-info", "verbose"]


def test_bootstrap_sem_a_flag_mantem_o_argv_intacto(bootstrap):
    split = require_attr(bootstrap, "split_bootstrap_argv")
    argv = ["--conf-dir=/p", "-w", "d", "-p", "d"]
    seed_only, conf_dir, spyder_argv = split(argv)
    assert seed_only is False
    assert conf_dir == "/p"
    assert spyder_argv == argv


def test_bootstrap_nao_importa_o_spyder_ao_ser_importado(bootstrap):
    """Quem importa o Spyder e `bootstrap.main`, nunca o import do modulo."""
    fonte = Path(bootstrap.__file__).read_text(encoding="utf-8")
    topo = fonte.split("\ndef ", 1)[0]
    assert "from spyder" not in topo and "import spyder" not in topo


# `.spyproject` sem importar o Spyder --------------------------------------


def test_ensure_spyproject_cria_o_layout_do_spyder(launcher, project_root):
    ensure_spyproject = require_attr(launcher, "ensure_spyproject")
    spyproject = ensure_spyproject(project_root)
    config = spyproject / "config"
    for name in ("workspace.ini", "codestyle.ini", "vcs.ini", "encoding.ini"):
        assert (config / name).is_file(), name
    workspace = (config / "workspace.ini").read_text(encoding="utf-8")
    assert "project_type = 'empty-project-type'" in workspace
    assert "[main]\nversion = " in workspace


def test_ensure_spyproject_nao_sobrescreve_o_que_existe(launcher, project_root):
    ensure_spyproject = require_attr(launcher, "ensure_spyproject")
    ensure_spyproject(project_root)
    workspace = project_root / ".spyproject" / "config" / "workspace.ini"
    workspace.write_text("keep-me\n", encoding="utf-8")
    ensure_spyproject(project_root)
    assert workspace.read_text(encoding="utf-8") == "keep-me\n"


def test_ensure_spyproject_convive_com_o_perfil_dentro_do_spyproject(
    launcher, project_root
):
    """O perfil mora em `.spyproject/setup-spyder`; criar o perfil primeiro
    nao pode impedir a criacao do `config/` do projeto."""
    from setup_spyder.perfil import conf_dir_for

    conf_dir_for(project_root)
    ensure_spyproject = require_attr(launcher, "ensure_spyproject")
    ensure_spyproject(project_root)
    assert (project_root / ".spyproject" / "config" / "workspace.ini").is_file()


# Precedencia do perfil ------------------------------------------------------


@pytest.fixture()
def resolve_profile(launcher):
    return require_attr(launcher, "resolve_profile")


def test_o_padrao_e_o_perfil_de_projeto(resolve_profile, project_root):
    from setup_spyder.perfil import CONF_DIRNAME

    chosen = resolve_profile(project_root)
    assert chosen.kind == "project"
    assert chosen.path == project_root / CONF_DIRNAME
    assert chosen.delete_at_exit is False


def test_conf_dir_explicito_ganha_de_ephemeral(resolve_profile, project_root, tmp_path):
    chosen = resolve_profile(
        project_root, conf_dir=tmp_path / "meu perfil", ephemeral=True,
        profile="ephemeral",
    )
    assert chosen.kind == "custom"
    assert chosen.path == (tmp_path / "meu perfil").resolve()
    assert chosen.delete_at_exit is False


@pytest.mark.parametrize("kwargs", [{"ephemeral": True}, {"profile": "ephemeral"}])
def test_ephemeral_e_profile_ephemeral_sao_equivalentes(resolve_profile, project_root,
                                                        kwargs):
    chosen = resolve_profile(project_root, **kwargs)
    try:
        assert chosen.kind == "ephemeral"
        assert chosen.path.name.startswith("setup-spyder-conf-")
        assert chosen.delete_at_exit is True
    finally:
        chosen.path.rmdir()


def test_keep_config_so_vale_para_o_perfil_efemero(resolve_profile, project_root):
    efemero = resolve_profile(project_root, ephemeral=True, keep_config=True)
    efemero.path.rmdir()
    assert efemero.delete_at_exit is False
    projeto = resolve_profile(project_root, keep_config=True)
    assert projeto.delete_at_exit is False
