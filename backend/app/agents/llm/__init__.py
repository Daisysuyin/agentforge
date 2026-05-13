"""LLM provider abstraction. Factory selects implementation from config."""
from __future__ import annotations

from app.agents.llm.anthropic import AnthropicLLMClient
from app.agents.llm.base import (
    LLMClient,
    StreamEvent,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    TurnEnd,
)
from app.agents.llm.mock import MockLLMClient
from app.agents.llm.vllm import VLLMClient
from app.config import get_settings


def get_llm_client() -> LLMClient:
    """Construct the configured LLM client. Defaults to mock for safety."""
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        return AnthropicLLMClient(
            api_key=settings.anthropic_api_key, model=settings.anthropic_model
        )
    if settings.llm_provider == "vllm":
        return VLLMClient(base_url=settings.vllm_base_url, model=settings.vllm_model)
    return MockLLMClient()


__all__ = [
    "AnthropicLLMClient",
    "LLMClient",
    "MockLLMClient",
    "StreamEvent",
    "TextDelta",
    "ToolCallRequest",
    "ToolSchema",
    "TurnEnd",
    "VLLMClient",
    "get_llm_client",
]
