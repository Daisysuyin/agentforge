"""vLLM provider via OpenAI-compatible chat completions.

Targets vLLM running Llama 3.3 70B Instruct on DGX Spark. The OpenAI-compatible
endpoint (default: http://localhost:8000/v1) accepts the standard tools schema.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.agents.llm.base import (
    LLMClient,
    StreamEvent,
    TextDelta,
    ToolCallRequest,
    ToolSchema,
    TurnEnd,
)


class VLLMClient(LLMClient):
    """Streams from a vLLM OpenAI-compatible endpoint with native tool calls."""

    def __init__(self, base_url: str, model: str, api_key: str = "EMPTY"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    async def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSchema],
    ) -> AsyncIterator[StreamEvent]:
        # oai_messages = [{"role": "system", "content": system}]
        # for m in messages:
        #     if m["role"] == "tool":
        #         oai_messages.append(
        #             {
        #                 "role": "tool",
        #                 "tool_call_id": m["tool_call_id"],
        #                 "content": str(m["content"]),
        #             }
        #         )
        #     else:
        #         oai_messages.append({"role": m["role"], "content": m["content"]})

        import json as _json

        oai_messages = [{"role": "system", "content": system}]
        for m in messages:
            role = m["role"]
            if role == "tool":
                oai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": m["tool_call_id"],
                        "content": str(m["content"]),
                    }
                )
            elif role == "assistant":
                # Translate Anthropic-style content blocks to OpenAI format:
                # - text blocks -> string content
                # - tool_use blocks -> tool_calls array
                content = m.get("content")
                if isinstance(content, list):
                    text_parts: list[str] = []
                    tool_calls: list[dict] = []
                    for block in content:
                        btype = block.get("type")
                        if btype == "text":
                            text_parts.append(block.get("text", ""))
                        elif btype == "tool_use":
                            tool_calls.append({
                                "id": block.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": block.get("name", ""),
                                    "arguments": _json.dumps(block.get("input", {})),
                                },
                            })
                    msg: dict = {"role": "assistant", "content": "".join(text_parts) or None}
                    if tool_calls:
                        msg["tool_calls"] = tool_calls
                    oai_messages.append(msg)
                else:
                    oai_messages.append({"role": "assistant", "content": content})
            else:
                # user or system passthrough
                oai_messages.append({"role": role, "content": m["content"]})

        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

        payload = {
            "model": self.model,
            "messages": oai_messages,
            "tools": oai_tools or None,
            "stream": True,
            "max_tokens": 4096,
        }

        # vLLM streams Server-Sent Events with `data: {...}` lines
        tool_buffers: dict[int, dict[str, Any]] = {}  # index -> {"id","name","args_str"}
        stop_reason = "end_turn"
        tokens_in = 0
        tokens_out = 0

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=120.0) as http:
            async with http.stream(
                "POST", f"{self.base_url}/chat/completions", headers=headers, json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    if text := delta.get("content"):
                        yield TextDelta(text=text)
                    for tc in delta.get("tool_calls", []) or []:
                        idx = tc.get("index", 0)
                        buf = tool_buffers.setdefault(idx, {"id": "", "name": "", "args_str": ""})
                        if tc.get("id"):
                            buf["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            buf["name"] = fn["name"]
                        if fn.get("arguments"):
                            buf["args_str"] += fn["arguments"]
                    if finish := choice.get("finish_reason"):
                        stop_reason = "tool_use" if finish == "tool_calls" else "end_turn"
                    if usage := chunk.get("usage"):
                        tokens_in = usage.get("prompt_tokens", 0)
                        tokens_out = usage.get("completion_tokens", 0)

        # Flush completed tool calls
        for buf in tool_buffers.values():
            try:
                args = json.loads(buf["args_str"] or "{}")
            except json.JSONDecodeError:
                args = {}
            yield ToolCallRequest(call_id=buf["id"], name=buf["name"], arguments=args)

        yield TurnEnd(stop_reason=stop_reason, tokens_in=tokens_in, tokens_out=tokens_out)
