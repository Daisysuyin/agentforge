"""End-to-end runtime tests using the mock LLM provider."""
from __future__ import annotations

import pytest

from app.agents import RuntimeDone, RuntimeToolCall, RuntimeToolResult, run_agent
from app.agents.llm.mock import MockLLMClient


@pytest.mark.asyncio
async def test_runtime_create_lead_flow(seeded_session):
    db, agent, *_ = seeded_session
    events = []
    async for ev in run_agent(
        db=db,
        agent=agent,
        user_input="Please create a lead for Sarah Chen at Hexagon Labs.",
        llm=MockLLMClient(stream_delay_ms=0.0),
    ):
        events.append(ev)

    # Expect at least: text deltas, one tool_call, one tool_result, one done
    tool_calls = [e for e in events if isinstance(e, RuntimeToolCall)]
    tool_results = [e for e in events if isinstance(e, RuntimeToolResult)]
    done = [e for e in events if isinstance(e, RuntimeDone)]

    assert len(tool_calls) == 1
    assert tool_calls[0].name == "create_lead"
    assert len(tool_results) == 1
    assert tool_results[0].ok
    assert len(done) == 1
    assert done[0].trace_id


@pytest.mark.asyncio
async def test_runtime_persists_trace(seeded_session):
    db, agent, *_ = seeded_session
    async for _ev in run_agent(
        db=db,
        agent=agent,
        user_input="Search the knowledge base for pricing info.",
        llm=MockLLMClient(stream_delay_ms=0.0),
    ):
        pass

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models import Trace as TraceModel

    rows = (
        await db.execute(
            select(TraceModel)
            .options(selectinload(TraceModel.tool_calls))
            .where(TraceModel.agent_id == agent.id)
        )
    ).scalars().all()
    assert len(rows) == 1
    trace = rows[0]
    assert trace.status == "done"
    assert trace.user_input.startswith("Search")
    assert any(tc.tool_name == "search_knowledge_base" for tc in trace.tool_calls)


@pytest.mark.asyncio
async def test_runtime_unknown_tool_handled(seeded_session):
    """Even if an LLM hallucinates a tool name, runtime should not crash."""
    db, agent, *_ = seeded_session

    # Override the agent to reference no tools but force a tool call via a custom mock
    from collections.abc import AsyncIterator

    from app.agents.llm.base import (
        LLMClient,
        StreamEvent,
        TextDelta,
        ToolCallRequest,
        ToolSchema,
        TurnEnd,
    )

    class HallucinatingMock(LLMClient):
        def __init__(self):
            self.turn = 0

        async def stream(self, *, system, messages, tools) -> AsyncIterator[StreamEvent]:
            self.turn += 1
            if self.turn == 1:
                yield TextDelta(text="Calling tool. ")
                yield ToolCallRequest(call_id="c1", name="nonexistent_tool", arguments={})
                yield TurnEnd(stop_reason="tool_use", tokens_in=10, tokens_out=5)
            else:
                yield TextDelta(text="Sorry, that tool is unavailable.")
                yield TurnEnd(stop_reason="end_turn", tokens_in=10, tokens_out=5)

    events = []
    async for ev in run_agent(db=db, agent=agent, user_input="Use a fake tool.", llm=HallucinatingMock()):
        events.append(ev)

    # Should still complete with a Done event, and tool_result should mark ok=False
    bad_results = [e for e in events if isinstance(e, RuntimeToolResult) and not e.ok]
    assert len(bad_results) == 1
    assert "unknown tool" in (bad_results[0].error or "").lower()
    assert any(isinstance(e, RuntimeDone) for e in events)
