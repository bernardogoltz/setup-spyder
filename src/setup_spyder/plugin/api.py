"""Identifiers, configuration defaults and environment contract of the AI Terminal."""

from __future__ import annotations

PLUGIN_NAME = "setup_spyder_ai"

# Environment variables set by the ``setup-spyder`` launcher (plan section 5.2).
ENV_AGENT = "SETUP_SPYDER_AGENT"
ENV_WORKDIR = "SETUP_SPYDER_WORKDIR"
ENV_AUTOSTART = "SETUP_SPYDER_AUTOSTART"


class AITerminalActions:
    NewSession = "new_session"
    Restart = "restart"
    Interrupt = "interrupt"
    Clear = "clear"
    CloseSession = "close_session"


class AITerminalWidgets:
    ProviderSelector = "setup_spyder_ai_provider_selector"


class AITerminalToolbarSections:
    Provider = "setup_spyder_ai_provider_section"
    Session = "setup_spyder_ai_session_section"
    Screen = "setup_spyder_ai_screen_section"


class AITerminalOptionsMenuSections:
    Session = "setup_spyder_ai_options_session_section"


class SessionState:
    Idle = "idle"
    Starting = "starting"
    Running = "running"
    Exited = "exited"
    Error = "error"


CONF_SECTION = PLUGIN_NAME
CONF_VERSION = "1.0.0"
CONF_OPTIONS = {
    "provider": "auto",
    "autostart": True,
    "terminal_bell": True,
    "scrollback": 5000,
}
CONF_DEFAULTS = [(CONF_SECTION, dict(CONF_OPTIONS))]
