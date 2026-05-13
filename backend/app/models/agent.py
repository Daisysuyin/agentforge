"""Agent definitions and execution traces.

AgentDefinition: user-authored agent config (system prompt, tools, guardrails).
Trace: full reasoning + tool-call history for a single agent run -- the unit of evaluation.
ToolCallRecord: individual tool invocations within a trace.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AgentDefinition(Base):
    """User-authored agent. The 'agent builder' UI writes to this table."""

    __tablename__ = "agent_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text)
    # List of tool names from the registry, e.g. ["create_lead", "find_contact"].
    tool_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Free-form guardrail rules: {"max_amount": 50000, "block_topics": ["legal"]}.
    guardrails: Mapped[dict] = mapped_column(JSON, default=dict)
    role: Mapped[str] = mapped_column(String(50), default="generalist")  # sales|service|marketing
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    traces: Mapped[list["Trace"]] = relationship(back_populates="agent", cascade="all,delete")


class Trace(Base):
    """One full agent run from user input to final answer.

    Stored eagerly so the eval harness can replay deterministically.
    """

    __tablename__ = "traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent_definitions.id"))
    user_input: Mapped[str] = mapped_column(Text)
    final_output: Mapped[str | None] = mapped_column(Text)
    # Full message history including tool calls/results for replay.
    messages_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(50), default="running")  # running|done|error
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    agent: Mapped[AgentDefinition] = relationship(back_populates="traces")
    tool_calls: Mapped[list["ToolCallRecord"]] = relationship(
        back_populates="trace", cascade="all,delete", order_by="ToolCallRecord.sequence"
    )

    def messages(self) -> list[dict]:
        return json.loads(self.messages_json or "[]")

    def set_messages(self, value: list[dict]) -> None:
        self.messages_json = json.dumps(value)


class ToolCallRecord(Base):
    """One tool invocation. Indexed within its trace for replay ordering."""

    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    trace_id: Mapped[str] = mapped_column(ForeignKey("traces.id"))
    sequence: Mapped[int] = mapped_column(Integer)  # 0-indexed within trace
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    trace: Mapped[Trace] = relationship(back_populates="tool_calls")
