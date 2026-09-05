"""AITerminalPlugin: the Spyder 5.x dockable plugin behind ``setup_spyder_ai``.

The plugin is the controller: it reads the launcher's environment, talks to
Preferences, Projects, WorkingDirectory and MainMenu when they exist, and
applies the autostart rule once the main window is visible. The pane itself is
:class:`~setup_spyder.plugin.main_widget.AITerminalWidget`.

No PTY backend is imported here (plan section 6.1): a missing ``pywinpty`` or
``ptyprocess`` degrades the pane, never the discovery of the plugin.
"""

from __future__ import annotations

import logging
import os

from spyder.api.config.decorators import on_conf_change
from spyder.api.plugin_registration.decorators import (
    on_plugin_available,
    on_plugin_teardown,
)
from spyder.api.plugins import Plugins, SpyderDockablePlugin
from spyder.api.translations import _
from spyder.plugins.mainmenu.api import ApplicationMenus, ToolsMenuSections

from setup_spyder.plugin.api import (
    CONF_DEFAULTS,
    CONF_VERSION,
    ENV_AUTOSTART,
    ENV_WORKDIR,
    PLUGIN_NAME,
    AITerminalActions,
)
from setup_spyder.plugin.main_widget import AITerminalWidget
from setup_spyder.plugin.preferences import AITerminalConfigPage

logger = logging.getLogger("setup_spyder.plugin")


class AITerminalPlugin(SpyderDockablePlugin):
    """A real terminal pane that runs the Codex or Claude Code CLI."""

    NAME = PLUGIN_NAME
    REQUIRES = [Plugins.Preferences]
    OPTIONAL = [
        Plugins.Editor,
        Plugins.Projects,
        Plugins.WorkingDirectory,
        Plugins.MainMenu,
    ]
    TABIFY = [Plugins.IPythonConsole]
    WIDGET_CLASS = AITerminalWidget

    CONF_SECTION = PLUGIN_NAME
    CONF_FILE = True
    CONF_DEFAULTS = CONF_DEFAULTS
    CONF_VERSION = CONF_VERSION
    CONF_WIDGET_CLASS = AITerminalConfigPage

    CAN_BE_DISABLED = True
    REQUIRE_WEB_WIDGETS = True
    RAISE_AND_FOCUS = True

    # ---- SpyderDockablePlugin API --------------------------------------------

    @staticmethod
    def get_name():
        return _("AI Terminal")

    def get_description(self):
        return _("Run the Codex or Claude Code CLI in a real terminal, in the project.")

    def get_icon(self):
        return self.create_icon("ipython_console")

    def on_initialize(self):
        widget = self.get_widget()
        widget.sig_state_changed.connect(self._on_state_changed)
        workdir = os.environ.get(ENV_WORKDIR)
        if workdir and os.path.isdir(workdir):
            widget.set_working_directory(os.path.abspath(workdir))

    def on_mainwindow_visible(self):
        widget = self.get_widget()
        resolution = widget.refresh_providers()
        if self._should_autostart(resolution):
            logger.info(
                "AI Terminal autostart: %s (%s)", resolution.provider.name, resolution.reason
            )
            widget.start_session(resolution.provider.name)

    def on_close(self, cancelable=False):
        self.get_widget().close_session()
        return True

    def update_font(self):
        self.get_widget().apply_appearance()

    def update_style(self):
        self.get_widget().apply_appearance()

    # ---- Other plugins (always in available/teardown pairs) -------------------

    @on_plugin_available(plugin=Plugins.Preferences)
    def on_preferences_available(self):
        self.get_plugin(Plugins.Preferences).register_plugin_preferences(self)

    @on_plugin_teardown(plugin=Plugins.Preferences)
    def on_preferences_teardown(self):
        self.get_plugin(Plugins.Preferences).deregister_plugin_preferences(self)

    @on_plugin_available(plugin=Plugins.Projects)
    def on_projects_available(self):
        projects = self.get_plugin(Plugins.Projects)
        projects.sig_project_loaded.connect(self._on_project_loaded)
        projects.sig_project_closed.connect(self._on_project_closed)
        if not os.environ.get(ENV_WORKDIR):
            active = projects.get_active_project_path()
            if active:
                self.get_widget().set_working_directory(active)

    @on_plugin_teardown(plugin=Plugins.Projects)
    def on_projects_teardown(self):
        projects = self.get_plugin(Plugins.Projects)
        projects.sig_project_loaded.disconnect(self._on_project_loaded)
        projects.sig_project_closed.disconnect(self._on_project_closed)

    @on_plugin_available(plugin=Plugins.MainMenu)
    def on_main_menu_available(self):
        mainmenu = self.get_plugin(Plugins.MainMenu)
        mainmenu.add_item_to_application_menu(
            self.get_widget().get_action(AITerminalActions.NewSession),
            menu_id=ApplicationMenus.Tools,
            section=ToolsMenuSections.Extras,
        )

    @on_plugin_teardown(plugin=Plugins.MainMenu)
    def on_main_menu_teardown(self):
        mainmenu = self.get_plugin(Plugins.MainMenu)
        mainmenu.remove_item_from_application_menu(
            AITerminalActions.NewSession, menu_id=ApplicationMenus.Tools
        )

    @on_conf_change(option="scrollback")
    def _on_scrollback_changed(self, value):
        self.get_widget().apply_appearance()

    # ---- Public API -----------------------------------------------------------

    def start_session(self, provider=None):
        """Start a session, raising the pane (used by the Tools menu action)."""
        self.switch_to_plugin()
        self.get_widget().start_session(provider)

    def close_session(self):
        self.get_widget().close_session()

    # ---- Private ----------------------------------------------------------------

    def _should_autostart(self, resolution) -> bool:
        if resolution.provider is None or not resolution.autostart:
            return False
        if os.environ.get(ENV_AUTOSTART, "1").strip() == "0":
            return False
        return bool(self.get_conf("autostart"))

    def _on_state_changed(self, state):
        logger.debug("AI Terminal state: %s", state)

    def _on_project_loaded(self, path):
        if path:
            self.get_widget().set_working_directory(path)

    def _on_project_closed(self, *args):
        widget = self.get_widget()
        workdir = os.environ.get(ENV_WORKDIR)
        widget.set_working_directory(workdir if workdir else os.getcwd())
