"""Explicit opt-in for relaxed playtest admission rules."""
import pytest

from backend.core.config import Config


def test_playtest_defaults_off(monkeypatch):
    monkeypatch.delenv('PLAYTEST_MODE', raising=False)
    assert Config.from_env().playtest is False


@pytest.mark.parametrize('value,expected', [('true', True), ('1', True), ('false', False), ('0', False)])
def test_playtest_environment_boolean(monkeypatch, value, expected):
    monkeypatch.setenv('PLAYTEST_MODE', value)
    assert Config.from_env().playtest is expected


def test_invalid_playtest_value_fails_startup(monkeypatch):
    monkeypatch.setenv('PLAYTEST_MODE', 'sometimes')
    with pytest.raises(ValueError, match='PLAYTEST_MODE'):
        Config.from_env()
