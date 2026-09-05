"""Dockable AI Terminal pane: xterm.js in a QWebEngineView, fed by a PTY worker.

Everything the pane needs is local to the process: the web page is built from
the bundled assets and handed to the view with ``setHtml``; JavaScript talks to
Python through ``QWebChannel``; the child CLI runs in a pseudo-terminal owned
by a :class:`~setup_spyder.plugin.pty_worker.PTYWorker`. No network, no
listener, no shell.
"""

from __future__ import annotations

import base64
import codecs
import json
import logging
import os
import sys
from pathlib import Path

from qtpy.QtCore import QEvent, QFile, QIODevice, QObject, Qt, Signal, Slot
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from spyder.api.translations import _
from spyder.api.widgets.main_widget import PluginMainWidget
from spyder.config.user import NoDefault

from setup_spyder.plugin.api import (
    CONF_OPTIONS,
    ENV_AGENT,
    ENV_WORKDIR,
    PLUGIN_NAME,
    AITerminalActions,
    AITerminalOptionsMenuSections,
    AITerminalToolbarSections,
    AITerminalWidgets,
    SessionState,
)
from setup_spyder.plugin.providers import (
    AGENT_AUTO,
    AGENT_NONE,
    KNOWN_PROVIDERS,
    PROVIDER_ORDER,
    REASON_AMBIGUOUS,
    REASON_DISABLED,
    REASON_MISSING,
    AgentResolution,
    build_command,
    default_shell,
    normalize_request,
    resolve_provider,
)

logger = logging.getLogger("setup_spyder.plugin")

ASSETS_DIR = Path(__file__).parent / "assets"
QWEBCHANNEL_RESOURCE = ":/qtwebchannel/qwebchannel.js"

# The page runs in a QtWebEngine process, which doesn't see the fonts Qt
# registered for the widgets, so the ones Spyder bundles have to travel with
# the page itself.
BUNDLED_WEBFONTS = (
    ("JetBrains Mono", "JetBrainsMono-Regular.woff2", 400, "normal"),
    ("JetBrains Mono", "JetBrainsMono-Italic.woff2", 400, "italic"),
    ("JetBrains Mono", "JetBrainsMono-Bold.woff2", 700, "normal"),
    ("JetBrains Mono", "JetBrainsMono-BoldItalic.woff2", 700, "italic"),
)

INSTALL_HINT = (
    "Install the PTY backend in the project environment: "
    "uv add pywinpty (Windows) / uv add ptyprocess (Linux, macOS), "
    "or pip install pywinpty / pip install ptyprocess, then restart Spyder."
)


def create_pty_worker(**kwargs):
    """Single creation point of the transport; the backend is imported here.

    Tests replace this function to inject a fake transport, so the widget must
    never reach ``pty_worker`` by any other path.
    """
    from setup_spyder.plugin import pty_worker

    return pty_worker.create_pty_worker(**kwargs)


class TerminalBridge(QObject):
    """The object JavaScript sees through QWebChannel.

    Slots are called by the page; signals push data to it. The ``sig_*``
    Python-side signals re-emit what the page sent so the widget can connect
    to them like to any other Qt signal.
    """

    # Python -> JavaScript
    sig_output = Signal(str)
    sig_clear = Signal(bool)
    sig_options = Signal(str)
    sig_focus = Signal()

    # JavaScript -> Python (re-emitted from the slots below)
    sig_input = Signal(str)
    sig_resized = Signal(int, int)
    sig_ready = Signal(int, int)
    sig_bell = Signal()

    @Slot(str)
    def send_input(self, text):
        self.sig_input.emit(text)

    @Slot(int, int)
    def resize(self, rows, cols):
        self.sig_resized.emit(int(rows), int(cols))

    @Slot(int, int)
    def ready(self, rows, cols):
        self.sig_ready.emit(int(rows), int(cols))

    @Slot()
    def bell(self):
        self.sig_bell.emit()

    @Slot(str)
    def log(self, message):
        logger.warning("terminal page: %s", message)


def read_asset(name: str) -> str:
    return (ASSETS_DIR / name).read_text(encoding="utf-8")


def read_qwebchannel_js() -> str:
    """Qt's own ``qwebchannel.js``, read from the Qt resource system."""
    resource = QFile(QWEBCHANNEL_RESOURCE)
    if not resource.open(QIODevice.ReadOnly):
        raise RuntimeError(f"Qt resource {QWEBCHANNEL_RESOURCE} is not available")
    try:
        return bytes(resource.readAll()).decode("utf-8")
    finally:
        resource.close()


def font_faces_css() -> str:
    """``@font-face`` rules, as data URIs, for the fonts Spyder ships."""
    try:
        from spyder.config.fonts import get_bundled_font_path
    except Exception as exc:  # embedded fonts are cosmetic; never block the pane
        logger.debug("bundled fonts unavailable: %s", exc)
        return ""

    rules = []
    for family, fname, weight, style in BUNDLED_WEBFONTS:
        try:
            data = Path(get_bundled_font_path("webfonts", fname)).read_bytes()
        except OSError as exc:
            logger.debug("font file unavailable: %s", exc)
            continue
        source = base64.b64encode(data).decode("ascii")
        rules.append(
            f'@font-face {{ font-family: "{family}"; font-weight: {weight};'
            f' font-style: {style}; font-display: block;'
            f' src: url(data:font/woff2;base64,{source}) format("woff2"); }}'
        )
    return "\n".join(rules)


def build_page(options: dict) -> str:
    """Inline every asset into ``terminal.html`` so the page needs no URL."""
    theme = options.get("theme") or {}
    payload = json.dumps(options).replace("<", "\\u003c")
    page = read_asset("terminal.html")
    replacements = {
        "/*__FONT_FACES__*/": font_faces_css(),
        "/*__XTERM_CSS__*/": read_asset("xterm.css"),
        "/*__QWEBCHANNEL_JS__*/": read_qwebchannel_js(),
        "/*__XTERM_JS__*/": read_asset("xterm.js"),
        "/*__XTERM_FIT_JS__*/": read_asset("xterm-addon-fit.js"),
        "/*__TERMINAL_JS__*/": read_asset("terminal.js"),
        "__OPTIONS_JSON__": payload,
        "__BACKGROUND__": theme.get("background", "#000000"),
    }
    for marker, content in replacements.items():
        page = page.replace(marker, content)
    return page


def terminal_appearance(scrollback: int) -> dict:
    """xterm options derived from Spyder's palette and editor font."""
    theme = {}
    try:
        from spyder.utils.palette import QStylePalette

        theme = {
            "background": QStylePalette.COLOR_BACKGROUND_1,
            "foreground": QStylePalette.COLOR_TEXT_1,
            "cursor": QStylePalette.COLOR_TEXT_1,
            "cursorAccent": QStylePalette.COLOR_BACKGROUND_1,
            "selectionBackground": QStylePalette.COLOR_ACCENT_2,
            "selectionForeground": QStylePalette.COLOR_TEXT_1,
        }
    except Exception as exc:  # palette is cosmetic; never block the pane
        logger.debug("palette unavailable: %s", exc)

    family, size = "monospace", 10
    try:
        from spyder.config.gui import get_font

        font = get_font()
        family = font.family() or family
        size = font.pointSize() if font.pointSize() > 0 else size
    except Exception as exc:
        logger.debug("font unavailable: %s", exc)

    return {
        "theme": theme,
        "fontFamily": f'"{family}", "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace',
        "fontSize": max(round(size * 96 / 72), 8),
        "lineHeight": 1.15,
        "scrollback": int(scrollback),
        "windowsMode": sys.platform == "win32",
    }


class DirectoryLabel(QLabel):
    """Keep the project directory readable without widening the dock."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._path = ""
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def set_path(self, path: str) -> None:
        self._path = path
        self.setToolTip(path)
        self.setAccessibleName(_("Directory for new sessions: %s") % path)
        self._elide_path()

    def _elide_path(self) -> None:
        self.setText(self.fontMetrics().elidedText(
            self._path, Qt.ElideLeft, max(self.contentsRect().width(), 0)
        ))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide_path()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._elide_path()


class AITerminalWidget(PluginMainWidget):
    """The pane: provider selector, session actions, status line and terminal."""

    CONF_SECTION = PLUGIN_NAME
    ENABLE_SPINNER = False

    sig_state_changed = Signal(str)
    """Emitted with the new state: idle | starting | running | exited | error."""

    def __init__(self, name=PLUGIN_NAME, plugin=None, parent=None):
        super().__init__(name, plugin, parent)

        # Session state
        self._local_conf: dict = {}
        self._state = SessionState.Idle
        self._worker = None
        self._resolution: AgentResolution | None = None
        self._session_provider: str | None = None
        self._session_argv: list[str] = []
        self._exit_code: int | None = None
        self._error_message = ""
        self._hint_message = ""
        self._workdir = self._initial_workdir()
        self._rows, self._cols = 24, 80
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._page_ready = False
        self._pending_output: list[str] = []
        self._selector_guard = False

        # Widgets
        self._selector = QComboBox(self)
        self._selector.ID = AITerminalWidgets.ProviderSelector
        self._selector.setToolTip(_("Agent CLI to start with New session"))
        for choice in (AGENT_AUTO, *PROVIDER_ORDER):
            self._selector.addItem(choice)
        self._selector.currentIndexChanged.connect(self._on_selector_changed)

        self._state_label = QLabel(self)
        self._state_label.setTextFormat(Qt.PlainText)
        self._directory_label = DirectoryLabel(self)
        self._status_bar = QWidget(self)
        self._status_bar.setObjectName("ai_terminal_status")
        status_layout = QHBoxLayout(self._status_bar)
        status_layout.setContentsMargins(10, 5, 10, 5)
        status_layout.setSpacing(12)
        status_layout.addWidget(self._state_label)
        status_layout.addWidget(self._directory_label, 1)
        self._hint_label = QLabel(self)
        self._hint_label.setTextFormat(Qt.PlainText)
        self._hint_label.setWordWrap(True)
        self._hint_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._error_label = QLabel(self)
        self._error_label.setTextFormat(Qt.PlainText)
        self._error_label.setWordWrap(True)
        self._error_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._style_labels()

        self._bridge = TerminalBridge(self)
        self._bridge.sig_input.connect(self._on_page_input)
        self._bridge.sig_resized.connect(self._on_page_resized)
        self._bridge.sig_ready.connect(self._on_page_ready)
        self._bridge.sig_bell.connect(self._on_bell)
        self._view = None
        self._channel = None
        self._placeholder = None
        self._create_view()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._view if self._view is not None else self._placeholder, 1)
        layout.addWidget(self._hint_label)
        layout.addWidget(self._error_label)
        layout.addWidget(self._status_bar)
        self.setLayout(layout)

        self._select_initial_provider()
        self._refresh_labels()

        if plugin is None:
            # Outside Spyder (tests, standalone use) nobody drives the
            # PluginMainWidget bootstrap, so mirror what SpyderDockablePlugin
            # does: setup(), update_actions(), _setup(), render_toolbars().
            self.setup()
            self.update_actions()
            self._setup()
            self.render_toolbars()

    # ---- PluginMainWidget API ----------------------------------------------

    def get_title(self):
        return _("AI Terminal")

    def get_focus_widget(self):
        return self._view if self._view is not None else self

    def setup(self):
        new_session = self.create_action(
            AITerminalActions.NewSession,
            text=_("New session"),
            tip=_("Start the selected agent CLI in a new terminal session"),
            icon=self.create_icon("run"),
            triggered=lambda: self.start_session(),
            register_shortcut=False,
            overwrite=True,
        )
        restart = self.create_action(
            AITerminalActions.Restart,
            text=_("Restart"),
            tip=_("Close the current session and start it again"),
            icon=self.create_icon("restart"),
            triggered=self.restart,
            register_shortcut=False,
            overwrite=True,
        )
        interrupt = self.create_action(
            AITerminalActions.Interrupt,
            text=_("Interrupt"),
            tip=_("Send Ctrl+C to the running CLI"),
            icon=self.create_icon("stop"),
            triggered=self.interrupt,
            register_shortcut=False,
            overwrite=True,
        )
        clear = self.create_action(
            AITerminalActions.Clear,
            text=_("Clear"),
            tip=_("Clear the terminal screen (the session keeps running)"),
            icon=self.create_icon("editclear"),
            triggered=self.clear,
            register_shortcut=False,
            overwrite=True,
        )
        close_session = self.create_action(
            AITerminalActions.CloseSession,
            text=_("Close session"),
            tip=_("Terminate the CLI and its child processes"),
            icon=self.create_icon("close_pane"),
            triggered=self.close_session,
            register_shortcut=False,
            overwrite=True,
        )

        toolbar = self.get_main_toolbar()
        self.add_item_to_toolbar(
            self._selector, toolbar=toolbar, section=AITerminalToolbarSections.Provider
        )
        for action in (new_session, restart, interrupt, close_session):
            self.add_item_to_toolbar(
                action, toolbar=toolbar, section=AITerminalToolbarSections.Session
            )
        self.add_item_to_toolbar(
            clear, toolbar=toolbar, section=AITerminalToolbarSections.Screen
        )

        options_menu = self.get_options_menu()
        for action in (new_session, restart, interrupt, clear, close_session):
            self.add_item_to_menu(
                action, menu=options_menu, section=AITerminalOptionsMenuSections.Session
            )

    def update_actions(self):
        alive = self.has_live_session()
        started = self._session_argv != []
        self.get_action(AITerminalActions.Interrupt).setEnabled(alive)
        self.get_action(AITerminalActions.CloseSession).setEnabled(alive)
        self.get_action(AITerminalActions.Restart).setEnabled(started)
        self.get_action(AITerminalActions.Clear).setEnabled(self._view is not None)

    def on_close(self):
        """Called from ``closeEvent``: never leave the child behind."""
        self.close_session()

    # ---- Configuration without a plugin ---------------------------------

    def get_conf(self, option, default=NoDefault, section=None):
        if self._plugin is None and section in (None, self.CONF_SECTION):
            fallback = CONF_OPTIONS.get(option) if default is NoDefault else default
            return self._local_conf.get(option, fallback)
        return super().get_conf(option, default=default, section=section)

    def set_conf(self, option, value, section=None, recursive_notification=True):
        if self._plugin is None and section in (None, self.CONF_SECTION):
            self._local_conf[option] = value
            return
        super().set_conf(
            option, value, section=section, recursive_notification=recursive_notification
        )

    # ---- Public API --------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    def has_live_session(self) -> bool:
        worker = self._worker
        if worker is None:
            return False
        try:
            return bool(worker.is_alive())
        except Exception:
            return False

    def get_provider_selector(self) -> QComboBox:
        return self._selector

    def get_state_label(self) -> QLabel:
        return self._state_label

    def get_error_message(self) -> str:
        return self._error_message

    def get_hint_message(self) -> str:
        return self._hint_message

    def get_working_directory(self) -> str:
        return self._workdir

    def set_working_directory(self, path) -> None:
        """Directory for *new* sessions; a running session is never moved."""
        self._workdir = os.fspath(path) if path else os.getcwd()
        self._refresh_labels()

    def set_provider(self, name: str) -> None:
        """Select a provider; with a live session, ask before replacing it."""
        choice = self._selector_value(name)
        if choice is None:
            raise ValueError(f"unknown provider {name!r}")
        current = self._selector.currentText()
        if choice == current:
            return
        if self.has_live_session():
            if not self.confirm_replace_session():
                return
            self._set_selector(choice)
            self.close_session()
            self.start_session(choice)
            return
        self._set_selector(choice)

    def confirm_replace_session(self) -> bool:
        """Ask the user whether the running session may be closed."""
        answer = QMessageBox.question(
            self,
            _("AI Terminal"),
            _(
                "A session is still running. Close it and start the selected "
                "provider instead?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return answer == QMessageBox.Yes

    def refresh_providers(self) -> AgentResolution:
        """Re-scan PATH and refresh the hint; never starts anything."""
        requested = os.environ.get(ENV_AGENT) or None
        try:
            resolution = resolve_provider(
                requested=requested, preference=self.get_conf("provider")
            )
        except ValueError as exc:
            logger.warning("%s; falling back to automatic selection", exc)
            resolution = resolve_provider(requested=None, preference=self.get_conf("provider"))
        self._resolution = resolution
        self._hint_message = self._hint_for(resolution)
        self._refresh_labels()
        return resolution

    def start_session(self, provider: str | None = None) -> None:
        """Start the CLI (or the plain shell when no CLI is available)."""
        if self.has_live_session():
            self.close_session()

        chosen, hint = self._choose_provider(provider)
        if chosen is not None:
            try:
                argv = build_command(KNOWN_PROVIDERS[chosen])
            except FileNotFoundError as exc:
                logger.warning("%s", exc)
                chosen, hint = None, str(exc)
                argv = default_shell()
        else:
            argv = default_shell()
        self._hint_message = hint
        self._error_message = ""
        self._exit_code = None
        self._session_provider = chosen
        self._session_argv = list(argv)
        self._decoder.reset()
        self._reset_screen()
        self._set_state(SessionState.Starting)

        cwd = self._workdir if os.path.isdir(self._workdir) else os.getcwd()
        if cwd != self._workdir:
            self._hint_message = _("Directory %s does not exist; using %s.") % (
                self._workdir,
                cwd,
            )
        try:
            worker = create_pty_worker(parent=self)
            self._attach_worker(worker)
            worker.start(list(argv), cwd=cwd, env=None)
        except Exception as exc:
            self._fail(exc)
            return
        try:
            worker.resize(self._rows, self._cols)
        except Exception as exc:
            logger.debug("initial resize failed: %s", exc)
        self._set_state(SessionState.Running)
        self._bridge.sig_focus.emit()

    def restart(self) -> None:
        provider = self._session_provider
        self.close_session()
        self.start_session(provider)

    def interrupt(self) -> None:
        if self.has_live_session():
            self._worker.interrupt()

    def clear(self) -> None:
        self._bridge.sig_clear.emit(False)

    def close_session(self) -> None:
        worker = self._worker
        if worker is None:
            return
        if self.has_live_session():
            try:
                worker.terminate(grace_period=2.0)
            except Exception as exc:
                logger.error("terminate failed: %s", exc)
        if self._state in (SessionState.Starting, SessionState.Running):
            self._set_state(SessionState.Exited)
        self.update_actions()

    def send_input(self, text: str | bytes) -> None:
        if not self.has_live_session():
            return
        data = text if isinstance(text, bytes) else str(text).encode("utf-8")
        try:
            self._worker.write(data)
        except Exception as exc:
            self._fail(exc)

    def resize_terminal(self, rows: int, cols: int) -> None:
        self._rows, self._cols = max(int(rows), 1), max(int(cols), 1)
        if self.has_live_session():
            try:
                self._worker.resize(self._rows, self._cols)
            except Exception as exc:
                logger.debug("resize failed: %s", exc)

    def apply_appearance(self) -> None:
        """Re-send theme, font and scrollback to the page (font/theme change)."""
        options = terminal_appearance(self.get_conf("scrollback"))
        self._bridge.sig_options.emit(json.dumps(options))
        self._style_labels()

    def focus_terminal(self) -> None:
        if self._view is not None:
            self._view.setFocus()
        self._bridge.sig_focus.emit()

    # ---- Web view ----------------------------------------------------------

    def _create_view(self) -> None:
        try:
            from qtpy.QtWebChannel import QWebChannel
            from qtpy.QtWebEngineWidgets import QWebEnginePage, QWebEngineView

            class TerminalPage(QWebEnginePage):
                """Forward the page's console to the Python log (diagnostics)."""

                def javaScriptConsoleMessage(self, level, message, line, source):
                    logger.log(
                        logging.ERROR if int(level) >= 2 else logging.DEBUG,
                        "terminal page (line %s): %s",
                        line,
                        message,
                    )

            view = QWebEngineView(self)
            view.setContextMenuPolicy(Qt.NoContextMenu)
            view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            page = TerminalPage(view)
            view.setPage(page)
            channel = QWebChannel(page)
            channel.registerObject("bridge", self._bridge)
            page.setWebChannel(channel)
            options = terminal_appearance(self.get_conf("scrollback"))
            page.setHtml(build_page(options))
        except Exception as exc:
            logger.error("terminal view unavailable: %s", exc)
            self._placeholder = QWidget(self)
            self._error_message = _(
                "The terminal view could not be created (%s). Spyder must run "
                "with web widgets enabled (do not pass --no-web-widgets)."
            ) % exc
            return
        self._view = view
        self._channel = channel

    def _on_page_ready(self, rows: int, cols: int) -> None:
        self._page_ready = True
        if rows > 0 and cols > 0:
            self.resize_terminal(rows, cols)
        pending, self._pending_output = self._pending_output, []
        for chunk in pending:
            self._bridge.sig_output.emit(chunk)

    def _on_page_input(self, text: str) -> None:
        self.send_input(text)

    def _on_page_resized(self, rows: int, cols: int) -> None:
        self.resize_terminal(rows, cols)

    def _on_bell(self) -> None:
        if self.get_conf("terminal_bell"):
            QApplication.beep()

    def _push_output(self, text: str) -> None:
        if not text:
            return
        if self._page_ready:
            self._bridge.sig_output.emit(text)
        else:
            self._pending_output.append(text)

    def _reset_screen(self) -> None:
        self._pending_output = []
        self._bridge.sig_clear.emit(True)

    # ---- Worker signals ----------------------------------------------------

    def _attach_worker(self, worker) -> None:
        self._detach_worker()
        self._worker = worker
        worker.sig_output.connect(self._on_worker_output)
        worker.sig_exited.connect(self._on_worker_exited)
        worker.sig_error.connect(self._on_worker_error)

    def _detach_worker(self) -> None:
        worker, self._worker = self._worker, None
        if worker is None:
            return
        for signal, slot in (
            (worker.sig_output, self._on_worker_output),
            (worker.sig_exited, self._on_worker_exited),
            (worker.sig_error, self._on_worker_error),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _on_worker_output(self, data: bytes) -> None:
        self._push_output(self._decoder.decode(bytes(data)))

    def _on_worker_exited(self, code: int) -> None:
        if self.sender() is not None and self.sender() is not self._worker:
            return
        self._exit_code = int(code)
        self._push_output(self._decoder.decode(b"", final=True))
        self._push_output(
            "\r\n\x1b[2m[" + _("session ended with exit code %d") % code + "]\x1b[0m\r\n"
        )
        if self._state != SessionState.Error:
            self._set_state(SessionState.Exited)
        self.update_actions()

    def _on_worker_error(self, message: str) -> None:
        if self.sender() is not None and self.sender() is not self._worker:
            return
        self._error_message = str(message)
        self._set_state(SessionState.Error)
        self.update_actions()

    def _fail(self, exc: BaseException) -> None:
        """Backend failure: show it in the pane, with the suggested action."""
        cause = str(exc) or exc.__class__.__name__
        logger.error("AI Terminal could not start the session: %s", cause)
        self._error_message = f"{cause}. {INSTALL_HINT}"
        self._push_output(f"\r\n\x1b[31m{cause}\x1b[0m\r\n{INSTALL_HINT}\r\n")
        worker, self._worker = self._worker, None
        if worker is not None:
            try:
                if worker.is_alive():
                    worker.terminate(grace_period=0.5)
            except Exception:
                pass
        self._set_state(SessionState.Error)
        self.update_actions()

    # ---- Providers and state -------------------------------------------------

    def _initial_workdir(self) -> str:
        workdir = os.environ.get(ENV_WORKDIR)
        if workdir and os.path.isdir(workdir):
            return os.path.abspath(workdir)
        return os.getcwd()

    def _selector_value(self, name: str | None) -> str | None:
        try:
            normalized = normalize_request(name)
        except ValueError:
            return None
        if normalized in (None, AGENT_NONE):
            return AGENT_AUTO
        return normalized

    def _set_selector(self, choice: str) -> None:
        index = self._selector.findText(choice)
        if index < 0:
            return
        self._selector_guard = True
        try:
            self._selector.setCurrentIndex(index)
        finally:
            self._selector_guard = False

    def _on_selector_changed(self, index: int) -> None:
        if self._selector_guard or index < 0:
            return
        choice = self._selector.itemText(index)
        if self.has_live_session():
            previous = self._session_provider or AGENT_AUTO
            if not self.confirm_replace_session():
                self._set_selector(previous)
                return
            self.close_session()
            self.start_session(choice)

    def _select_initial_provider(self) -> None:
        requested = os.environ.get(ENV_AGENT)
        choice = self._selector_value(requested) if requested else None
        if choice in (None, AGENT_AUTO):
            choice = self._selector_value(self.get_conf("provider")) or AGENT_AUTO
        self._set_selector(choice)

    def _choose_provider(self, provider: str | None) -> tuple[str | None, str]:
        """Provider name to start and the hint to show (empty when all is well)."""
        if provider is None:
            selected = self._selector.currentText()
            provider = selected if selected in KNOWN_PROVIDERS else None
        if provider is not None:
            name = normalize_request(provider)
            if name == AGENT_NONE:
                return None, self._hint_for(resolve_provider(requested=AGENT_NONE))
            resolution = resolve_provider(requested=name)
        else:
            resolution = self.refresh_providers()
        self._resolution = resolution
        if resolution.provider is not None:
            return resolution.provider.name, ""
        return None, self._hint_for(resolution)

    def _hint_for(self, resolution: AgentResolution) -> str:
        names = ", ".join(PROVIDER_ORDER)
        if resolution.reason == REASON_MISSING:
            if resolution.requested:
                return _(
                    "%s was not found on PATH. Install the CLI or pick another "
                    "provider; New session opens your shell meanwhile."
                ) % resolution.requested
            return _(
                "No agent CLI found on PATH (%s). Install one and click New "
                "session; until then New session opens your shell."
            ) % names
        if resolution.reason == REASON_AMBIGUOUS:
            return _(
                "Both %s are installed. Pick one in the selector and click New "
                "session (nothing starts automatically)."
            ) % names
        if resolution.reason == REASON_DISABLED:
            return _("Agent disabled (--agent none). New session opens your shell.")
        return ""

    def _set_state(self, state: str) -> None:
        self._state = state
        self._refresh_labels()
        self.update_actions()
        self.sig_state_changed.emit(state)

    def _refresh_labels(self) -> None:
        state = self._state
        detail = ""
        if state == SessionState.Idle:
            detail = _("no session")
        elif state in (SessionState.Starting, SessionState.Running):
            detail = self._session_provider or ""
            if not detail and self._session_argv:
                detail = Path(self._session_argv[0]).name
        elif state == SessionState.Exited and self._exit_code is not None:
            detail = _("code %d") % self._exit_code
        elif state == SessionState.Error:
            detail = _("see message above")
        text = f"{state} · {detail}" if detail else state
        self._state_label.setText(text)
        self._state_label.setToolTip(text)
        self._directory_label.set_path(self._workdir)
        self._hint_label.setText(self._hint_message)
        self._hint_label.setVisible(bool(self._hint_message))
        self._error_label.setText(self._error_message)
        self._error_label.setVisible(bool(self._error_message))

    def _style_labels(self) -> None:
        try:
            from spyder.utils.palette import QStylePalette, SpyderPalette

            self._state_label.setStyleSheet(
                f"color: {QStylePalette.COLOR_TEXT_1}; font-weight: 600;"
            )
            self._directory_label.setStyleSheet(
                f"color: {QStylePalette.COLOR_TEXT_4};"
            )
            self._status_bar.setStyleSheet(
                "QWidget#ai_terminal_status {"
                f"border-top: 1px solid {QStylePalette.COLOR_BACKGROUND_4};"
                "}"
            )
            self._hint_label.setStyleSheet(
                f"color: {SpyderPalette.COLOR_WARN_2}; padding: 6px 10px;"
            )
            self._error_label.setStyleSheet(
                f"color: {SpyderPalette.COLOR_ERROR_2}; padding: 6px 10px;"
            )
        except Exception as exc:
            logger.debug("label style skipped: %s", exc)
