"""Runtime configuration for ADR Manager MCP Server."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded exclusively from environment variables and `.env`."""

    anthropic_api_key: SecretStr | None = Field(
        default=None,
        alias="ANTHROPIC_API_KEY",
        description="Anthropic API key used for Claude extraction and reasoning calls.",
    )
    adr_db_path: Path = Field(
        default=Path("~/.adr-mcp/adr.db"),
        alias="ADR_DB_PATH",
        description="Path to the local SQLite ADR database.",
    )
    adr_embedding_model: str = Field(default="voyage-3", alias="ADR_EMBEDDING_MODEL")
    adr_llm_model: str = Field(default="claude-haiku-4-5", alias="ADR_LLM_MODEL")
    adr_max_conflicts: int = Field(default=5, alias="ADR_MAX_CONFLICTS", ge=1, le=20)
    adr_conflict_threshold: float = Field(
        default=0.72,
        alias="ADR_CONFLICT_THRESHOLD",
        ge=0.0,
        le=1.0,
    )
    adr_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        alias="ADR_LOG_LEVEL",
    )
    adr_ai_timeout_seconds: float = Field(default=30.0, alias="ADR_AI_TIMEOUT_SECONDS", gt=0)
    adr_summary_token_budget: int = Field(default=80_000, alias="ADR_SUMMARY_TOKEN_BUDGET")
    adr_summary_max_depth: int = Field(default=3, alias="ADR_SUMMARY_MAX_DEPTH", ge=1, le=10)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("adr_db_path")
    @classmethod
    def expand_db_path(cls, value: Path) -> Path:
        return value.expanduser()

    def require_anthropic_api_key(self) -> str:
        """Return the configured API key or raise a clear runtime error."""
        if self.anthropic_api_key is None or not self.anthropic_api_key.get_secret_value():
            raise ValueError(
                "ANTHROPIC_API_KEY is required for AI-backed tools. "
                "Set it in the environment or in a local .env file."
            )
        return self.anthropic_api_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings factory used by the server entrypoint."""
    return Settings()
