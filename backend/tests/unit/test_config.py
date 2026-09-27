"""Unit tests — application configuration."""

import pytest
from app.config import Settings, get_settings


def test_default_settings():
    """Settings should load with correct defaults."""
    s = Settings()
    assert s.app_name == "AgentGuard"
    assert s.app_env == "development"
    assert s.debug is True
    assert s.api_v1_prefix == "/api/v1"
    assert "sqlite" in s.database_url or "postgresql" in s.database_url


def test_is_sqlite_default():
    """Default DATABASE_URL should be SQLite."""
    s = Settings()
    assert s.is_sqlite is True


def test_is_production_false_by_default():
    """Default environment should not be production."""
    s = Settings()
    assert s.is_production is False


def test_log_level_default():
    """Default log level should be INFO."""
    s = Settings()
    assert s.log_level == "INFO"


def test_get_settings_cached():
    """get_settings() should return the same cached instance on repeated calls."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
