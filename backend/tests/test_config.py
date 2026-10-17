"""Tests for environment-based settings (app/config.py)."""

from __future__ import annotations

import pytest

from app.config import Settings, get_settings, load_settings

_VARS = ("WP_APP_NAME", "WP_ENVIRONMENT", "WP_RUN_STORE_MAX_RUNS")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults():
    assert load_settings() == Settings()
    s = Settings()
    assert (s.app_name, s.environment, s.run_store_max_runs) == (
        "Waste-Potential API", "development", 1000,
    )


def test_environment_overrides(monkeypatch):
    monkeypatch.setenv("WP_APP_NAME", "Test API")
    monkeypatch.setenv("WP_ENVIRONMENT", " Production ")
    monkeypatch.setenv("WP_RUN_STORE_MAX_RUNS", "25")
    s = load_settings()
    assert s == Settings(app_name="Test API", environment="production", run_store_max_runs=25)


@pytest.mark.parametrize("name", _VARS)
@pytest.mark.parametrize("blank", ["", " ", "\t", "  \n "], ids=repr)
def test_blank_values_fall_back_to_defaults(monkeypatch, name, blank):
    monkeypatch.setenv(name, blank)
    assert load_settings() == Settings()


def test_all_blank_values_together_fall_back_to_defaults(monkeypatch):
    for name in _VARS:
        monkeypatch.setenv(name, "   ")
    assert load_settings() == Settings()


def test_nonblank_values_are_stripped(monkeypatch):
    monkeypatch.setenv("WP_APP_NAME", "  Test API  ")
    monkeypatch.setenv("WP_RUN_STORE_MAX_RUNS", " 7 ")
    s = load_settings()
    assert (s.app_name, s.run_store_max_runs) == ("Test API", 7)


@pytest.mark.parametrize(
    "name, value",
    [
        ("WP_ENVIRONMENT", "staging"),
        ("WP_RUN_STORE_MAX_RUNS", "lots"),
        ("WP_RUN_STORE_MAX_RUNS", "0"),
    ],
)
def test_invalid_values_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        load_settings()


def test_get_settings_is_cached_until_cleared(monkeypatch):
    first = get_settings()
    monkeypatch.setenv("WP_APP_NAME", "Changed")
    assert get_settings() is first
    get_settings.cache_clear()
    assert get_settings().app_name == "Changed"


def test_settings_are_immutable():
    with pytest.raises(Exception):
        Settings().app_name = "x"  # type: ignore[misc]
