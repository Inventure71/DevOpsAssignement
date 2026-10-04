"""Explicit opt-in for relaxed playtest admission rules."""

import pytest

from backend.core.config import Config
from backend.core.paths import pinned_demo_pack_path


def test_playtest_defaults_off(monkeypatch):
    monkeypatch.delenv("PLAYTEST_MODE", raising=False)
    assert Config.from_env().playtest is False


@pytest.mark.parametrize(
    "value,expected", [("true", True), ("1", True), ("false", False), ("0", False)]
)
def test_playtest_environment_boolean(monkeypatch, value, expected):
    monkeypatch.setenv("PLAYTEST_MODE", value)
    assert Config.from_env().playtest is expected


def test_invalid_playtest_value_fails_startup(monkeypatch):
    monkeypatch.setenv("PLAYTEST_MODE", "sometimes")
    with pytest.raises(ValueError, match="PLAYTEST_MODE"):
        Config.from_env()


def test_demo_pack_defaults_to_pinned_installation(monkeypatch):
    monkeypatch.delenv("DEMO_PACK_DIR", raising=False)
    assert Config.from_env().demo_pack_dir == pinned_demo_pack_path()


def test_local_demo_pack_is_explicit_and_resolves_from_environment(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEMO_PACK_DIR", "music")
    assert Config.from_env().demo_pack_dir == tmp_path / "music"


def test_empty_demo_pack_setting_uses_pinned_installation(monkeypatch):
    monkeypatch.setenv("DEMO_PACK_DIR", "")
    assert Config.from_env().demo_pack_dir == pinned_demo_pack_path()


def test_pinned_location_is_independent_of_working_directory(monkeypatch, tmp_path):
    expected = pinned_demo_pack_path()
    monkeypatch.chdir(tmp_path)
    assert Config().demo_pack_dir == expected


@pytest.mark.parametrize("pack,sha", [("../escape", "a" * 64), ("demo", "../bad")])
def test_pinned_location_rejects_unsafe_identity(tmp_path, pack, sha):
    with pytest.raises(ValueError, match="pinned Demo pack"):
        pinned_demo_pack_path(tmp_path, {"pack": pack, "sha256": sha})


def test_missing_pack_fails_before_creating_application_database(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app import create_app

    config = Config(tmp_path / "data", demo_pack_dir=tmp_path / "missing")
    application = create_app(config, background=False)
    assert not config.database_path.exists()
    with pytest.raises(ValueError, match="setup_demo_pack.py"):
        with TestClient(application):
            pass
    assert not config.database_path.exists()


def test_launch_defaults_to_demo_without_environment(monkeypatch):
    monkeypatch.delenv("GAME_MODE", raising=False)
    assert Config.from_env().game_mode == "demo"


@pytest.mark.parametrize("mode", ["demo", "normal"])
def test_explicit_launch_mode(monkeypatch, mode):
    monkeypatch.setenv("GAME_MODE", mode)
    assert Config.from_env().game_mode == mode


@pytest.mark.parametrize("mode", ["both", "real", "", None])
def test_invalid_launch_mode_is_rejected(monkeypatch, mode):
    with pytest.raises(ValueError, match="GAME_MODE"):
        Config(game_mode=mode)
    if mode is not None:
        monkeypatch.setenv("GAME_MODE", mode)
        with pytest.raises(ValueError, match="GAME_MODE"):
            Config.from_env()
