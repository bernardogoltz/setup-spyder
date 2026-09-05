"""AI Terminal: an external Spyder 5.x plugin that runs codex/claude in a real PTY.

Nothing here imports Qt, Spyder or a PTY backend: the entry point
``setup_spyder_ai = setup_spyder.plugin.plugin:AITerminalPlugin`` loads the
plugin module lazily, and the platform backend is imported only when a session
starts (see ``main_widget.create_pty_worker``).
"""

from __future__ import annotations

PLUGIN_NAME = "setup_spyder_ai"

__all__ = ["PLUGIN_NAME"]
