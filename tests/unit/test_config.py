"""Deployment settings and explicit opt-in for relaxed playtest admission rules."""

import pytest

from backend.core.config import Config
from backend.core.paths import pinned_demo_pack_path


def test_environment_config_uses_deployment_path_port_and_secure_cookie(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PORT", "9000")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    config = Config.from_env()
    assert config.data_dir == tmp_path
    assert config.database_path == tmp_path / "whos_on_repeat.sqlite3"
    assert config.port == 9000 and config.cookie_secure is True


@pytest.mark.parametrize(
    "setting,value",
    [("PORT", "70000"), ("COOKIE_SECURE", "sometimes"), ("SETUP_TIMEOUT_MS", "9999")],
)
def test_invalid_deployment_setting_fails_startup(monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    with pytest.raises(ValueError, match=setting):
        Config.from_env()


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


@pytest.mark.parametrize("value", [None, ""], ids=["absent", "empty"])
def test_demo_pack_defaults_to_pinned_installation(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("DEMO_PACK_DIR", raising=False)
    else:
        monkeypatch.setenv("DEMO_PACK_DIR", value)
    assert Config.from_env().demo_pack_dir == pinned_demo_pack_path()


def test_local_demo_pack_is_explicit_and_resolves_from_environment(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEMO_PACK_DIR", "music")
    assert Config.from_env().demo_pack_dir == tmp_path / "music"


def test_pinned_location_is_independent_of_working_directory(monkeypatch, tmp_path):
    expected = pinned_demo_pack_path()
    monkeypatch.chdir(tmp_path)
    assert Config().demo_pack_dir == expected


@pytest.mark.parametrize("pack,sha", [("../escape", "a" * 64), ("demo", "../bad")])
def test_pinned_location_rejects_unsafe_identity(tmp_path, pack, sha):
    with pytest.raises(ValueError, match="pinned Demo pack"):
        pinned_demo_pack_path(tmp_path, {"pack": pack, "sha256": sha})


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
