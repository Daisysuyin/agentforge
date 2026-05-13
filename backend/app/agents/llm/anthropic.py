"""Anthropic provider. Streams Claude with native tool use."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.agents.llm.base import (
    LLMClient,
    StreamEvent,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    TurnEnd,
)


class AnthropicLLMClient(LLMClient):
    """Streams from Anthropic's Messages API with tool use enabled."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key) if api_key else anthropic.AsyncAnthropic()
        self.model = model

    async def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSchema],
    ) -> AsyncIterator[StreamEvent]:
        anthropic_messages = self._to_anthropic_messages(messages)
        anthropic_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]

        # Buffers for in-progress tool_use block
        current_tool: dict[str, Any] | None = None
        current_json_buffer = ""
        tokens_in = 0
        tokens_out = 0
        stop_reason = "end_turn"

        async with self.client.messages.stream(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=anthropic_messages,
            tools=anthropic_tools or anthropic.NOT_GIVEN,
        ) as stream:
            async for event in stream:
                # See https://docs.anthropic.com/claude/reference/messages-streaming
                etype = event.type
                if etype == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        current_tool = {"id": block.id, "name": block.name}
                        current_json_buffer = ""
                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield TextDelta(text=delta.text)
                    elif delta.type == "input_json_delta":
                        current_json_buffer += delta.partial_json
                elif etype == "content_block_stop":
                    if current_tool is not None:
                        import json as _json

                        try:
                            args = _json.loads(current_json_buffer or "{}")
                        except _json.JSONDecodeError:
                            args = {}
                        yield ToolCallRequest(
                            call_id=current_tool["id"],
                            name=current_tool["name"],
                            arguments=args,
                        )
                        current_tool = None
                        current_json_buffer = ""
                elif etype == "message_delta":
                    if event.delta.stop_reason:
                        stop_reason = event.delta.stop_reason
                    if event.usage:
                        tokens_out = event.usage.output_tokens
                elif etype == "message_start":
                    if event.message.usage:
                        tokens_in = event.message.usage.input_tokens

        yield TurnEnd(stop_reason=stop_reason, tokens_in=tokens_in, tokens_out=tokens_out)

    @staticmethod
    def _to_anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate our internal OpenAI-ish history into Anthropic's content-block format.

        Tool results need to be wrapped as user-role content blocks with type=tool_result.
        """
        out: list[dict[str, Any]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            role = msg["role"]
            if role == "user":
                out.append({"role": "user", "content": msg["content"]})
                i += 1
            elif role == "assistant":
                # content may already be in block form (text + tool_use); pass through
                out.append({"role": "assistant", "content": msg["content"]})
                i += 1
            elif role == "tool":
                # Group consecutive tool results into one user message
                blocks = []
                while i < len(messages) and messages[i]["role"] == "tool":
                    tm = messages[i]
                    blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tm["tool_call_id"],
                            "content": str(tm["content"]),
                        }
                    )
                    i += 1
                out.append({"role": "user", "content": blocks})
            else:
                i += 1
        return out
