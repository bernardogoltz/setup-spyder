# Suíte de testes do plano `setup-spyder` + AI Terminal

Testes automatizados para a seção 10 (“Estratégia de testes”) e os critérios de
aceitação da seção 11 de [`docs/plan.md`](../../docs/plan.md) do fork.

## Como rodar

De dentro de `setup-spyder/`. O repositório funciona sozinho: `uv run` resolve
o fork `spyder` pinado no `pyproject.toml` direto do GitHub e cria o `.venv`
próprio — é exatamente o que a CI faz (`.github/workflows/ci.yml`):

```powershell
cd setup-spyder
uv run pytest -m "unit or legacy"       # job `unit` da CI: sem Qt, sem PTY
uv run pytest -m "not e2e"              # job `full` da CI
```

Dentro do checkout do fork também dá para usar o venv da raiz, que já tem o
fork `spyder` 5.6.0.dev0 e este pacote instalados em modo editável. Nunca rode
o pytest *da raiz* do fork (o `conftest.py` de lá tem uma fixture `autouse`
que importa e reseta o `CONF` do Spyder a cada teste).

```powershell
cd setup-spyder
$py = "..\.venv\Scripts\python.exe"

# tudo que não abre janela
& $py -m pytest tests/unit tests/integration tests/legacy -p no:cacheprovider

# só o que já tem de passar hoje (contratos congelados da Fase 0)
& $py -m pytest tests/unit tests/integration tests/legacy -m phase0 -p no:cacheprovider

# fechando uma fase: skip vira falha
$env:SETUP_SPYDER_STRICT="1"
& $py -m pytest tests/unit tests/integration tests/legacy -m "phase0 or phase2" -p no:cacheprovider
```

O `pyproject.toml` deste pacote fixa a *rootdir*, o `testpaths` e os marcadores;
um `pytest` pelado de dentro de `setup-spyder/` também coleta `tests/e2e`, que
só roda com `SETUP_SPYDER_E2E=1`.

### Variáveis de ambiente

| Variável | Efeito |
| --- | --- |
| `SETUP_SPYDER_STRICT=1` | “entrega ainda não feita” deixa de ser skip e vira falha |
| `SETUP_SPYDER_E2E=1` | habilita `tests/e2e/`, que abre o Spyder de verdade |
| `SETUP_SPYDER_WHEEL=<caminho>` | faz `tests/integration/test_packaging.py` inspecionar uma wheel construída em vez do pacote instalado |

### Dependências opcionais

`pytest-qt`, `psutil` (árvore de processos e portas em escuta),
`pywinpty`/`ptyprocess` (backend real de PTY). Sem elas os testes
correspondentes pulam com a razão explícita, e o resto roda.

O mesmo vale para o QtWebEngine: num Linux sem `libnss3`/`libasound2` o
import falha e só `tests/qt` é pulado. O skip é feito por
`helpers.pending.pular_diretorio` num hook `pytest_collection_modifyitems`,
nunca por `pytest.importorskip` no topo de um `conftest.py` aninhado — no
pytest 7 isso derruba a coleta da sessão inteira ("collected 0 items / 1
skipped", código 5), levando `tests/unit` junto.

`QT_QPA_PLATFORM=offscreen` só no Linux. No Windows o QtWebEngine sob a
plataforma offscreen morre com *access violation* ao criar o primeiro
`QWebEngineView`; o runner do Windows tem sessão de desktop e não precisa.

## Os três regimes da suíte

1. **Passa hoje.** Congela o que `setup_spyder/` já faz: a API pública
   (`launch`/`main`/`open_spyder`), os argumentos da CLI, `perfil.py`,
   `patches.py`, o invariante “nome do entry point = `PluginClass.NAME`”, e a
   configuração isolada de verdade em `<projeto>/.spyproject/setup-spyder/`.
   É a Fase 0 do plano: “congelar os contratos públicos atuais com testes”.
2. **Pula, dizendo o que falta.** O que o plano promete e ainda não existe.
   Guardado por `require_module` / `require_attr`. Com
   `SETUP_SPYDER_STRICT=1` esses skips viram falhas — é assim que se declara
   uma fase encerrada. A Fase 2 (launcher, perfis, bootstrap filho) está
   fechada: `-m "phase0 or phase2"` passa em modo estrito.
3. **Divergências resolvidas.** `tests/unit/test_plan_divergences.py` guardava
   como `xfail` as decisões do código antigo que o plano revisado desfazia. A
   migração aconteceu e os testes viraram asserts simples; voltar a falhar ali
   é regressão.

As oito divergências, e como foram resolvidas:

| Seção do plano | O que o código fazia | Hoje |
| --- | --- | --- |
| 2.2 “SDK + widget de chat → não usar no MVP” | `worker.py` falava com `claude_agent_sdk` | sem SDK; o painel é xterm + PTY |
| 1 “fora do MVP: enviar seleção do editor automaticamente” | conectava `sig_editor_focus_changed` | removido |
| 4 “não adicionar `claude-agent-sdk`” | dependência do SDK | `requires(setup-spyder)` não cita SDK nenhum |
| 1 / 11 “nenhuma flag de bypass implícita” | `permission_mode="bypassPermissions"` | removido |
| 7 “sem monkeypatch global de `QApplication.beep`” | `patches.py` trocava `beep` | `patches.py` só filtra o painel Projetos |
| 8 “não desabilitar avisos críticos” | `show_internal_errors=False`, `compute_dependencies` anulado | `POPUPS` sem `show_internal_errors`; patch removido |
| 5.3 “não limpar `CONDA_*` sem prova” | `strip_conda_env`, `find_conda` anulado | o filho herda `os.environ` intacto |
| 5.3 “seed versionado, não regravar a cada boot” | `apply_perfil` em toda inicialização | `seed_profile` com marcador versionado |

## Mapa arquivo → seção do plano

| Arquivo | Seção |
| --- | --- |
| `tests/unit/test_baseline_public_api.py` | 2.1, 9 (Fase 0) |
| `tests/unit/test_cli_arguments.py` | 5.1 |
| `tests/unit/test_launcher_bootstrap.py` | 5.1, 5.2, 5.3 |
| `tests/unit/test_profile.py` | 5.1, 5.3 |
| `tests/unit/test_providers.py` | 6.3, 7 |
| `tests/unit/test_argv_no_shell.py` | 6.2, 11, 12 |
| `tests/unit/test_entry_point.py` | 4, 6 |
| `tests/unit/test_plan_divergences.py` | 1, 2.2, 4, 5.3, 7, 8, 11 |
| `tests/unit/test_cross_platform.py` | 12 (“CI por plataforma”), 5.2, 6.3 |
| `tests/qt/test_widget_session.py` | 6.2, 7 |
| `tests/qt/test_plugin_dock.py` | 6, 7 |
| `tests/qt/test_backend_failure.py` | 6.1, 8 |
| `tests/pty/test_pty_contract.py` | 6.2, 10 (“PTY por plataforma”) |
| `tests/integration/test_process_isolation.py` | 5.2 |
| `tests/integration/test_isolated_config.py` | 5.1, 5.3, 11 |
| `tests/integration/test_plugin_discovery.py` | 6.1, 9 (Fase 0), 12 |
| `tests/integration/test_packaging.py` | 4, 9 (Fase 6), 11 |
| `tests/e2e/test_launch_spyder.py` | 10, 11 |
| `tests/legacy/` | API 0.2.0 com stubs do Spyder (sem Qt, sem display) |

## Contrato alvo

Os testes do regime 2 fixam a API que a implementação precisa oferecer. Onde o
plano dá o esqueleto (o `AgentProvider`, o contrato do `PTYWorker`), a suíte
segue o plano; onde o plano fica no nível da descrição, a suíte escolhe a forma
mínima que torna o comportamento verificável. Mudar a forma é legítimo — mudar
o comportamento não.

```python
# setup_spyder (API pública, congelada)
launch(spyder_args=(), *, no_launch=False, keep_config=False, ephemeral=False,
       sem_estilo=False, workdir=None, conf_dir=None, hide=(), show=(),
       agent=None, profile=None, reset_profile=False) -> int
main(argv=None) -> int
open_spyder is launch

# setup_spyder.launcher (processo pai; nunca importa o Spyder)
resolve_workdir(workdir=None, cwd=None) -> Path
resolve_profile(workdir, *, conf_dir=None, ephemeral=False, profile=None,
                keep_config=False) -> Profile(kind, path, delete_at_exit)
ensure_spyproject(root) -> Path                  # escreve .spyproject/config/*.ini
build_child_command(*, conf_dir, workdir, agent, autostart, spyder_args=(),
                    profile="ephemeral", hidden=(), sem_estilo=False,
                    seed_only=False) -> tuple[list[str], dict[str, str]]

# setup_spyder.bootstrap (processo filho: python -m setup_spyder.bootstrap)
split_bootstrap_argv(argv) -> (seed_only, conf_dir, spyder_argv)
main(argv=None) -> int          # seed_profile -> filtro do painel -> spyder.app.start

# setup_spyder.perfil
CONF_DIRNAME = ".spyproject/setup-spyder"
SEED_VERSION: int
conf_dir_for(workdir, ephemeral=False) -> Path
seed_profile(conf_dir, *, version=SEED_VERSION, font_family=None,
             com_estilo=True) -> bool                       # True se escreveu
reset_profile(conf_dir, *, project_root=None) -> Path      # valida o caminho

# variáveis que o pai entrega ao filho (e que o plugin lê)
SPYDER_CONFDIR, SETUP_SPYDER_AGENT (auto|codex|claude|none),
SETUP_SPYDER_WORKDIR, SETUP_SPYDER_AUTOSTART (0|1),
SETUP_SPYDER_HIDDEN (nomes separados por os.pathsep), SETUP_SPYDER_SEED_STYLE (0|1)

# setup_spyder.plugin.providers
AgentProvider(name, executable, argv)          # frozen dataclass
KNOWN_PROVIDERS: Mapping[str, AgentProvider]   # {"codex", "claude"}
available_providers() -> tuple[AgentProvider, ...]
resolve_provider(requested=None, preference=None) -> AgentResolution
AgentResolution(provider, reason, candidates, requested, autostart)
#   reason: explicit | preference | single | ambiguous | missing | disabled
build_command(provider) -> list[str]

# setup_spyder.plugin.pty_worker
create_pty_worker() -> PTYWorker do sistema operacional corrente
PTYWorker.start(argv, cwd=None, env=None, rows=24, cols=80)
PTYWorker.write(data) / resize(rows, cols) / interrupt() / is_alive()
PTYWorker.terminate(grace_period=2.0)
PTYWorker.sig_output(bytes) / sig_exited(int) / sig_error(str)

# setup_spyder.plugin.main_widget
create_pty_worker(...)          # ponto único de criação, com import tardio
AITerminalWidget
    sig_state_changed(str)      # idle | starting | running | exited | error
    state -> str
    set_working_directory(path) / set_provider(name) / refresh_providers()
    start_session(provider=None) / restart() / interrupt() / clear()
    close_session() / send_input(text) / resize_terminal(rows, cols)
    get_provider_selector() / get_state_label()
    get_error_message() / get_hint_message() / confirm_replace_session()

# setup_spyder.plugin.plugin
AITerminalPlugin(SpyderDockablePlugin)
    NAME = "setup_spyder_ai"    # igual ao nome do entry point
```

## Os auxiliares

`helpers/` não é testado, é ferramenta:

* `pending.py` — os dois modos (skip vs. falha), o ambiente dos subprocessos e
  `owning_distribution()` (qual distribuição publica `setup_spyder`). Mora aqui
  e não no `conftest.py` porque cada `conftest.py` aninhado é importado com o
  nome de módulo `conftest` e sombrearia o da raiz.
* `fake_tui.py` — TUI determinística para os testes de PTY: emite ANSI e
  Unicode, ecoa **um byte por vez**, responde ao resize, trata `Ctrl+C` e sai
  com código 42/130. Também cria um neto que dorme, para provar que
  `terminate()` leva a árvore junto.
* `fake_cli.py` — `codex`/`claude` de mentira, gravando o `argv` recebido: é o
  que prova que o comando foi montado como lista, sem shell no meio.
* `fake_pty.py` — transporte de mentira com o contrato da seção 6.2, para os
  testes de Qt não dependerem de ConPTY.
* `procutil.py` — “esse processo ainda vive?” e “abriu porta TCP?”. Usa
  `psutil` quando existe; no Windows nunca `os.kill(pid, 0)`, que lá **mata** o
  processo em vez de consultá-lo.

`tests/legacy/conftest.py` sobe um Spyder falso (`spyder`, `spyder_kernels`,
`spyder.config.fonts.MONOSPACE`, `spyder.config.manager.ConfigurationManager`)
só para aquela pasta; os testes de lá provam o launcher sem Qt nem display.

## Intermitência conhecida em `tests/e2e`

Em rodadas em que várias instâncias do Spyder sobem e são mortas em sequência
(o padrão do próprio harness), de vez em quando um teste falha com "o Spyder
morreu na subida (código 0)": o `mainwindow.main()` retorna normalmente nos
primeiros 30 s, sem traceback, sem "Spyder is already running" e sem evento de
console (`Handling signal`). Não reproduziu com `SPYDER_DEBUG=3`. Reexecute o
arquivo; se persistir isolado, aí é regressão.

## O que a suíte deliberadamente não testa

Nada que dependa de rede, conta ou credencial real. Login das CLIs e
comportamento das TUIs reais ficam para a CI por plataforma prevista na
seção 12.

A matriz de sistemas operacionais é dividida em duas metades.
`tests/unit/test_cross_platform.py` (marcador `plataforma`) roda **aqui**, no
sistema de quem executa a suíte, tudo que é *decisão* por sistema: os
marcadores PEP 508 do `pyproject.toml` avaliados contra um ambiente sintético
por SO, e os ramos `win32`/`darwin`/`linux` do código com `sys.platform`
simulado e dublês para `subprocess.Popen`, `os.killpg` e `signal.signal`.

```powershell
uv run pytest -m plataforma -v      # os três sistemas, sem sair do seu
```

O que ele existe para pegar é a classe de erro que não depende do runner — e
que a CI só denuncia depois do push, num sistema que você não tem na mesa. O
caso que motivou o arquivo: `pyqt5-qt5` 5.15.2 é a última versão com wheel de
Windows e não tem wheel `macosx arm64`; sem o piso `>=5.15.11` fora do Windows,
o `uv` fixava 5.15.2 para todo mundo e o `macos-latest` (Apple Silicon) morria
na instalação, antes do primeiro teste.

O resto continua sendo da CI: wheel que existe no índice mas não instala,
ConPTY que se comporta diferente, fonte que só existe naquele sistema.
