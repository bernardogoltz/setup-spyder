from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from setup_spyder import __version__, launch, open_spyder
from setup_spyder import cli


def test_public_api_aliases() -> None:
    assert open_spyder is launch
    assert __version__ == "0.1.0"


def test_parse_args_no_launch_and_workdir() -> None:
    args = cli.parse_args(["--no-launch", "-w", "/tmp/repo"])
    assert args.no_launch is True
    assert args.keep_config is False
    assert args.workdir == "/tmp/repo"


def test_parse_args_keeps_spyder_remainder() -> None:
    args = cli.parse_args(["--", "script.py"])
    assert args.spyder_args == ["--", "script.py"]


def test_jetbrains_mono_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    font = tmp_path / "JetBrainsMono-Regular.ttf"
    font.write_bytes(b"")
    monkeypatch.setattr(cli, "FONT_DIRS", (tmp_path,))
    assert font in cli.jetbrains_mono_installed()


def test_jetbrains_mono_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "FONT_DIRS", (tmp_path,))
    assert cli.jetbrains_mono_installed() == []


def test_ensure_spyproject_creates_files(tmp_path: Path) -> None:
    spyproject = cli.ensure_spyproject(tmp_path)
    assert spyproject == tmp_path / ".spyproject"
    assert (spyproject / "config" / "workspace.ini").is_file()


def test_ensure_spyproject_reuses_existing(tmp_path: Path) -> None:
    first = cli.ensure_spyproject(tmp_path)
    marker = first / "config" / "workspace.ini"
    marker.write_text("keep-me\n")
    second = cli.ensure_spyproject(tmp_path)
    assert second == first
    assert marker.read_text() == "keep-me\n"


def test_apply_spyder_config_sets_font_and_wrap(tmp_path: Path) -> None:
    font, wrap = cli.apply_spyder_config(tmp_path)
    assert font == ["JetBrains Mono"]
    assert wrap is True
    ini = tmp_path / "config" / "spyder.ini"
    assert ini.is_file()
    text = ini.read_text()
    assert "JetBrains Mono" in text
    assert "wrap = True" in text


def test_launch_no_launch_creates_project_and_skips_gui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = MagicMock()
    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/usr/bin/spyder")

    code = launch(no_launch=True, workdir=tmp_path)

    assert code == 0
    assert (tmp_path / ".spyproject" / "config" / "workspace.ini").is_file()
    run.assert_not_called()


def test_launch_opens_spyder_with_project_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = MagicMock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(cli.subprocess, "run", run)
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/opt/spyder")

    code = launch(spyder_args=["notebook.py"], workdir=tmp_path)

    assert code == 0
    cmd = run.call_args.args[0]
    assert cmd[0] == "/opt/spyder"
    assert "--new-instance" in cmd
    assert cmd[cmd.index("-w") + 1] == str(tmp_path.resolve())
    assert cmd[cmd.index("-p") + 1] == str(tmp_path.resolve())
    assert "--conf-dir" in cmd
    assert "notebook.py" in cmd


def test_launch_missing_spyder_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    code = launch(workdir=tmp_path)
    assert code == 1


def test_launch_deletes_isolated_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    removed: list[str] = []
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/opt/spyder")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        cli.shutil, "rmtree", lambda path, ignore_errors=False: removed.append(str(path))
    )

    launch(workdir=tmp_path)

    assert removed
    assert any("setup-spyder-conf-" in path for path in removed)


def test_launch_keep_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    removed: list[str] = []
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/opt/spyder")
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(
        cli.shutil, "rmtree", lambda path, ignore_errors=False: removed.append(str(path))
    )

    launch(workdir=tmp_path, keep_config=True)

    assert removed == []


def test_launch_import_error_returns_1(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"spyder", "spyder_kernels"}:
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert launch(no_launch=True, workdir=tmp_path) == 1


def test_main_forwards_cli_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_launch(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return 0

    monkeypatch.setattr(cli, "launch", fake_launch)
    code = cli.main(["--no-launch", "--keep-config", "-w", str(tmp_path)])
    assert code == 0
    assert seen["kwargs"]["no_launch"] is True
    assert seen["kwargs"]["keep_config"] is True
    assert seen["kwargs"]["workdir"] == str(tmp_path)
