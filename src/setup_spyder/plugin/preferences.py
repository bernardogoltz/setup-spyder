"""Preferences page of the AI Terminal: provider, autostart, bell, scrollback."""

from __future__ import annotations

from qtpy.QtWidgets import QGroupBox, QVBoxLayout

from spyder.api.preferences import PluginConfigPage
from spyder.api.translations import _

from setup_spyder.plugin.providers import AGENT_AUTO, AGENT_NONE, PROVIDER_ORDER


class AITerminalConfigPage(PluginConfigPage):
    """Options stored in the plugin's own config file (``CONF_FILE = True``)."""

    def setup_page(self):
        agent_group = QGroupBox(_("Agent"))
        choices = [
            (_("Automatic (the only CLI installed)"), AGENT_AUTO),
            *[(name, name) for name in PROVIDER_ORDER],
            (_("None (do not start an agent)"), AGENT_NONE),
        ]
        provider = self.create_combobox(
            _("Provider:"),
            choices,
            "provider",
            tip=_("Which CLI New session starts. --agent overrides it for one run."),
        )
        autostart = self.create_checkbox(
            _("Start the agent when Spyder opens"),
            "autostart",
            tip=_("Never applies when the choice is ambiguous or --agent none was given."),
        )
        agent_layout = QVBoxLayout()
        agent_layout.addWidget(provider)
        agent_layout.addWidget(autostart)
        agent_group.setLayout(agent_layout)

        terminal_group = QGroupBox(_("Terminal"))
        bell = self.create_checkbox(_("Audible bell"), "terminal_bell")
        scrollback = self.create_spinbox(
            _("Scrollback lines:"), "", "scrollback", min_=100, max_=200000, step=100
        )
        terminal_layout = QVBoxLayout()
        terminal_layout.addWidget(bell)
        terminal_layout.addWidget(scrollback)
        terminal_group.setLayout(terminal_layout)

        layout = QVBoxLayout()
        layout.addWidget(agent_group)
        layout.addWidget(terminal_group)
        layout.addStretch(1)
        self.setLayout(layout)
