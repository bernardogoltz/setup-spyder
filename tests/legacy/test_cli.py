"""Legacy 0.2.0 behaviours that `tests/unit` does not already cover.

Runs with the fake Spyder from the sibling ``conftest.py``: the parent never
imports Spyder, and the child bootstrap is replaced by a recorded
``subprocess.run``. Argument parsing, the public signature, the child command
and the profile seed are covered in ``tests/unit`` and are not repeated here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from setup_spyder import __version__, cli, launch, launcher, open_spyder, perfil

pytestmark = [pytest.mark.legacy]


def test_public_api_aliases() -> None:
    assert open_spyder is launch
    assert __version__ == "0.3.0"


# Fonts ----------------------------------------------------------------------


def test_font_dirs_on_windows_look_at_the_two_font_folders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perfil.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\ana\AppData\Local")
    monkeypatch.setenv("WINDIR", r"C:\Windows")

    dirs = cli.font_dirs()

    assert [d.name for d in dirs] == ["Fonts", "Fonts"]
    assert "AppData" in str(dirs[0])
    assert str(dirs[1]).endswith("Fonts")


def test_font_dirs_on_macos_look_at_the_library_folders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(perfil.sys, "platform", "darwin")
    assert Path("/Library/Fonts") in cli.font_dirs()


def test_font_dirs_on_linux_look_at_share_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(perfil.sys, "platform", "linux")
    assert Path("/usr/share/fonts") in cli.font_dirs()


def test_jetbrains_mono_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    font = tmp_path / "JetBrainsMono-Regular.ttf"
    font.write_bytes(b"")
    monkeypatch.setattr(perfil, "font_dirs", lambda: (tmp_path,))
    assert font in cli.jetbrains_mono_installed()


def test_jetbrains_mono_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(perfil, "font_dirs", lambda: (tmp_path,))
    assert cli.jetbrains_mono_installed() == []


def test_resolve_editor_font_uses_jetbrains_when_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    font = tmp_path / "JetBrainsMono-Regular.ttf"
    font.write_bytes(b"")
    monkeypatch.setattr(perfil, "font_dirs", lambda: (tmp_path,))
    family, hits = cli.resolve_editor_font()
    assert family == "JetBrains Mono"
    assert font in hits


def test_resolve_editor_font_falls_back_to_spyder_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(perfil, "font_dirs", lambda: (tmp_path,))
    family, hits = cli.resolve_editor_font()
    assert family == "Menlo"
    assert hits == []


# Filesystem and console helpers --------------------------------------------


def test_remove_tree_deletes_read_only_files(tmp_path: Path) -> None:
    tree = tmp_path / "conf"
    (tree / "config").mkdir(parents=True)
    locked = tree / "config" / "spyder.ini"
    locked.write_text("[appearance]\n")
    locked.chmod(0o444)

    cli.remove_tree(tree)

    assert not tree.exists()


def test_write_launcher_is_utf8(tmp_path: Path) -> None:
    script = launcher.write_launcher(tmp_path, ["spyder", "-w", str(tmp_path)], [".venv"])
    text = script.read_text(encoding="utf-8")
    assert "do not edit by hand" in text
    assert "from spyder.app.start import main" in text


def test_enable_utf8_output_reconfigures_a_legacy_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    class FakeStream:
        encoding = "cp1252"

        def reconfigure(self, **kwargs: str) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(sys, "stdout", FakeStream())
    monkeypatch.setattr(sys, "stderr", FakeStream())

    cli.enable_utf8_output()

    assert calls == [{"encoding": "utf-8", "errors": "replace"}] * 2


def test_enable_utf8_output_leaves_a_utf8_console_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeStream:
        encoding = "UTF-8"

        def reconfigure(self, **kwargs: str) -> None:
            raise AssertionError("must not reconfigure a UTF-8 stream")

    monkeypatch.setattr(sys, "stdout", FakeStream())
    monkeypatch.setattr(sys, "stderr", FakeStream())

    cli.enable_utf8_output()


# Seed with the fake CONF ---------------------------------------------------


def test_seed_profile_writes_font_and_wrap(tmp_path: Path) -> None:
    assert perfil.seed_profile(tmp_path, font_family="JetBrains Mono") is True
    text = (tmp_path / "config" / "spyder.ini").read_text(encoding="utf-8")
    assert "JetBrains Mono" in text
    assert "wrap = True" in text
    assert perfil.seed_profile(tmp_path, font_family="JetBrains Mono") is False


def test_seed_profile_falls_back_when_jetbrains_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(perfil, "font_dirs", lambda: (tmp_path / "no-fonts",))
    assert perfil.seed_profile(tmp_path) is True
    text = (tmp_path / "config" / "spyder.ini").read_text(encoding="utf-8")
    assert "Menlo" in text
    assert "JetBrains Mono" not in text


# launch() with a recorded child --------------------------------------------


def record_child(monkeypatch: pytest.MonkeyPatch, returncode: int = 0) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = kwargs.get("env")
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    return captured


def test_launch_no_launch_creates_project_and_only_seeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = record_child(monkeypatch)

    code = launch(no_launch=True, workdir=tmp_path)

    assert code == 0
    assert (tmp_path / ".spyproject" / "config" / "workspace.ini").is_file()
    assert "--seed-only" in captured["cmd"]


def test_launch_opens_spyder_with_project_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = record_child(monkeypatch)

    code = launch(spyder_args=["notebook.py"], workdir=tmp_path)

    assert code == 0
    cmd = captured["cmd"]
    assert cmd[:3] == [sys.executable, "-m", "setup_spyder.bootstrap"]
    assert cmd[cmd.index("-w") + 1] == str(tmp_path.resolve())
    assert cmd[cmd.index("-p") + 1] == str(tmp_path.resolve())
    assert cmd[cmd.index("--conf-dir") + 1] == str(tmp_path.resolve() / perfil.CONF_DIRNAME)
    assert "--new-instance" not in cmd, "project profile respects single instance"
    assert cmd[-1] == "notebook.py"
    assert "--seed-only" not in cmd


def test_launch_ephemeral_forces_a_new_instance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = record_child(monkeypatch)
    assert launch(workdir=tmp_path, ephemeral=True) == 0
    assert "--new-instance" in captured["cmd"]


def test_launch_hides_clutter_from_project_pane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = record_child(monkeypatch)

    launch(workdir=tmp_path, hide=[".secrets,notes.txt"], show=[".github"])

    hidden = set(captured["env"]["SETUP_SPYDER_HIDDEN"].split(perfil.os.pathsep))
    assert {".venv", "dist", "uv.lock", ".secrets", "notes.txt"} <= hidden
    assert ".github" not in hidden


def test_launch_forwards_the_agent_to_the_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = record_child(monkeypatch)
    launch(workdir=tmp_path, agent="none")
    assert captured["env"]["SETUP_SPYDER_AGENT"] == "none"
    assert captured["env"]["SETUP_SPYDER_AUTOSTART"] == "0"


def test_launch_returns_the_child_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_child(monkeypatch, returncode=3)
    assert launch(workdir=tmp_path) == 3


def test_launch_deletes_the_ephemeral_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    removed: list[str] = []
    record_child(monkeypatch)
    monkeypatch.setattr(
        perfil.shutil, "rmtree", lambda path, ignore_errors=False: removed.append(str(path))
    )

    launch(workdir=tmp_path, ephemeral=True)

    assert removed
    assert any("setup-spyder-conf-" in path for path in removed)


def test_launch_keep_config_keeps_the_ephemeral_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    removed: list[str] = []
    record_child(monkeypatch)
    monkeypatch.setattr(
        perfil.shutil, "rmtree", lambda path, ignore_errors=False: removed.append(str(path))
    )

    launch(workdir=tmp_path, ephemeral=True, keep_config=True)

    assert removed == []


def test_launch_never_deletes_the_project_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    removed: list[str] = []
    record_child(monkeypatch)
    monkeypatch.setattr(
        perfil.shutil, "rmtree", lambda path, ignore_errors=False: removed.append(str(path))
    )

    launch(workdir=tmp_path)

    assert removed == []
    assert (tmp_path / perfil.CONF_DIRNAME).is_dir()


def test_launch_reset_profile_wipes_only_the_project_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_child(monkeypatch)
    stale = tmp_path / perfil.CONF_DIRNAME / "config" / "spyder.ini"
    stale.parent.mkdir(parents=True)
    stale.write_text("[main]\n", encoding="utf-8")
    witness = tmp_path / "importante.txt"
    witness.write_text("keep-me\n", encoding="utf-8")

    assert launch(workdir=tmp_path, reset_profile=True) == 0

    assert not stale.exists()
    assert (tmp_path / perfil.CONF_DIRNAME).is_dir()
    assert witness.read_text(encoding="utf-8") == "keep-me\n"


def test_launch_reset_profile_refuses_a_custom_conf_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = record_child(monkeypatch)
    custom = tmp_path / "meu perfil"
    (custom / "config").mkdir(parents=True)
    (custom / "config" / "spyder.ini").write_text("[main]\n", encoding="utf-8")

    assert launch(workdir=tmp_path, conf_dir=custom, reset_profile=True) == 1

    assert (custom / "config" / "spyder.ini").is_file()
    assert "cmd" not in captured, "nothing may start after a refused reset"


def test_launch_missing_spyder_returns_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delitem(sys.modules, "spyder")
    monkeypatch.setattr(launcher, "find_spec", lambda name: None)
    captured = record_child(monkeypatch)

    assert launch(no_launch=True, workdir=tmp_path) == 1
    assert "cmd" not in captured
