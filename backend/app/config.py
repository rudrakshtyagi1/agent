"""
AgentGuard application configuration.

All settings are loaded from environment variables (or a .env file via
python-dotenv). Secrets must never be placed in source code — only in
environment-specific .env files or secrets managers.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    app_name: str = Field(default="AgentGuard", description="Application name.")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", description="Deployment environment."
    )
    debug: bool = Field(default=True, description="Enable debug mode.")
    api_v1_prefix: str = Field(default="/api/v1", description="API v1 route prefix.")

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    database_url: str = Field(
        default="sqlite+aiosqlite:///./agentguard_dev.db",
        description=(
            "Async-compatible database URL. "
            "SQLite (sqlite+aiosqlite:///) for local/testing; "
            "PostgreSQL (postgresql+asyncpg://...) for production."
        ),
    )

    # ------------------------------------------------------------------ #
    # External services (Phase 2+)
    # ------------------------------------------------------------------ #
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL (used in Phase 2+).",
    )
    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant vector DB URL (used in Phase 3+ RAG).",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL (used in Phase 2+ LLM evaluation).",
    )
    ollama_model: str = Field(
        default="llama3.2",
        description="Default Ollama model name.",
    )

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Application log level."
    )

    # ------------------------------------------------------------------ #
    # Computed helpers
    # ------------------------------------------------------------------ #
    # One API process/worker is supported; inbox rows survive restarts.
    monitor_keys: dict[str, str] = Field(default_factory=dict, repr=False)
    monitor_capture_payloads: bool = False
    monitor_queue_capacity: int = Field(default=1000, ge=1, le=100000)
    monitor_sample_rate: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
    monitor_retention_days: int = Field(default=7, ge=1, le=365)
    monitor_poll_seconds: float = Field(default=1, ge=0.05, le=60)
    monitor_window: int = Field(default=50, ge=5, le=500)
    monitor_min_samples: int = Field(default=5, ge=1, le=500)
    monitor_failure_rate: float = Field(default=0.2, gt=0, le=1, allow_inf_nan=False)
    monitor_latency_ms: int = Field(default=5000, ge=1)

    @property
    def is_production(self) -> bool:
        """Return True when running in production environment."""
        return self.app_env == "production"

    @property
    def is_sqlite(self) -> bool:
        """Return True when the configured database is SQLite."""
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()
