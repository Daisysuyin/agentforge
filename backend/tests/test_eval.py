"""Eval harness smoke test."""
from __future__ import annotations

import pytest

from app.eval import EvalCase, run_eval


@pytest.mark.asyncio
async def test_eval_runs_against_seeded_agent(seeded_session):
    db, agent, *_ = seeded_session
    cases = [
        EvalCase(
            case_id="t1",
            agent_name=agent.name,
            user_input="Please create a lead for Jane Doe at Acme Corp.",
            expected_tools=["create_lead"],
            expected_text_contains=[],
        ),
        EvalCase(
            case_id="t2",
            agent_name=agent.name,
            user_input="Search the knowledge base for pricing info.",
            expected_tools=["search_knowledge_base"],
            expected_text_contains=[],
        ),
    ]
    report = await run_eval(db=db, cases=cases, use_judge=False, concurrency=2)
    assert len(report.cases) == 2
    assert report.tool_accuracy == 1.0
    assert report.error_rate == 0.0
    assert report.p50_latency_ms >= 0


@pytest.mark.asyncio
async def test_eval_records_failure_when_tool_not_called(seeded_session):
    db, agent, *_ = seeded_session
    cases = [
        EvalCase(
            case_id="missfire",
            agent_name=agent.name,
            user_input="Hello there.",  # plain greeting -- no tool will fire
            expected_tools=["create_lead"],
            expected_text_contains=[],
        ),
    ]
    report = await run_eval(db=db, cases=cases, use_judge=False, concurrency=1)
    assert report.tool_accuracy == 0.0
    assert report.cases[0].tools_match is False
