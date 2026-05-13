"""Provider-agnostic LLM streaming interface.

Every provider (mock, Anthropic, vLLM) emits the same event stream so the agent
runtime stays decoupled from the underlying model. Events are intentionally narrow:
a runtime needs to (a) stream tokens to the UI, (b) detect tool calls, (c) record usage.
"""
from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TextDelta:
    """Incremental text token(s) from the model."""

    type: Literal["text_delta"] = "text_delta"
    text: str = ""


@dataclass
class ToolCallRequest:
    """Model has decided to invoke a tool. Emitted once per tool call, fully formed."""

    type: Literal["tool_call"] = "tool_call"
    call_id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnEnd:
    """Marks end of one assistant turn. May or may not include tool calls."""

    type: Literal["turn_end"] = "turn_end"
    stop_reason: str = "end_turn"  # end_turn | tool_use | max_tokens | error
    tokens_in: int = 0
    tokens_out: int = 0


StreamEvent = TextDelta | ToolCallRequest | TurnEnd


@dataclass
class ToolSchema:
    """JSON-schema description of a tool. Provider adapters translate to native format."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object


class LLMClient(abc.ABC):
    """Abstract provider. Implementations: MockLLMClient, AnthropicLLMClient, VLLMClient."""

    @abc.abstractmethod
    async def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSchema],
    ) -> AsyncIterator[StreamEvent]:
        """Stream a single assistant turn.

        Args:
            system: System prompt.
            messages: OpenAI-style message history. Each item:
                {"role": "user"|"assistant"|"tool", "content": str | list[dict]}
                Tool results use role="tool" with content=str(result), tool_call_id=str.
            tools: Available tools the model may invoke.

        Yields:
            StreamEvent in the order produced by the model.
        """
        ...
        # Async generator -- never reached, here for type checker.
        yield  # pragma: no cover
