"""Stubs for Spyder so unit tests do not need a display or real Qt."""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest


class FakeCONF:
    data: dict[tuple[str, str], object] = {}

    @classmethod
    def reset(cls) -> None:
        cls.data = {}

    @classmethod
    def set(cls, section: str, option: str, value: object) -> None:
        cls.data[(section, option)] = value
        conf_dir = Path(os.environ["SPYDER_CONFDIR"])
        ini = conf_dir / "config" / "spyder.ini"
        ini.parent.mkdir(parents=True, exist_ok=True)
        ini.write_text(
            "[appearance]\n"
            "font/family = ['JetBrains Mono']\n"
            "[editor]\n"
            "wrap = True\n"
        )

    @classmethod
    def get(cls, section: str, option: str) -> object:
        return cls.data[(section, option)]


class FakeEmptyProject:
    def __init__(self, root_path: str, parent_plugin=None) -> None:
        config = Path(root_path) / ".spyproject" / "config"
        config.mkdir(parents=True, exist_ok=True)
        (config / "workspace.ini").write_text(
            "[workspace]\nproject_type = empty-project-type\n"
        )


def _module(name: str, monkeypatch: pytest.MonkeyPatch, **attrs: object) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


@pytest.fixture(autouse=True)
def fake_spyder(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeCONF.reset()

    spyder = _module("spyder", monkeypatch, __version__="5.5.6")
    _module("spyder_kernels", monkeypatch, __version__="2.5.2")

    plugins = _module("spyder.plugins", monkeypatch)
    projects = _module("spyder.plugins.projects", monkeypatch)
    api = _module(
        "spyder.plugins.projects.api",
        monkeypatch,
        EmptyProject=FakeEmptyProject,
    )
    spyder.plugins = plugins
    plugins.projects = projects
    projects.api = api

    config = _module("spyder.config", monkeypatch)
    manager = _module("spyder.config.manager", monkeypatch, CONF=FakeCONF)
    config.manager = manager
    spyder.config = config
