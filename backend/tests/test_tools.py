"""Tool unit tests."""
from __future__ import annotations

import pytest

from app.agents.tools import ToolContext, registry


@pytest.mark.asyncio
async def test_create_lead(seeded_session):
    db, agent, _account, _contact = seeded_session
    tool = registry.get("create_lead")
    assert tool is not None
    ctx = ToolContext(db=db, agent_id=agent.id, guardrails=agent.guardrails)
    result = await tool.execute(
        {"first_name": "Sarah", "last_name": "Chen", "company": "Hexagon"}, ctx
    )
    assert result.ok
    assert result.data["first_name"] == "Sarah"
    assert result.data["company"] == "Hexagon"
    assert result.data["status"] == "new"


@pytest.mark.asyncio
async def test_create_lead_blocked_company(seeded_session):
    db, agent, *_ = seeded_session
    agent.guardrails = {"blocked_companies": ["Hooli"]}
    tool = registry.get("create_lead")
    ctx = ToolContext(db=db, agent_id=agent.id, guardrails=agent.guardrails)
    result = await tool.execute(
        {"first_name": "X", "last_name": "Y", "company": "Hooli"}, ctx
    )
    assert not result.ok
    assert "blocklist" in (result.error or "")


@pytest.mark.asyncio
async def test_find_contact_by_email(seeded_session):
    db, agent, _account, _contact = seeded_session
    tool = registry.get("find_contact")
    ctx = ToolContext(db=db, agent_id=agent.id)
    result = await tool.execute({"email": "anna@example.com"}, ctx)
    assert result.ok
    assert len(result.data["matches"]) == 1
    assert result.data["matches"][0]["name"] == "Anna Reyes"


@pytest.mark.asyncio
async def test_find_contact_invalid_email(seeded_session):
    db, agent, *_ = seeded_session
    tool = registry.get("find_contact")
    ctx = ToolContext(db=db, agent_id=agent.id)
    # "not-an-email" should fail Pydantic EmailStr validation -> ToolResult(ok=False)
    result = await tool.execute({"email": "not-an-email"}, ctx)
    assert not result.ok
    assert "Invalid arguments" in (result.error or "")


@pytest.mark.asyncio
async def test_search_knowledge_base(seeded_session):
    db, agent, *_ = seeded_session
    tool = registry.get("search_knowledge_base")
    ctx = ToolContext(db=db, agent_id=agent.id)
    result = await tool.execute({"query": "refund policy"}, ctx)
    assert result.ok
    assert len(result.data["matches"]) >= 1
    assert any("refund" in m["title"].lower() for m in result.data["matches"])


def test_all_tools_have_valid_schemas():
    for tool in registry.all():
        schema = tool.schema()
        assert schema.name
        assert schema.description
        assert isinstance(schema.parameters, dict)
        assert schema.parameters.get("type") == "object"
