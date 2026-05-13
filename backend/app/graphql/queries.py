"""GraphQL Query root."""
from __future__ import annotations

import json

import strawberry
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agents.tools import registry
from app.db import session_scope
from app.graphql.types import Agent, ToolCall, ToolDescriptor, Trace
from app.models import AgentDefinition
from app.models import Trace as TraceModel


def _agent_to_gql(a: AgentDefinition) -> Agent:
    return Agent(
        id=a.id,
        name=a.name,
        description=a.description,
        system_prompt=a.system_prompt,
        tool_names=a.tool_names or [],
        role=a.role,
        guardrails_json=json.dumps(a.guardrails or {}),
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


def _trace_to_gql(t: TraceModel) -> Trace:
    return Trace(
        id=t.id,
        agent_id=t.agent_id,
        user_input=t.user_input,
        final_output=t.final_output,
        status=t.status,
        error=t.error,
        duration_ms=t.duration_ms,
        tokens_in=t.tokens_in,
        tokens_out=t.tokens_out,
        created_at=t.created_at,
        tool_calls=[
            ToolCall(
                id=tc.id,
                sequence=tc.sequence,
                tool_name=tc.tool_name,
                arguments_json=tc.arguments_json,
                result_json=tc.result_json,
                error=tc.error,
                duration_ms=tc.duration_ms,
                created_at=tc.created_at,
            )
            for tc in t.tool_calls
        ],
    )


@strawberry.type
class Query:
    @strawberry.field
    async def agents(self) -> list[Agent]:
        async with session_scope() as db:
            rows = (await db.execute(select(AgentDefinition).order_by(AgentDefinition.created_at.desc()))).scalars().all()
            return [_agent_to_gql(a) for a in rows]

    @strawberry.field
    async def agent(self, id: str) -> Agent | None:
        async with session_scope() as db:
            row = (await db.execute(select(AgentDefinition).where(AgentDefinition.id == id))).scalar_one_or_none()
            return _agent_to_gql(row) if row else None

    @strawberry.field
    async def traces(self, agent_id: str | None = None, limit: int = 50) -> list[Trace]:
        async with session_scope() as db:
            stmt = select(TraceModel).options(selectinload(TraceModel.tool_calls))
            if agent_id:
                stmt = stmt.where(TraceModel.agent_id == agent_id)
            stmt = stmt.order_by(TraceModel.created_at.desc()).limit(limit)
            rows = (await db.execute(stmt)).scalars().all()
            return [_trace_to_gql(t) for t in rows]

    @strawberry.field
    async def trace(self, id: str) -> Trace | None:
        async with session_scope() as db:
            stmt = (
                select(TraceModel)
                .options(selectinload(TraceModel.tool_calls))
                .where(TraceModel.id == id)
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            return _trace_to_gql(row) if row else None

    @strawberry.field
    async def tools(self) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name=t.name,
                description=t.description,
                schema_json=json.dumps(t.Args.model_json_schema()),
            )
            for t in registry.all()
        ]
