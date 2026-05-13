"""Strawberry GraphQL types.

Mirrors ORM models with annotations. Kept in one module for simplicity in v0.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import strawberry


@strawberry.type
class ToolDescriptor:
    name: str
    description: str
    schema_json: str  # Pydantic-generated JSON Schema, serialised


@strawberry.type
class GuardrailEntry:
    key: str
    value: str  # always JSON-encoded for schema simplicity


@strawberry.type
class Agent:
    id: str
    name: str
    description: str | None
    system_prompt: str
    tool_names: list[str]
    role: str
    guardrails_json: str  # JSON-encoded
    created_at: datetime
    updated_at: datetime


@strawberry.type
class ToolCall:
    id: str
    sequence: int
    tool_name: str
    arguments_json: str
    result_json: str | None
    error: str | None
    duration_ms: float | None
    created_at: datetime


@strawberry.type
class Trace:
    id: str
    agent_id: str
    user_input: str
    final_output: str | None
    status: str
    error: str | None
    duration_ms: float | None
    tokens_in: int
    tokens_out: int
    created_at: datetime
    tool_calls: list[ToolCall]


@strawberry.type
class EvalCaseResult:
    case_id: str
    user_input: str
    final_text: str
    tool_calls_made: list[str]
    expected_tools: list[str]
    tools_match: bool
    text_match: bool
    judge_score: float | None
    judge_reasoning: str | None
    error: str | None
    duration_ms: float


@strawberry.type
class EvalReport:
    n: int
    tool_accuracy: float
    text_accuracy: float
    avg_judge_score: float | None
    p50_latency_ms: float
    p95_latency_ms: float
    error_rate: float
    cases: list[EvalCaseResult]


@strawberry.input
class CreateAgentInput:
    name: str
    system_prompt: str
    tool_names: list[str]
    description: str | None = None
    role: str = "generalist"
    guardrails_json: str = "{}"


@strawberry.input
class UpdateAgentInput:
    id: str
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    tool_names: list[str] | None = None
    role: str | None = None
    guardrails_json: str | None = None


def parse_json_or_default(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
