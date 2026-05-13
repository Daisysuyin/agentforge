"""Tool framework: base class, execution context, and discovery registry.

Design:
  Tool(ABC) -- subclass to define a tool. Each subclass declares name, description,
  a Pydantic args model, and async run().

  Registry -- module-level singleton mapping name -> Tool. The agent runtime queries
  it to (a) supply schemas to the LLM, (b) dispatch tool calls.

  ToolContext -- everything a tool might need at execution time: db session, the
  AgentDefinition (for guardrails), and the trace_id for audit logging.
"""
from __future__ import annotations

import abc
import time
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import ToolSchema


@dataclass
class ToolContext:
    """Runtime context passed to every tool invocation."""

    db: AsyncSession
    agent_id: str | None = None
    trace_id: str | None = None
    guardrails: dict[str, Any] | None = None


@dataclass
class ToolResult:
    """Normalised tool result. `ok=False` triggers an error message back to the LLM."""

    ok: bool
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        if self.ok:
            return {"ok": True, "data": self.data}
        return {"ok": False, "error": self.error}


class Tool(abc.ABC):
    """Base class for all tools.

    Subclasses MUST set:
      - name: stable identifier the LLM uses to call this tool
      - description: short human-readable purpose, surfaces to the LLM
      - Args: a pydantic.BaseModel describing arguments (used for JSON-schema)

    Subclasses MUST implement:
      - run(args, ctx) -> result payload (will be wrapped in ToolResult)
    """

    name: ClassVar[str]
    description: ClassVar[str]
    Args: ClassVar[type[BaseModel]]

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=self.Args.model_json_schema(),
        )

    async def execute(self, raw_args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """Public entrypoint: validates args, runs, times, and wraps errors."""
        start = time.perf_counter()
        try:
            args = self.Args.model_validate(raw_args)
        except ValidationError as e:
            return ToolResult(
                ok=False,
                error=f"Invalid arguments for {self.name}: {e.errors()}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        try:
            data = await self.run(args, ctx)
            return ToolResult(ok=True, data=data, duration_ms=(time.perf_counter() - start) * 1000)
        except Exception as e:  # surface tool errors back to the model
            return ToolResult(
                ok=False, error=f"{type(e).__name__}: {e}", duration_ms=(time.perf_counter() - start) * 1000
            )

    @abc.abstractmethod
    async def run(self, args: BaseModel, ctx: ToolContext) -> Any:
        """Tool-specific implementation. Return JSON-serialisable data."""


class ToolRegistry:
    """Singleton registry. Tools self-register via @register decorator."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_for_agent(self, names: list[str]) -> list[Tool]:
        return [self._tools[n] for n in names if n in self._tools]

    def all(self) -> list[Tool]:
        return list(self._tools.values())


registry = ToolRegistry()


def register(cls: type[Tool]) -> type[Tool]:
    """Class decorator: instantiate and register on import."""
    registry.register(cls())
    return cls
