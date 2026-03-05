"""Application settings with validation.

Uses pydantic-settings for environment variable parsing with .env file support.
All settings are validated at import time — missing required values fail fast.
"""

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """PD3r application configuration."""

    # Required
    openai_api_key: str = Field(description="OpenAI API key")

    # LLM configuration
    openai_default_model: str = Field(default="gpt-4o")
    openai_rewrite_model: str = Field(default="gpt-4o")

    # Database
    database_url: str = Field(
        default="sqlite:///./output/.sessions/checkpoints.db",
        description="Database URL for session checkpointing",
    )

    # Knowledge base
    vector_store_path: str = Field(
        default="./knowledge/vector_store",
        description="Path to ChromaDB vector store",
    )

    # Session limits
    max_session_age_hours: int = Field(default=72)
    max_tokens_per_session: int = Field(default=500_000)

    # API configuration
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
    )
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)

    # Testing controls
    stop_at: str | None = Field(default=None, description="Stop at phase for testing")
    skip_qa: bool = Field(default=False)
    tracing: bool = Field(default=False)
    max_drafts: int = Field(default=0)

    # Paths
    output_dir: str = Field(default="./output")
    session_dir: str = Field(default="./output/.sessions")

    model_config = {
        "env_prefix": "PD3R_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        # Map OPENAI_API_KEY (no prefix) to openai_api_key
        "env_nested_delimiter": "__",
    }

    def __init__(self, **kwargs):
        # Allow OPENAI_API_KEY without PD3R_ prefix.
        # Check both os.environ and .env file since pydantic-settings
        # only looks for PD3R_OPENAI_API_KEY with the prefix.
        if "openai_api_key" not in kwargs:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                from dotenv import dotenv_values
                env_values = dotenv_values(".env")
                api_key = env_values.get("OPENAI_API_KEY")
            if api_key:
                kwargs["openai_api_key"] = api_key
        super().__init__(**kwargs)

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir)

    @property
    def session_path(self) -> Path:
        return Path(self.session_dir)


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings. Validates on first call."""
    return Settings()
