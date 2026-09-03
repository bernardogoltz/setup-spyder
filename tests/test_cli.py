from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from setup_spyder import __version__, launch, open_spyder
from setup_spyder import cli


def test_public_api_aliases() -> None:
    assert open_spyder is launch
    assert __version__ == "0.2.0"


def test_parse_args_no_launch_and_workdir() -> None:
    args = cli.parse_args(["--no-launch", "-w", "/tmp/repo"])
    assert args.no_launch is True
    assert args.keep_config is False
    assert args.workdir == "/tmp/repo"


def test_parse_args_keeps_spyder_remainder() -> None:
    args = cli.parse_args(["--", "script.py"])
    assert args.spyder_args == ["--", "script.py"]


def test_font_dirs_on_windows_look_at_the_two_font_folders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\ana\AppData\Local")
    monkeypatch.setenv("WINDIR", r"C:\Windows")

    dirs = cli.font_dirs()

    assert [d.name for d in dirs] == ["Fonts", "Fonts"]
    assert "AppData" in str(dirs[0])
    assert str(dirs[1]).endswith("Fonts")


def test_font_dirs_on_macos_look_at_the_library_folders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    assert Path("/Library/Fonts") in cli.font_dirs()


def test_font_dirs_on_linux_look_at_share_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.sys, "platform", "linux")
    assert Path("/usr/share/fonts") in cli.font_dirs()


def test_remove_tree_deletes_read_only_files(tmp_path: Path) -> None:
    tree = tmp_path / "conf"
    (tree / "config").mkdir(parents=True)
    locked = tree / "config" / "spyder.ini"
    locked.write_text("[appearance]\n")
    locked.chmod(0o444)

    cli.remove_tree(tree)

    assert not tree.exists()


def test_write_launcher_is_utf8(tmp_path: Path) -> None:
    launcher = cli.write_launcher(tmp_path, ["spyder", "-w", str(tmp_path)], [".venv"])
    assert "do not edit by hand" in launcher.read_text(encoding="utf-8")


def test_enable_utf8_output_reconfigures_a_legacy_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    class FakeStream:
        encoding = "cp1252"

        def reconfigure(self, **kwargs: str) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(cli.sys, "stdout", FakeStream())
    monkeypatch.setattr(cli.sys, "stderr", FakeStream())

    cli.enable_utf8_output()

    assert calls == [{"encoding": "utf-8", "errors": "replace"}] * 2


def test_enable_utf8_output_leaves_a_utf8_console_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStream:
        encoding = "UTF-8"

        def reconfigure(self, **kwargs: str) -> None:
            raise AssertionError("must not reconfigure a UTF-8 stream")

    monkeypatch.setattr(cli.sys, "stdout", FakeStream())
    monkeypatch.setattr(cli.sys, "stderr", FakeStream())

    cli.enable_utf8_output()


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
    font, wrap = cli.apply_spyder_config(tmp_path, font_family="JetBrains Mono")
    assert font == ["JetBrains Mono"]
    assert wrap is True
    ini = tmp_path / "config" / "spyder.ini"
    assert ini.is_file()
    text = ini.read_text()
    assert "JetBrains Mono" in text
    assert "wrap = True" in text


def test_resolve_editor_font_uses_jetbrains_when_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    font = tmp_path / "JetBrainsMono-Regular.ttf"
    font.write_bytes(b"")
    monkeypatch.setattr(cli, "FONT_DIRS", (tmp_path,))
    family, hits = cli.resolve_editor_font()
    assert family == "JetBrains Mono"
    assert font in hits


def test_resolve_editor_font_falls_back_to_spyder_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "FONT_DIRS", (tmp_path,))
    family, hits = cli.resolve_editor_font()
    assert family == "Menlo"
    assert hits == []


def test_apply_spyder_config_falls_back_when_jetbrains_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "jetbrains_mono_installed", lambda: [])
    font, wrap = cli.apply_spyder_config(tmp_path)
    assert font == ["Menlo"]
    assert wrap is True
    text = (tmp_path / "config" / "spyder.ini").read_text()
    assert "Menlo" in text
    assert "JetBrains Mono" not in text


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


def capture_launcher(
    monkeypatch: pytest.MonkeyPatch, which: str | None = "/opt/spyder"
) -> dict[str, object]:
    """Run Spyder into a mock, keeping the generated launcher before cleanup."""
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        source = Path(cmd[1]).read_text()
        captured["cmd"] = cmd
        captured["source"] = source
        line = next(
            ln for ln in source.splitlines() if ln.startswith("sys.argv = ")
        )
        captured["argv"] = ast.literal_eval(line.removeprefix("sys.argv = "))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli.shutil, "which", lambda _: which)
    return captured


def test_launch_opens_spyder_with_project_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = capture_launcher(monkeypatch)

    code = launch(spyder_args=["notebook.py"], workdir=tmp_path)

    assert code == 0
    assert captured["cmd"][0] == sys.executable
    argv = captured["argv"]
    assert argv[0] == "/opt/spyder"
    assert "--new-instance" in argv
    assert argv[argv.index("-w") + 1] == str(tmp_path.resolve())
    assert argv[argv.index("-p") + 1] == str(tmp_path.resolve())
    assert "--conf-dir" in argv
    assert "notebook.py" in argv


def test_launch_without_spyder_binary_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The console script is only argv[0]; the launcher runs on sys.executable."""
    captured = capture_launcher(monkeypatch, which=None)

    assert launch(workdir=tmp_path) == 0
    assert captured["argv"][0] == "spyder"


def test_launch_hides_clutter_from_project_pane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = capture_launcher(monkeypatch)

    launch(workdir=tmp_path, hide=[".secrets,notes.txt"], show=[".github"])

    line = next(
        ln
        for ln in str(captured["source"]).splitlines()
        if ln.startswith("HIDDEN = ")
    )
    hidden = ast.literal_eval(line.removeprefix("HIDDEN = "))
    assert {".venv", "dist", "uv.lock", ".secrets", "notes.txt"} <= set(hidden)
    assert ".github" not in hidden


def test_resolve_hidden_paths_defaults_plus_hide_minus_show() -> None:
    hidden = cli.resolve_hidden_paths(hide=["a, b", "c"], show=[".venv"])
    assert {"a", "b", "c"} <= set(hidden)
    assert ".venv" not in hidden
    assert hidden == sorted(hidden)


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
