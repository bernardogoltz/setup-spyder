from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from setup_spyder import integration
from setup_spyder.cli import REPO_URL


def test_parse_args_defaults() -> None:
    args = integration.parse_args([])
    assert args.ref is None
    assert args.local is False
    assert args.fresh is False
    assert args.no_launch is False
    assert args.keep is False
    assert args.spyder_args == []


def test_parse_args_flags_and_remainder() -> None:
    args = integration.parse_args(["--fresh", "--ref", "develop", "--", "main.py"])
    assert args.fresh is True
    assert args.ref == "develop"
    assert args.spyder_args == ["--", "main.py"]


def test_dependency_spec_github(tmp_path: Path) -> None:
    assert integration.dependency_spec(tmp_path, ref=None, local=False) == f"git+{REPO_URL}"


def test_dependency_spec_github_with_ref(tmp_path: Path) -> None:
    spec = integration.dependency_spec(tmp_path, ref="v1.2.3", local=False)
    assert spec == f"git+{REPO_URL}@v1.2.3"


def test_dependency_spec_local_uses_repo_path(tmp_path: Path) -> None:
    assert integration.dependency_spec(tmp_path, ref="develop", local=True) == str(tmp_path)


def test_child_env_drops_inherited_venv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIRTUAL_ENV", "/somewhere/.venv")
    monkeypatch.setenv("SPYDER_CONFDIR", "/somewhere/conf")
    monkeypatch.setenv("PATH", "/usr/bin")
    env = integration.child_env()
    assert "VIRTUAL_ENV" not in env
    assert "SPYDER_CONFDIR" not in env
    assert env["PATH"] == "/usr/bin"


def test_scaffold_fixture_creates_and_reuses(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture_integration"
    integration.scaffold_fixture(fixture)
    pyproject = fixture / "pyproject.toml"
    main_py = fixture / "main.py"
    assert integration.FIXTURE_NAME in pyproject.read_text()

    main_py.write_text("# edited\n")
    integration.scaffold_fixture(fixture)
    assert main_py.read_text() == "# edited\n"


def test_clean_fixture_keeps_checked_in_files(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture_integration"
    integration.scaffold_fixture(fixture)
    (fixture / "README.md").write_text("keep-me\n")
    (fixture / ".venv").mkdir()

    removed = integration.clean_fixture(fixture)

    assert set(removed) == {"pyproject.toml", "main.py", ".venv"}
    assert (fixture / "README.md").read_text() == "keep-me\n"
    assert not (fixture / "pyproject.toml").exists()


def test_find_repo_root_from_nested_dir(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / integration.FIXTURE_RELPATH).mkdir(parents=True)
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    assert integration.find_repo_root(nested) == root.resolve()


def test_run_integration_requires_uv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(integration.shutil, "which", lambda name: None)
    assert integration.run_integration() == 1


def test_uv_install_hints_cover_both_platforms() -> None:
    assert "install.ps1" in integration.UV_INSTALL_WINDOWS
    assert "install.sh" in integration.UV_INSTALL_POSIX


@pytest.fixture()
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    (root / integration.FIXTURE_RELPATH).mkdir(parents=True)
    monkeypatch.setattr(integration.shutil, "which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr(integration, "find_repo_root", lambda start=None: root)
    return root


def _record_runs(monkeypatch: pytest.MonkeyPatch, returncode: int = 0) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, returncode, stdout="0.1.0\n", stderr="")

    monkeypatch.setattr(integration.subprocess, "run", fake_run)
    return calls


def test_run_integration_installs_from_github_then_launches(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_runs(monkeypatch)

    assert integration.run_integration() == 0

    add, check, launch = calls
    assert add[:4] == ["/usr/bin/uv", "add", "--refresh-package", "setup-spyder"]
    assert add[-1] == f"git+{REPO_URL}"
    assert check[:4] == ["/usr/bin/uv", "run", "python", "-c"]
    assert launch == ["/usr/bin/uv", "run", "setup-spyder"]


def test_run_integration_cleans_the_fixture_afterwards(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_runs(monkeypatch)
    fixture = fake_repo / integration.FIXTURE_RELPATH
    (fixture / "README.md").write_text("keep-me\n")

    assert integration.run_integration() == 0

    assert not (fixture / "pyproject.toml").exists()
    assert not (fixture / "main.py").exists()
    assert (fixture / "README.md").read_text() == "keep-me\n"


def test_run_integration_keeps_the_fixture_with_keep(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_runs(monkeypatch)
    fixture = fake_repo / integration.FIXTURE_RELPATH

    assert integration.run_integration(keep=True) == 0

    assert (fixture / "pyproject.toml").is_file()
    assert (fixture / "main.py").is_file()


def test_run_integration_cleans_up_after_a_failure(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_runs(monkeypatch, returncode=1)
    fixture = fake_repo / integration.FIXTURE_RELPATH

    assert integration.run_integration() == 1
    assert not (fixture / "pyproject.toml").exists()


def test_run_integration_no_launch_and_extra_args(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_runs(monkeypatch)

    assert integration.run_integration(no_launch=True, spyder_args=["--", "main.py"]) == 0

    assert calls[-1] == ["/usr/bin/uv", "run", "setup-spyder", "--no-launch", "--", "main.py"]


def test_run_integration_local_installs_repo_path(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_runs(monkeypatch)

    assert integration.run_integration(local=True) == 0

    assert calls[0][-1] == str(fake_repo)


def test_run_integration_stops_when_uv_add_fails(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _record_runs(monkeypatch, returncode=1)

    assert integration.run_integration() == 1
    assert len(calls) == 1


def test_run_integration_fresh_recreates_fixture(
    fake_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _record_runs(monkeypatch)
    fixture = fake_repo / integration.FIXTURE_RELPATH
    (fixture / "main.py").write_text("# stale\n")

    assert integration.run_integration(fresh=True, keep=True) == 0
    assert "# stale" not in (fixture / "main.py").read_text()
