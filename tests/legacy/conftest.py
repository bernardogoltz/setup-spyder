"""Stubs for Spyder so the legacy tests do not need Spyder, Qt or a display.

Only the pieces the launcher layers touch lazily are faked: the top-level
``spyder``/``spyder_kernels`` modules (availability checks), ``MONOSPACE``
(font fallback) and ``ConfigurationManager`` (the seed writer).
"""

from __future__ import annotations

import configparser
import importlib.machinery
import os
import sys
import types
from pathlib import Path

import pytest


class FakeConfigurationManager:
    """Writes every `set` straight into ``$SPYDER_CONFDIR/config/spyder.ini``."""

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], object] = {}
        self.ini = Path(os.environ["SPYDER_CONFDIR"]) / "config" / "spyder.ini"
        self.ini.parent.mkdir(parents=True, exist_ok=True)

    def set(self, section: str, option: str, value: object) -> None:
        self.data[(section, option)] = value
        parser = configparser.ConfigParser()
        for (sec, opt), val in self.data.items():
            if not parser.has_section(sec):
                parser.add_section(sec)
            parser.set(sec, opt, repr(val))
        with self.ini.open("w", encoding="utf-8") as handle:
            parser.write(handle)

    def get(self, section: str, option: str) -> object:
        return self.data[(section, option)]


def _module(name: str, monkeypatch: pytest.MonkeyPatch, **attrs: object) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__spec__ = importlib.machinery.ModuleSpec(name, None)
    for key, value in attrs.items():
        setattr(mod, key, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


@pytest.fixture(autouse=True)
def fake_spyder(monkeypatch: pytest.MonkeyPatch) -> None:
    spyder = _module("spyder", monkeypatch, __version__="5.6.0.dev0")
    _module("spyder_kernels", monkeypatch, __version__="2.5.2")

    config = _module("spyder.config", monkeypatch)
    fonts = _module(
        "spyder.config.fonts",
        monkeypatch,
        MONOSPACE=["Menlo", "Monospace"],
    )
    manager = _module(
        "spyder.config.manager",
        monkeypatch,
        ConfigurationManager=FakeConfigurationManager,
    )
    config.fonts = fonts
    config.manager = manager
    spyder.config = config
