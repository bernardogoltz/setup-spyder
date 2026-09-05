"""Argumentos da CLI: frente nativa (`setup-spyder`) e fork (`setup-spyder-fork`).

A frente nativa so configura o projeto e abre o Spyder como modulo. Agent,
perfil efemero, hide/show e --conf-dir ficam em `setup-spyder-fork`.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from helpers.pending import not_implemented

pytestmark = [pytest.mark.unit]


def parse(cli, argv):
    return cli.parse_args(argv)


def parse_or_pending(cli, argv, what):
    """Faz o parse; se o argparse rejeitar a opcao, e entrega pendente."""
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return cli.parse_args(argv)
    except SystemExit:
        not_implemented(f"{what} (argparse recusou {argv!r})")


# Frente nativa (`setup-spyder`) ------------------------------------------


@pytest.mark.phase0
def test_sem_argumentos_usa_os_defaults_nativos(setup_spyder_cli):
    args = parse(setup_spyder_cli, [])
    assert args.no_launch is False
    assert args.sem_estilo is False
    assert args.workdir is None
    assert args.reset_profile is False
    assert args.spyder_args == []
    assert not hasattr(args, "agent")
    assert not hasattr(args, "ephemeral")


@pytest.mark.phase0
@pytest.mark.parametrize(
    "flag, atributo",
    [
        ("--no-launch", "no_launch"),
        ("--sem-estilo", "sem_estilo"),
        ("--reset-profile", "reset_profile"),
    ],
)
def test_flags_nativas_continuam_existindo(setup_spyder_cli, flag, atributo):
    assert getattr(parse(setup_spyder_cli, [flag]), atributo) is True


@pytest.mark.phase0
@pytest.mark.parametrize("flag", ["-w", "--workdir"])
def test_workdir_aceita_forma_curta_e_longa(setup_spyder_cli, flag, tmp_path):
    args = parse(setup_spyder_cli, [flag, str(tmp_path)])
    assert args.workdir == str(tmp_path)


@pytest.mark.phase0
def test_argumentos_extras_vao_para_o_spyder_na_ordem(setup_spyder_cli):
    args = parse(setup_spyder_cli, ["--", "--debug-info", "minimal", "--multithread"])
    forwarded = [a for a in args.spyder_args if a != "--"]
    assert forwarded == ["--debug-info", "minimal", "--multithread"]


@pytest.mark.phase0
@pytest.mark.parametrize(
    "spyder_flag", ["--defaults", "--reset", "--safe-mode", "--new-instance"]
)
def test_o_parser_nao_reclama_de_flags_do_spyder(setup_spyder_cli, spyder_flag):
    """`spyder_args` tem de continuar sendo REMAINDER: flags do Spyder passam
    inteiras, sem virar erro de uso do `setup-spyder`."""
    args = parse(setup_spyder_cli, ["--", spyder_flag])
    assert spyder_flag in args.spyder_args


@pytest.mark.phase0
def test_argumento_desconhecido_ainda_e_erro_de_uso(setup_spyder_cli):
    with contextlib.redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit) as excinfo:
            setup_spyder_cli.parse_args(["--nao-existe"])
    assert excinfo.value.code == 2


@pytest.mark.phase0
@pytest.mark.parametrize("flag", ["--agent", "--ephemeral", "--conf-dir", "--hide", "--show", "--profile"])
def test_flags_do_fork_sao_erro_na_frente_nativa(setup_spyder_cli, flag):
    argv = [flag] if flag != "--conf-dir" and flag != "--profile" and flag != "--agent" else [flag, "x"]
    if flag == "--agent":
        argv = ["--agent", "codex"]
    elif flag == "--profile":
        argv = ["--profile", "project"]
    elif flag == "--conf-dir":
        argv = ["--conf-dir", "/tmp"]
    elif flag in {"--hide", "--show"}:
        argv = [flag, ".github"]
    with contextlib.redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit) as excinfo:
            setup_spyder_cli.parse_args(argv)
    assert excinfo.value.code == 2


@pytest.mark.phase0
def test_main_repassa_as_opcoes_nativas_para_launch(setup_spyder_cli, monkeypatch,
                                                    tmp_path):
    """Nenhuma opcao nativa pode ficar orfa entre `parse_args` e `launch`."""
    recebidos = {}
    monkeypatch.setattr(
        setup_spyder_cli,
        "launch",
        lambda *args, **kwargs: recebidos.update(kwargs) or 0,
    )
    setup_spyder_cli.main(
        [
            "--no-launch",
            "--sem-estilo",
            "-w",
            str(tmp_path),
            "--reset-profile",
        ]
    )
    assert recebidos["no_launch"] is True
    assert recebidos["sem_estilo"] is True
    assert recebidos["workdir"] == str(tmp_path)
    assert recebidos["reset_profile"] is True
    assert "agent" not in recebidos


@pytest.mark.phase2
def test_o_cli_repassa_tudo_ao_launcher_nativo(setup_spyder_cli, monkeypatch, tmp_path):
    """`cli.launch` so imprime o banner e delega para `launch_native`."""
    recebidos = {}
    monkeypatch.setattr(
        setup_spyder_cli,
        "_launch",
        lambda *args, **kwargs: recebidos.update(kwargs) or 0,
    )
    code = setup_spyder_cli.launch(
        ["--debug-info", "minimal"],
        no_launch=True,
        workdir=tmp_path,
        reset_profile=True,
        sem_estilo=True,
    )
    assert code == 0
    assert recebidos["workdir"] == tmp_path.resolve()
    assert recebidos["reset_profile"] is True
    assert recebidos["sem_estilo"] is True
    assert recebidos["no_launch"] is True
    assert "agent" not in recebidos


@pytest.mark.phase2
def test_launch_com_agent_delega_para_o_fork(setup_spyder_cli, monkeypatch, tmp_path):
    recebidos = {}
    monkeypatch.setattr(
        "setup_spyder.fork.launch",
        lambda *args, **kwargs: recebidos.update(kwargs) or 0,
    )
    setup_spyder_cli.launch(workdir=tmp_path, agent="codex")
    assert recebidos["agent"] == "codex"
    assert recebidos["workdir"] == tmp_path


# Blocklist do painel Projetos (ainda no perfil, usada pelo fork) ---------


@pytest.mark.phase0
def test_resolve_hidden_paths_soma_hide_e_subtrai_show():
    from setup_spyder.perfil import HIDDEN_PATHS, resolve_hidden_paths

    resolved = resolve_hidden_paths(hide=["segredo, outro"], show=[".github"])
    assert "segredo" in resolved and "outro" in resolved
    assert ".github" not in resolved
    assert ".venv" in resolved  # continua vindo dos defaults
    assert set(resolved) <= set(HIDDEN_PATHS) | {"segredo", "outro"}
    assert resolved == sorted(resolved), "a lista precisa ser deterministica"


@pytest.mark.phase0
def test_resolve_hidden_paths_ignora_entradas_vazias():
    from setup_spyder.perfil import HIDDEN_PATHS, resolve_hidden_paths

    resolved = resolve_hidden_paths(hide=[" , ,"], show=[""])
    assert "" not in resolved
    assert set(resolved) == set(HIDDEN_PATHS)


@pytest.mark.phase0
def test_o_proprio_diretorio_de_config_fica_oculto():
    from setup_spyder.perfil import CONF_DIRNAME, resolve_hidden_paths

    assert CONF_DIRNAME in resolve_hidden_paths()


# Frente fork (`setup-spyder-fork`) ---------------------------------------


@pytest.mark.phase0
def test_fork_sem_argumentos_usa_os_defaults_atuais(setup_spyder_fork):
    args = parse(setup_spyder_fork, [])
    assert args.no_launch is False
    assert args.keep_config is False
    assert args.ephemeral is False
    assert args.sem_estilo is False
    assert args.workdir is None
    assert args.conf_dir is None
    assert args.hide == []
    assert args.show == []
    assert args.spyder_args == []


@pytest.mark.phase0
@pytest.mark.parametrize(
    "flag, atributo",
    [
        ("--no-launch", "no_launch"),
        ("--keep-config", "keep_config"),
        ("--ephemeral", "ephemeral"),
        ("--sem-estilo", "sem_estilo"),
    ],
)
def test_flags_booleanas_do_fork_continuam_existindo(setup_spyder_fork, flag, atributo):
    assert getattr(parse(setup_spyder_fork, [flag]), atributo) is True


@pytest.mark.phase0
def test_fork_conf_dir_e_aceito(setup_spyder_fork, tmp_path):
    """Secao 5.1: "--conf-dir tem precedencia explicita sobre os dois modos"."""
    args = parse(setup_spyder_fork, ["--conf-dir", str(tmp_path)])
    assert args.conf_dir == str(tmp_path)


@pytest.mark.phase0
def test_fork_hide_e_show_sao_repetiveis(setup_spyder_fork):
    args = parse(
        setup_spyder_fork, ["--hide", "a,b", "--hide", "c", "--show", ".github"]
    )
    assert args.hide == ["a,b", "c"]
    assert args.show == [".github"]


@pytest.mark.phase0
def test_fork_main_repassa_todas_as_opcoes_para_launch(setup_spyder_fork, monkeypatch,
                                                       tmp_path):
    recebidos = {}
    monkeypatch.setattr(
        setup_spyder_fork,
        "launch",
        lambda *args, **kwargs: recebidos.update(kwargs) or 0,
    )
    setup_spyder_fork.main(
        [
            "--no-launch",
            "--keep-config",
            "--ephemeral",
            "--sem-estilo",
            "-w",
            str(tmp_path),
            "--conf-dir",
            str(tmp_path / "conf"),
            "--hide",
            "docs",
            "--show",
            ".github",
        ]
    )
    assert recebidos["no_launch"] is True
    assert recebidos["keep_config"] is True
    assert recebidos["ephemeral"] is True
    assert recebidos["sem_estilo"] is True
    assert recebidos["workdir"] == str(tmp_path)
    assert recebidos["conf_dir"] == str(tmp_path / "conf")
    assert recebidos["hide"] == ["docs"]
    assert recebidos["show"] == [".github"]


@pytest.mark.phase2
def test_fork_main_repassa_as_opcoes_novas_para_launch(setup_spyder_fork, monkeypatch):
    recebidos = {}
    monkeypatch.setattr(
        setup_spyder_fork,
        "launch",
        lambda *args, **kwargs: recebidos.update(kwargs) or 0,
    )
    setup_spyder_fork.main(
        ["--agent", "codex", "--profile", "ephemeral", "--reset-profile"]
    )
    assert recebidos["agent"] == "codex"
    assert recebidos["profile"] == "ephemeral"
    assert recebidos["reset_profile"] is True


@pytest.mark.phase2
def test_fork_main_sem_opcoes_novas_deixa_launch_decidir(setup_spyder_fork, monkeypatch):
    """`--agent` ausente e None (preferencia salva decide), nao 'auto'."""
    recebidos = {}
    monkeypatch.setattr(
        setup_spyder_fork,
        "launch",
        lambda *args, **kwargs: recebidos.update(kwargs) or 0,
    )
    setup_spyder_fork.main([])
    assert recebidos["agent"] is None
    assert recebidos["profile"] is None
    assert recebidos["reset_profile"] is False


@pytest.mark.phase2
def test_o_fork_repassa_tudo_ao_launcher(setup_spyder_fork, monkeypatch, tmp_path):
    recebidos = {}
    monkeypatch.setattr(
        setup_spyder_fork,
        "_launch",
        lambda *args, **kwargs: recebidos.update(kwargs) or 0,
    )
    code = setup_spyder_fork.launch(
        ["--debug-info", "minimal"],
        no_launch=True,
        workdir=tmp_path,
        agent="none",
        profile="project",
        reset_profile=True,
        sem_estilo=True,
    )
    assert code == 0
    assert recebidos["workdir"] == tmp_path.resolve()
    assert recebidos["agent"] == "none"
    assert recebidos["profile"] == "project"
    assert recebidos["reset_profile"] is True
    assert recebidos["sem_estilo"] is True
    assert recebidos["no_launch"] is True


@pytest.mark.phase4
@pytest.mark.parametrize("agent", ["auto", "codex", "claude", "none"])
def test_agent_aceita_os_quatro_perfis(setup_spyder_fork, agent):
    args = parse_or_pending(setup_spyder_fork, ["--agent", agent], "--agent")
    assert args.agent == agent


@pytest.mark.phase4
def test_agent_recusa_provedor_desconhecido(setup_spyder_fork):
    parse_or_pending(setup_spyder_fork, ["--agent", "codex"], "--agent")
    with contextlib.redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit):
            setup_spyder_fork.parse_args(["--agent", "gpt-hipotetico"])


@pytest.mark.phase2
@pytest.mark.parametrize("profile", ["ephemeral", "project"])
def test_profile_aceita_efemero_e_de_projeto(setup_spyder_fork, profile):
    args = parse_or_pending(setup_spyder_fork, ["--profile", profile], "--profile")
    assert args.profile == profile


@pytest.mark.phase2
def test_reset_profile_existe_no_fork(setup_spyder_fork):
    args = parse_or_pending(
        setup_spyder_fork, ["--reset-profile"], "--reset-profile"
    )
    assert args.reset_profile is True


@pytest.mark.phase2
def test_a_flag_ephemeral_atual_continua_valendo_com_profile(setup_spyder_fork):
    """Secao 5.1: as opcoes novas nao podem aposentar as antigas de surpresa."""
    args = parse_or_pending(
        setup_spyder_fork,
        ["--ephemeral", "--keep-config", "--profile", "ephemeral"],
        "--profile junto de --ephemeral",
    )
    assert args.ephemeral is True
    assert args.keep_config is True


@pytest.mark.phase4
def test_opcoes_novas_convivem_com_as_antigas(setup_spyder_fork, tmp_path):
    argv = [
        "--no-launch",
        "--sem-estilo",
        "-w",
        str(tmp_path),
        "--hide",
        "docs",
        "--agent",
        "codex",
        "--",
        "--debug-info",
        "verbose",
    ]
    args = parse_or_pending(setup_spyder_fork, argv, "combinacao de opcoes novas")
    assert args.no_launch and args.sem_estilo
    assert args.workdir == str(tmp_path)
    assert args.hide == ["docs"]
    assert args.agent == "codex"
    assert [a for a in args.spyder_args if a != "--"] == ["--debug-info", "verbose"]
