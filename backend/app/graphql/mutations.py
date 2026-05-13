"""GraphQL Mutation root."""
from __future__ import annotations

import json
from pathlib import Path

import strawberry
from sqlalchemy import select

from app.db import session_scope
from app.eval import load_cases, run_eval
from app.graphql.queries import _agent_to_gql
from app.graphql.types import (
    Agent,
    CreateAgentInput,
    EvalCaseResult,
    EvalReport,
    UpdateAgentInput,
    parse_json_or_default,
)
from app.models import AgentDefinition


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_agent(self, input: CreateAgentInput) -> Agent:
        async with session_scope() as db:
            agent = AgentDefinition(
                name=input.name,
                description=input.description,
                system_prompt=input.system_prompt,
                tool_names=input.tool_names,
                role=input.role,
                guardrails=parse_json_or_default(input.guardrails_json, {}),
            )
            db.add(agent)
            await db.flush()
            return _agent_to_gql(agent)

    @strawberry.mutation
    async def update_agent(self, input: UpdateAgentInput) -> Agent | None:
        async with session_scope() as db:
            agent = (await db.execute(select(AgentDefinition).where(AgentDefinition.id == input.id))).scalar_one_or_none()
            if agent is None:
                return None
            if input.name is not None:
                agent.name = input.name
            if input.description is not None:
                agent.description = input.description
            if input.system_prompt is not None:
                agent.system_prompt = input.system_prompt
            if input.tool_names is not None:
                agent.tool_names = input.tool_names
            if input.role is not None:
                agent.role = input.role
            if input.guardrails_json is not None:
                agent.guardrails = parse_json_or_default(input.guardrails_json, {})
            await db.flush()
            return _agent_to_gql(agent)

    @strawberry.mutation
    async def delete_agent(self, id: str) -> bool:
        async with session_scope() as db:
            agent = (await db.execute(select(AgentDefinition).where(AgentDefinition.id == id))).scalar_one_or_none()
            if agent is None:
                return False
            await db.delete(agent)
            return True

    @strawberry.mutation
    async def run_eval_suite(
        self,
        fixture_path: str = "../traces/sample_traces.json",
        use_judge: bool = False,
        concurrency: int = 4,
    ) -> EvalReport:
        cases = load_cases(Path(fixture_path).resolve())
        async with session_scope() as db:
            report = await run_eval(db=db, cases=cases, use_judge=use_judge, concurrency=concurrency)
        return EvalReport(
            n=len(report.cases),
            tool_accuracy=report.tool_accuracy,
            text_accuracy=report.text_accuracy,
            avg_judge_score=report.avg_judge_score,
            p50_latency_ms=report.p50_latency_ms,
            p95_latency_ms=report.p95_latency_ms,
            error_rate=report.error_rate,
            cases=[
                EvalCaseResult(
                    case_id=c.case_id,
                    user_input=c.user_input,
                    final_text=c.final_text,
                    tool_calls_made=c.tool_calls_made,
                    expected_tools=c.expected_tools,
                    tools_match=c.tools_match,
                    text_match=c.text_match,
                    judge_score=c.judge_score,
                    judge_reasoning=c.judge_reasoning,
                    error=c.error,
                    duration_ms=c.duration_ms,
                )
                for c in report.cases
            ],
        )
