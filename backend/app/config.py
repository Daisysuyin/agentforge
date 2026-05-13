"""Application configuration. Env-driven, single source of truth."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Override via environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database -- SQLite for v0, swap DSN to Postgres in prod
    database_url: str = "sqlite+aiosqlite:///./agentforge.db"

    # LLM provider selection
    llm_provider: Literal["mock", "anthropic", "vllm"] = "mock"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    # vLLM endpoint (for DGX Spark deployment)
    vllm_base_url: str = "http://localhost:8000/v1"
    vllm_model: str = "meta-llama/Llama-3.3-70B-Instruct"

    # Agent runtime caps
    max_tool_calls_per_turn: int = 10
    agent_timeout_seconds: float = 60.0

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
