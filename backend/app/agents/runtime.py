"""Agent runtime: the streaming loop.

Responsibilities:
  1. Build the message history from prior turns.
  2. Stream LLM events to the caller (TextDelta, ToolCallRequest, ToolResult).
  3. Dispatch tool calls against the registry, capturing results in the message history.
  4. Persist the full trace + per-tool-call records to the database.
  5. Enforce caps: max_tool_calls_per_turn, agent_timeout_seconds.

Exposes a single async-generator entrypoint `run_agent` that yields RuntimeEvent objects.
The HTTP layer streams these as Server-Sent Events.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMClient, TextDelta, ToolCallRequest, TurnEnd, get_llm_client
from app.agents.tools import ToolContext, ToolResult, registry
from app.config import get_settings
from app.models import AgentDefinition, ToolCallRecord, Trace


# ---------------------------------------------------------------------------- #
# Event types streamed from runtime -> HTTP -> UI
# ---------------------------------------------------------------------------- #
@dataclass
class RuntimeTextDelta:
    type: Literal["text_delta"] = "text_delta"
    text: str = ""


@dataclass
class RuntimeToolCall:
    type: Literal["tool_call"] = "tool_call"
    call_id: str = ""
    name: str = ""
    arguments: dict[str, Any] | None = None


@dataclass
class RuntimeToolResult:
    type: Literal["tool_result"] = "tool_result"
    call_id: str = ""
    name: str = ""
    ok: bool = True
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class RuntimeDone:
    type: Literal["done"] = "done"
    trace_id: str = ""
    final_text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    duration_ms: float = 0.0


@dataclass
class RuntimeError:
    type: Literal["error"] = "error"
    message: str = ""
    trace_id: str | None = None


RuntimeEvent = (
    RuntimeTextDelta | RuntimeToolCall | RuntimeToolResult | RuntimeDone | RuntimeError
)


def event_to_json(ev: RuntimeEvent) -> str:
    """Serialize a runtime event for SSE transport."""
    return json.dumps(asdict(ev), default=str)


# ---------------------------------------------------------------------------- #
# Core runtime
# ---------------------------------------------------------------------------- #
async def run_agent(
    *,
    db: AsyncSession,
    agent: AgentDefinition,
    user_input: str,
    llm: LLMClient | None = None,
) -> AsyncIterator[RuntimeEvent]:
    """Run one full agent turn -> tool dispatch loop -> final answer.

    Persists a Trace (and all ToolCallRecord rows) regardless of success/failure.
    Yields events suitable for streaming to the UI.
    """
    settings = get_settings()
    llm = llm or get_llm_client()
    started = time.perf_counter()

    # Persist trace skeleton up front so even partial runs are auditable.
    trace = Trace(agent_id=agent.id, user_input=user_input, status="running")
    db.add(trace)
    await db.flush()

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_input}]
    tools = registry.list_for_agent(agent.tool_names or [])
    tool_schemas = [t.schema() for t in tools]
    accumulated_text = ""
    total_in = 0
    total_out = 0
    tool_call_seq = 0

    try:
        async with asyncio.timeout(settings.agent_timeout_seconds):
            for _turn in range(settings.max_tool_calls_per_turn + 1):
                # --- stream one assistant turn -----------------------------------
                pending_tool_calls: list[ToolCallRequest] = []
                turn_text = ""

                async for event in llm.stream(
                    system=agent.system_prompt,
                    messages=messages,
                    tools=tool_schemas,
                ):
                    if isinstance(event, TextDelta):
                        turn_text += event.text
                        accumulated_text += event.text
                        yield RuntimeTextDelta(text=event.text)
                    elif isinstance(event, ToolCallRequest):
                        pending_tool_calls.append(event)
                        yield RuntimeToolCall(
                            call_id=event.call_id, name=event.name, arguments=event.arguments
                        )
                    elif isinstance(event, TurnEnd):
                        total_in += event.tokens_in
                        total_out += event.tokens_out
                        stop_reason = event.stop_reason

                # Append assistant message in Anthropic-style content blocks
                assistant_content: list[dict[str, Any]] = []
                if turn_text:
                    assistant_content.append({"type": "text", "text": turn_text})
                for tc in pending_tool_calls:
                    assistant_content.append(
                        {
                            "type": "tool_use",
                            "id": tc.call_id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                messages.append({"role": "assistant", "content": assistant_content or turn_text})

                # --- terminate loop if no tool calls -----------------------------
                if not pending_tool_calls:
                    break

                # --- dispatch tool calls -----------------------------------------
                if tool_call_seq + len(pending_tool_calls) > settings.max_tool_calls_per_turn:
                    yield RuntimeError(
                        message=f"Exceeded max_tool_calls_per_turn ({settings.max_tool_calls_per_turn})",
                        trace_id=trace.id,
                    )
                    raise RuntimeError("tool call cap exceeded")

                ctx = ToolContext(
                    db=db,
                    agent_id=agent.id,
                    trace_id=trace.id,
                    guardrails=agent.guardrails or {},
                )
                for tc in pending_tool_calls:
                    tool = registry.get(tc.name)
                    if tool is None:
                        result = ToolResult(ok=False, error=f"unknown tool: {tc.name}")
                    else:
                        result = await tool.execute(tc.arguments, ctx)

                    db.add(
                        ToolCallRecord(
                            trace_id=trace.id,
                            sequence=tool_call_seq,
                            tool_name=tc.name,
                            arguments_json=json.dumps(tc.arguments),
                            result_json=json.dumps(result.data) if result.ok else None,
                            error=result.error,
                            duration_ms=result.duration_ms,
                        )
                    )
                    tool_call_seq += 1

                    yield RuntimeToolResult(
                        call_id=tc.call_id,
                        name=tc.name,
                        ok=result.ok,
                        data=result.data,
                        error=result.error,
                        duration_ms=result.duration_ms,
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.call_id,
                            "content": json.dumps(result.to_payload()),
                        }
                    )

        # --- success ------------------------------------------------------------
        trace.set_messages(messages)
        trace.final_output = accumulated_text
        trace.status = "done"
        trace.tokens_in = total_in
        trace.tokens_out = total_out
        duration_ms = (time.perf_counter() - started) * 1000
        trace.duration_ms = duration_ms
        await db.flush()
        yield RuntimeDone(
            trace_id=trace.id,
            final_text=accumulated_text,
            tokens_in=total_in,
            tokens_out=total_out,
            duration_ms=duration_ms,
        )

    except TimeoutError:
        trace.status = "error"
        trace.error = f"timeout after {settings.agent_timeout_seconds}s"
        trace.set_messages(messages)
        await db.flush()
        yield RuntimeError(message=trace.error, trace_id=trace.id)

    except Exception as e:  # noqa: BLE001
        trace.status = "error"
        trace.error = f"{type(e).__name__}: {e}"
        trace.set_messages(messages)
        await db.flush()
        yield RuntimeError(message=trace.error, trace_id=trace.id)
