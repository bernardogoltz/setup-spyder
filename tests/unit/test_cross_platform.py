"""O mesmo codigo, e a mesma resolucao de dependencias, nos tres sistemas.

A secao 12 do plano deixava a matriz de sistemas operacionais inteiramente para
a CI. So que a CI descobre um ramo errado *depois* do push, num runner que o
desenvolvedor nao tem na mesa: foi assim que `pyqt5-qt5==5.15.2` (unica versao
com wheel de Windows) chegou ao runner macOS arm64, que nao tem wheel nenhum
dela, e derrubou `uv run pytest` antes do primeiro teste.

Este arquivo roda os ramos dos outros sistemas *aqui*, no sistema de quem roda
a suite, de dois jeitos:

* **metadados** - avaliando os marcadores PEP 508 do `pyproject.toml` contra um
  ambiente sintetico por sistema (nao resolve nada na rede, nao chama o `uv`);
* **codigo** - simulando ``sys.platform`` / ``os.name`` e provando o ramo do
  outro sistema com dubles (`subprocess.Popen`, `os.killpg`, `signal.signal`).

Nada aqui substitui a CI por plataforma: um wheel que existe no indice mas nao
instala, um ConPTY que se comporta diferente, isso so o runner de verdade pega.
O que este arquivo pega e a classe de erro que nao depende do runner - a
decisao por sistema escrita errada no codigo ou no `pyproject.toml`.
"""

from __future__ import annotations

import os
import re
import signal
import sys
from pathlib import Path

import pytest

pytest.importorskip(
    "packaging", reason="packaging vem com o pytest; sem ele nao ha marcador a avaliar"
)

from packaging.markers import Marker  # noqa: E402
from packaging.requirements import Requirement  # noqa: E402
from packaging.specifiers import SpecifierSet  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.plataforma]

REPO_ROOT = Path(__file__).resolve().parents[2]


# Os sistemas ------------------------------------------------------------

#: Um ambiente PEP 508 por sistema que o projeto suporta. As chaves sao as do
#: `packaging.markers`; o que nao esta aqui vem do interpretador corrente
#: (versao do Python, implementacao), que e o mesmo em qualquer sistema.
#:
#: macOS aparece duas vezes de proposito: `macos-latest` e Apple Silicon desde
#: a imagem 14, e foi exatamente o par arm64 que a resolucao ignorava.
AMBIENTES: dict[str, dict[str, str]] = {
    "windows": {
        "sys_platform": "win32",
        "platform_system": "Windows",
        "os_name": "nt",
        "platform_machine": "AMD64",
    },
    "macos-arm64": {
        "sys_platform": "darwin",
        "platform_system": "Darwin",
        "os_name": "posix",
        "platform_machine": "arm64",
    },
    "macos-x86_64": {
        "sys_platform": "darwin",
        "platform_system": "Darwin",
        "os_name": "posix",
        "platform_machine": "x86_64",
    },
    "linux": {
        "sys_platform": "linux",
        "platform_system": "Linux",
        "os_name": "posix",
        "platform_machine": "x86_64",
    },
}

SISTEMAS = tuple(AMBIENTES)
POSIX = tuple(so for so in SISTEMAS if so != "windows")


def eh_windows(so: str) -> bool:
    return so == "windows"


@pytest.fixture()
def simula_so(monkeypatch: pytest.MonkeyPatch):
    """Faz o processo de teste se passar por outro sistema operacional.

    Devolve uma funcao ``simula_so(nome) -> ambiente``. Mexe so em
    ``sys.platform``, que e por onde o pacote decide: o sistema de arquivos e o
    interpretador continuam sendo os desta maquina, entao os testes que usam
    isto exercitam *decisao*, nunca chamada de sistema.

    ``os.name`` fica de fora de proposito - o `pathlib` escolhe entre
    `WindowsPath` e `PosixPath` por ele, e trocar isso quebra qualquer `Path()`
    no meio do teste. Quem precisa do ramo por `os.name` (so
    `perfil.spyder_default_font`) troca na hora, e nao toca em caminho nenhum.
    """

    def aplicar(so: str) -> dict[str, str]:
        ambiente = AMBIENTES[so]
        monkeypatch.setattr(sys, "platform", ambiente["sys_platform"])
        return ambiente

    return aplicar


# ------------------------------------------------------------------------
# 1. Dependencias: o que cada sistema instala
# ------------------------------------------------------------------------

# As duas versoes que definem o problema do Qt. Nenhuma serve para todo mundo,
# e e por isso que a resolucao precisa bifurcar por plataforma:
#
#   5.15.2   ultima com wheel win_amd64; nao tem wheel macosx arm64
#   5.15.19  tem wheel macosx arm64 e manylinux; nao tem wheel de Windows
QT_COM_WHEEL_DE_WINDOWS = "5.15.2"
QT_COM_WHEEL_APPLE_SILICON = "5.15.19"

PACOTES_QT = ("pyqt5-qt5", "pyqtwebengine-qt5")


@pytest.fixture(scope="module")
def pyproject() -> dict:
    caminho = REPO_ROOT / "pyproject.toml"
    if not caminho.is_file():
        pytest.skip(f"sem pyproject.toml em {REPO_ROOT}: suite rodando fora do repo")
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        tomllib = pytest.importorskip(
            "tomli", reason="ler o pyproject em Python < 3.11 exige tomli"
        )
    return tomllib.loads(caminho.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dependencias(pyproject) -> list:
    return [Requirement(texto) for texto in pyproject["project"]["dependencies"]]


def ativas(dependencias: list, so: str) -> list:
    """As dependencias que valem em ``so``, ja com os marcadores avaliados."""
    ambiente = AMBIENTES[so]
    return [
        req for req in dependencias if req.marker is None or req.marker.evaluate(ambiente)
    ]


def limite_de(dependencias: list, nome: str, so: str) -> SpecifierSet:
    """Interseccao dos limites de versao que ``nome`` recebe em ``so``."""
    limite = SpecifierSet()
    for req in ativas(dependencias, so):
        if req.name.lower() == nome:
            limite &= req.specifier
    return limite


@pytest.mark.parametrize("so", SISTEMAS)
@pytest.mark.parametrize("pacote", PACOTES_QT)
def test_o_qt_tem_um_limite_instalavel_em_cada_sistema(dependencias, pacote, so):
    """Todo sistema tem de admitir uma versao do Qt que tenha wheel para ele.

    Sem os dois lados do pino (o teto no Windows *e* o piso fora dele) o uv
    resolve 5.15.2 para todo mundo e o macOS arm64 nao instala.
    """
    limite = limite_de(dependencias, pacote, so)
    assert str(limite), (
        f"{pacote} nao tem limite nenhum em {so}: o uv fica livre para escolher "
        "uma versao sem wheel para este sistema"
    )
    assert limite.contains(QT_COM_WHEEL_DE_WINDOWS) is eh_windows(so), (
        f"{pacote}{limite} em {so}: a {QT_COM_WHEEL_DE_WINDOWS} so tem wheel de "
        "Windows, e e a unica que tem"
    )
    assert limite.contains(QT_COM_WHEEL_APPLE_SILICON) is not eh_windows(so), (
        f"{pacote}{limite} em {so}: a {QT_COM_WHEEL_APPLE_SILICON} tem wheel "
        "macosx arm64 e manylinux, e nao tem wheel de Windows"
    )


@pytest.mark.parametrize("so", SISTEMAS)
def test_cada_sistema_recebe_exatamente_um_backend_de_pty(dependencias, so):
    """`pywinpty` no Windows, `ptyprocess` fora dele - nunca os dois, nunca zero."""
    backends = {
        req.name.lower()
        for req in ativas(dependencias, so)
        if req.name.lower() in {"pywinpty", "ptyprocess"}
    }
    esperado = {"pywinpty"} if eh_windows(so) else {"ptyprocess"}
    assert backends == esperado


@pytest.mark.parametrize("so", SISTEMAS)
def test_o_fork_e_o_spyder_valem_em_todo_sistema(dependencias, so):
    """O que nao e especifico de plataforma tem de chegar em todos eles."""
    nomes = {req.name.lower() for req in ativas(dependencias, so)}
    assert {"spyder", "pandas", "rich"} <= nomes


@pytest.mark.parametrize("so", SISTEMAS)
def test_required_environments_declara_os_tres_sistemas(pyproject, so):
    """`[tool.uv] required-environments` e o que forca o uv a checar o wheel.

    Um sistema de fora da lista e resolvido "no melhor esforco": o uv escolhe
    uma versao que serve para os declarados e so descobre que ela nao instala
    naquele sistema quando alguem roda o `uv run` la.
    """
    declarados = pyproject["tool"]["uv"]["required-environments"]
    marcadores = [Marker(texto) for texto in declarados]
    assert any(marcador.evaluate(AMBIENTES[so]) for marcador in marcadores), (
        f"{so} ({AMBIENTES[so]}) nao casa com nenhum required-environment: {declarados}"
    )


def sistema_do_runner(label: str) -> "str | None":
    """Mapeia o rotulo de um runner do GitHub para uma chave de `AMBIENTES`."""
    if label.startswith("windows"):
        return "windows"
    if label.startswith("ubuntu"):
        return "linux"
    if label.startswith("macos"):
        # macos-13 e a ultima imagem Intel; da 14 em diante (e `-latest`) e arm64.
        return "macos-x86_64" if label in ("macos-12", "macos-13") else "macos-arm64"
    return None


def runners_da_ci() -> set:
    caminho = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    if not caminho.is_file():
        pytest.skip(f"sem {caminho}: suite rodando fora do repo")
    texto = caminho.read_text(encoding="utf-8")
    labels = set()
    for bloco in re.findall(r"^\s*os:\s*\[([^\]]*)\]", texto, re.M):
        labels.update(item.strip() for item in bloco.split(",") if item.strip())
    labels.update(re.findall(r"^\s*runs-on:\s*([A-Za-z0-9._-]+)\s*$", texto, re.M))
    return labels


def test_a_ci_roda_nos_tres_sistemas():
    """Perder um sistema da matriz e perder a unica prova real que temos dele."""
    sistemas = {sistema_do_runner(label) for label in runners_da_ci()}
    assert {"windows", "linux"} <= sistemas
    assert sistemas & {"macos-arm64", "macos-x86_64"}, "a CI nao roda em macOS"


def test_todo_runner_da_ci_esta_declarado_no_pyproject(pyproject):
    """Runner novo na CI => `required-environments` novo, ou volta o erro do macOS."""
    declarados = [
        Marker(texto) for texto in pyproject["tool"]["uv"]["required-environments"]
    ]
    for label in sorted(runners_da_ci()):
        so = sistema_do_runner(label)
        assert so is not None, (
            f"runner {label!r} da CI nao esta mapeado em sistema_do_runner(); "
            "acrescente o sistema a AMBIENTES antes de usa-lo na matriz"
        )
        assert any(marcador.evaluate(AMBIENTES[so]) for marcador in declarados), (
            f"a CI roda em {label} ({so}), mas o pyproject nao declara esse "
            "ambiente em [tool.uv] required-environments"
        )


# ------------------------------------------------------------------------
# 2. Provedores: como o `codex`/`claude` e chamado em cada sistema
# ------------------------------------------------------------------------


@pytest.fixture()
def providers():
    from setup_spyder.plugin import providers as modulo

    return modulo


@pytest.mark.parametrize("so", SISTEMAS)
def test_o_shim_cmd_so_passa_pelo_comspec_no_windows(
    providers, simula_so, monkeypatch, so
):
    """No Windows o `codex.cmd` do npm nao e executavel por `CreateProcess`.

    A forma aceita e ``[cmd.exe, "/c", <caminho>, ...]`` - caminho como
    argumento separado, nunca interpolado numa linha de comando. Fora do
    Windows um arquivo terminado em `.cmd` e so um arquivo: chama-se direto.
    """
    simula_so(so)
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    shim = r"C:\Users\dev\AppData\Roaming\npm\codex.cmd"
    monkeypatch.setattr(providers, "find_executable", lambda provider: shim)

    comando = providers.build_command(providers.KNOWN_PROVIDERS["codex"])

    if eh_windows(so):
        assert comando == [r"C:\Windows\System32\cmd.exe", "/c", shim]
    else:
        assert comando == [shim]


@pytest.mark.parametrize("so", SISTEMAS)
def test_um_executavel_de_verdade_nunca_passa_pelo_comspec(
    providers, simula_so, monkeypatch, so
):
    simula_so(so)
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    binario = r"C:\ferramentas\claude.exe" if eh_windows(so) else "/usr/local/bin/claude"
    monkeypatch.setattr(providers, "find_executable", lambda provider: binario)

    assert providers.build_command(providers.KNOWN_PROVIDERS["claude"]) == [binario]


@pytest.mark.parametrize("so", SISTEMAS)
def test_o_shell_de_fallback_e_o_do_sistema(providers, simula_so, monkeypatch, so):
    simula_so(so)
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    monkeypatch.setenv("SHELL", "/bin/zsh")

    esperado = r"C:\Windows\System32\cmd.exe" if eh_windows(so) else "/bin/zsh"
    assert providers.default_shell() == [esperado]


# ------------------------------------------------------------------------
# 3. Arvore de processos: Job Object no Windows, grupo de processo no POSIX
# ------------------------------------------------------------------------


class ProcessoFalso:
    """O minimo de `subprocess.Popen` que o `ChildTree` consulta."""

    def __init__(self, pid: int = 4321, imortal: bool = False):
        self.pid = pid
        self.imortal = imortal
        self.vivo = True
        self.terminates = 0

    def poll(self):
        return None if self.vivo else 0

    def terminate(self):
        self.terminates += 1
        if not self.imortal:
            self.vivo = False

    def wait(self, timeout=None):
        self.vivo = False
        return 0


@pytest.fixture()
def children():
    from setup_spyder import _children as modulo

    return modulo


@pytest.fixture()
def arvore(children, monkeypatch):
    """Fabrica de `ChildTree` com `Popen`, Job Object e sinais dublados.

    Devolve ``arvore(so, imortal=False) -> (tree, registro, processo)``.
    `registro` traz o que cada sistema fez: os kwargs do `Popen`, os pids
    mandados para o Job Object e os sinais entregues ao grupo de processo.
    """

    def montar(so: str, imortal: bool = False):
        registro: dict = {
            "comando": None,
            "popen_kwargs": None,
            "jobs": [],
            "encerrados": [],
            "sinais": [],
        }
        processo = ProcessoFalso(imortal=imortal)

        def popen_falso(comando, **kwargs):
            registro["comando"] = list(comando)
            registro["popen_kwargs"] = kwargs
            return processo

        def assign_job_falso(pid):
            registro["jobs"].append(pid)
            return "JOB"

        def killpg_falso(pid, sig):
            registro["sinais"].append((pid, sig))
            if sig == signal.SIGTERM and not imortal:
                processo.vivo = False

        monkeypatch.setattr(children, "WINDOWS", eh_windows(so))
        monkeypatch.setattr(children.subprocess, "Popen", popen_falso)
        monkeypatch.setattr(children, "assign_job", assign_job_falso)
        monkeypatch.setattr(
            children, "terminate_job", lambda job: registro["encerrados"].append(job)
        )
        monkeypatch.setattr(
            children.ChildTree, "_install_signal_forwarding", lambda self: None
        )
        # `os.killpg` e `SIGKILL` nao existem no Windows: para rodar o ramo
        # POSIX numa maquina Windows eles precisam existir como duble.
        monkeypatch.setattr(os, "killpg", killpg_falso, raising=False)
        monkeypatch.setattr(signal, "SIGKILL", getattr(signal, "SIGKILL", 9), raising=False)

        return children.ChildTree(["prog", "--arg"]), registro, processo

    return montar


@pytest.mark.parametrize("so", SISTEMAS)
def test_o_filho_nasce_preso_ao_pai_em_qualquer_sistema(arvore, so):
    """Windows prende por Job Object; POSIX, por sessao nova + grupo."""
    tree, registro, processo = arvore(so)
    tree.start()

    assert registro["comando"] == ["prog", "--arg"]
    if eh_windows(so):
        assert registro["jobs"] == [processo.pid], "o filho ficou fora do Job Object"
        assert "start_new_session" not in registro["popen_kwargs"]
    else:
        assert registro["jobs"] == [], "Job Object e API de Windows"
        assert registro["popen_kwargs"]["start_new_session"] is True


@pytest.mark.parametrize("so", SISTEMAS)
def test_o_encerramento_educado_usa_o_mecanismo_do_sistema(arvore, so):
    tree, registro, processo = arvore(so)
    tree.start()
    tree.terminate(grace_period=0.5)

    if eh_windows(so):
        assert processo.terminates == 1
        assert registro["encerrados"] == ["JOB"], "o Job Object nao foi fechado"
        assert registro["sinais"] == []
    else:
        assert processo.terminates == 0, "no POSIX quem leva o sinal e o grupo"
        assert registro["sinais"] == [(processo.pid, signal.SIGTERM)]


@pytest.mark.parametrize("so", POSIX)
def test_no_posix_quem_ignora_o_sigterm_leva_sigkill(arvore, so):
    tree, registro, processo = arvore(so, imortal=True)
    tree.start()
    tree.terminate(grace_period=0.0)

    assert registro["sinais"] == [
        (processo.pid, signal.SIGTERM),
        (processo.pid, signal.SIGKILL),
    ]


#: Os sinais que existem em cada sistema. `SIGBREAK` so existe no Windows;
#: `SIGHUP` so fora dele. Pedir o que nao existe e `AttributeError` na subida.
SINAIS_DO_SISTEMA = {
    "windows": ("SIGTERM", "SIGINT", "SIGBREAK"),
    "macos-arm64": ("SIGTERM", "SIGINT", "SIGHUP"),
    "macos-x86_64": ("SIGTERM", "SIGINT", "SIGHUP"),
    "linux": ("SIGTERM", "SIGINT", "SIGHUP"),
}


@pytest.mark.parametrize("so", SISTEMAS)
def test_o_encaminhamento_de_sinais_pega_so_o_que_o_sistema_tem(
    children, monkeypatch, so
):
    numeros = {"SIGTERM": 15, "SIGINT": 2, "SIGHUP": 1, "SIGBREAK": 21}
    presentes = SINAIS_DO_SISTEMA[so]
    for nome, numero in numeros.items():
        if nome in presentes:
            monkeypatch.setattr(signal, nome, numero, raising=False)
        else:
            monkeypatch.delattr(signal, nome, raising=False)

    instalados: list = []

    def signal_falso(signum, handler):
        instalados.append(signum)
        return "HANDLER_ANTERIOR"

    monkeypatch.setattr(children.signal, "signal", signal_falso)

    tree = children.ChildTree(["prog"])
    tree._install_signal_forwarding()
    assert instalados == [numeros[nome] for nome in presentes]

    instalados.clear()
    tree.close()
    assert instalados == [numeros[nome] for nome in presentes], "os handlers nao voltaram"


# ------------------------------------------------------------------------
# 4. Perfil: onde cada sistema guarda fonte
# ------------------------------------------------------------------------


@pytest.fixture()
def perfil():
    import setup_spyder.perfil as modulo

    return modulo


#: Ancoras que identificam o diretorio de fontes de cada sistema. A primeira
#: entrada e sempre a do usuario: e onde o launcher pode instalar sem admin.
FONTES_ESPERADAS = {
    "windows": ("Microsoft/Windows/Fonts", "Fonts"),
    "macos-arm64": ("Library/Fonts", "/Library/Fonts", "/System/Library/Fonts"),
    "macos-x86_64": ("Library/Fonts", "/Library/Fonts", "/System/Library/Fonts"),
    "linux": (".local/share/fonts", "/usr/local/share/fonts", "/usr/share/fonts"),
}


@pytest.mark.parametrize("so", SISTEMAS)
def test_os_diretorios_de_fonte_sao_os_do_sistema(
    perfil, simula_so, monkeypatch, isolated_home, so
):
    simula_so(so)
    monkeypatch.setenv("LOCALAPPDATA", str(isolated_home / "AppData" / "Local"))
    monkeypatch.setenv("WINDIR", r"C:\Windows")

    diretorios = perfil.font_dirs()
    caminhos = [Path(d).as_posix() for d in diretorios]

    assert len(caminhos) == len(set(caminhos)), f"diretorio repetido em {so}: {caminhos}"
    assert len(caminhos) == len(FONTES_ESPERADAS[so])
    for ancora, caminho in zip(FONTES_ESPERADAS[so], caminhos):
        assert caminho.endswith(ancora), f"{so}: {caminho} nao termina em {ancora}"
    assert caminhos[0].startswith(isolated_home.as_posix()), (
        f"{so}: o primeiro diretorio tem de ser o do usuario, veio {caminhos[0]}"
    )


@pytest.mark.parametrize("so", SISTEMAS)
def test_sem_o_spyder_a_fonte_padrao_ainda_e_a_do_sistema(
    perfil, simula_so, monkeypatch, so
):
    """`spyder_default_font` cai num padrao proprio quando o Spyder nao importa.

    O fallback e o unico ramo que roda quando o fork nao esta no ambiente (a
    CI de empacotamento, por exemplo), e ele decide por `os.name` - o unico
    lugar do pacote que decide por ali, e por isso o unico teste que troca
    `os.name` (nada aqui constroi `Path`, que e o que essa troca quebraria).
    """
    simula_so(so)
    monkeypatch.setattr(os, "name", AMBIENTES[so]["os_name"])
    monkeypatch.setitem(sys.modules, "spyder.config.fonts", None)  # forca ImportError

    esperado = "Consolas" if eh_windows(so) else "Monospace"
    assert perfil.spyder_default_font() == esperado


# ------------------------------------------------------------------------
# 5. Pai -> filho: a lista de paineis escondidos atravessa o separador certo
# ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "so,separador", [("windows", ";"), ("linux", ":"), ("macos-arm64", ":")]
)
def test_a_blocklist_do_painel_projetos_sobrevive_ao_separador(
    simula_so, monkeypatch, tmp_path, so, separador
):
    """O pai junta com `os.pathsep` e o filho separa com `os.pathsep`.

    Sao dois processos e dois pontos do codigo; se um deles trocar o separador
    por um literal, a blocklist chega partida (ou vazia) do outro lado, e so
    no sistema cujo separador nao e o do literal.
    """
    from setup_spyder import bootstrap, launcher

    simula_so(so)
    monkeypatch.setattr(os, "pathsep", separador)
    escondidos = (".venv", "dist", "build")

    _, env = launcher.build_child_command(
        conf_dir=tmp_path / "conf",
        workdir=tmp_path,
        agent="none",
        autostart=False,
        hidden=escondidos,
    )
    assert env["SETUP_SPYDER_HIDDEN"] == separador.join(escondidos)

    monkeypatch.setenv("SETUP_SPYDER_HIDDEN", env["SETUP_SPYDER_HIDDEN"])
    assert bootstrap.hidden_names() == list(escondidos)
