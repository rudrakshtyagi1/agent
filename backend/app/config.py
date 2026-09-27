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
