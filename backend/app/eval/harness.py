"""Offline evaluation harness.

Loads a JSON fixture of `EvalCase` records, runs each through the agent runtime,
and scores against expected behaviour. Supports two complementary scoring modes:

  1. Programmatic checks (exact, deterministic):
       - did the expected tool(s) fire?
       - was the expected text substring present in the final answer?
  2. LLM-as-judge (qualitative):
       - did the agent satisfy the user's intent?

Results are aggregated into an EvalReport with per-case detail and rollups.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMClient, TextDelta, TurnEnd, get_llm_client
from app.agents.runtime import RuntimeDone, RuntimeToolCall, run_agent
from app.models import AgentDefinition


@dataclass
class EvalCase:
    """Single test case fixture."""

    case_id: str
    agent_name: str  # name of AgentDefinition to run against
    user_input: str
    expected_tools: list[str] = field(default_factory=list)
    expected_text_contains: list[str] = field(default_factory=list)
    judge_rubric: str | None = None  # optional rubric for LLM-as-judge


@dataclass
class CaseResult:
    case_id: str
    user_input: str
    final_text: str
    tool_calls_made: list[str]
    expected_tools: list[str]
    tools_match: bool
    text_match: bool
    judge_score: float | None = None  # 0.0-1.0 if judge ran
    judge_reasoning: str | None = None
    error: str | None = None
    duration_ms: float = 0.0
    p95_latency_ms: float = 0.0  # filled at aggregate stage


@dataclass
class EvalReport:
    cases: list[CaseResult]
    tool_accuracy: float  # share of cases where tools_match
    text_accuracy: float  # share where text_match
    avg_judge_score: float | None
    p50_latency_ms: float
    p95_latency_ms: float
    error_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "n": len(self.cases),
                "tool_accuracy": round(self.tool_accuracy, 3),
                "text_accuracy": round(self.text_accuracy, 3),
                "avg_judge_score": (
                    round(self.avg_judge_score, 3) if self.avg_judge_score is not None else None
                ),
                "p50_latency_ms": round(self.p50_latency_ms, 1),
                "p95_latency_ms": round(self.p95_latency_ms, 1),
                "error_rate": round(self.error_rate, 3),
            },
            "cases": [c.__dict__ for c in self.cases],
        }


# ---------------------------------------------------------------------------- #
# LLM-as-judge
# ---------------------------------------------------------------------------- #
_JUDGE_SYSTEM = """You are an evaluator scoring whether an AI agent satisfied a user's intent.
Output STRICTLY a JSON object: {"score": <float 0..1>, "reasoning": "<one sentence>"}.
1.0 = fully satisfied; 0.5 = partially; 0.0 = failed."""


async def llm_judge(
    user_input: str,
    final_text: str,
    rubric: str | None,
    llm: LLMClient | None = None,
) -> tuple[float, str]:
    """Score a single agent response. Returns (score, reasoning)."""
    llm = llm or get_llm_client()
    prompt = (
        f"USER INPUT:\n{user_input}\n\n"
        f"AGENT RESPONSE:\n{final_text}\n\n"
        f"RUBRIC: {rubric or 'Did the agent address the user request directly and correctly?'}"
    )
    text = ""
    async for ev in llm.stream(system=_JUDGE_SYSTEM, messages=[{"role": "user", "content": prompt}], tools=[]):
        if isinstance(ev, TextDelta):
            text += ev.text
        elif isinstance(ev, TurnEnd):
            break

    try:
        # tolerate code fences
        cleaned = text.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
        data = json.loads(cleaned)
        return float(data.get("score", 0.5)), str(data.get("reasoning", ""))
    except (json.JSONDecodeError, ValueError, TypeError):
        # Mock provider won't return JSON; fall back to heuristic so the pipeline still runs.
        score = 1.0 if final_text.strip() else 0.0
        return score, "fallback heuristic (judge response unparseable)"


# ---------------------------------------------------------------------------- #
# Replay one case
# ---------------------------------------------------------------------------- #
async def run_case(
    *,
    db: AsyncSession,
    case: EvalCase,
    use_judge: bool = False,
    llm: LLMClient | None = None,
) -> CaseResult:
    started = time.perf_counter()

    agent = (
        await db.execute(select(AgentDefinition).where(AgentDefinition.name == case.agent_name))
    ).scalar_one_or_none()
    if agent is None:
        return CaseResult(
            case_id=case.case_id,
            user_input=case.user_input,
            final_text="",
            tool_calls_made=[],
            expected_tools=case.expected_tools,
            tools_match=False,
            text_match=False,
            error=f"agent '{case.agent_name}' not found",
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    final_text = ""
    tools_made: list[str] = []
    error: str | None = None

    async for ev in run_agent(db=db, agent=agent, user_input=case.user_input, llm=llm):
        if isinstance(ev, RuntimeToolCall):
            tools_made.append(ev.name)
        elif isinstance(ev, RuntimeDone):
            final_text = ev.final_text
        elif hasattr(ev, "type") and ev.type == "error":
            error = getattr(ev, "message", "unknown error")

    # Programmatic scoring
    tools_match = set(case.expected_tools).issubset(set(tools_made))
    text_match = all(s.lower() in final_text.lower() for s in case.expected_text_contains)

    judge_score: float | None = None
    judge_reasoning: str | None = None
    if use_judge:
        judge_score, judge_reasoning = await llm_judge(
            case.user_input, final_text, case.judge_rubric, llm=llm
        )

    return CaseResult(
        case_id=case.case_id,
        user_input=case.user_input,
        final_text=final_text,
        tool_calls_made=tools_made,
        expected_tools=case.expected_tools,
        tools_match=tools_match,
        text_match=text_match,
        judge_score=judge_score,
        judge_reasoning=judge_reasoning,
        error=error,
        duration_ms=(time.perf_counter() - started) * 1000,
    )


# ---------------------------------------------------------------------------- #
# Public API: run a fixture file -> report
# ---------------------------------------------------------------------------- #
def load_cases(path: str | Path) -> list[EvalCase]:
    raw = json.loads(Path(path).read_text())
    return [EvalCase(**c) for c in raw]


async def run_eval(
    *,
    db: AsyncSession | None = None,
    cases: list[EvalCase],
    use_judge: bool = False,
    llm: LLMClient | None = None,
    concurrency: int = 4,
    session_factory: Any = None,
) -> EvalReport:
    """Run all cases with bounded concurrency. Returns aggregated report.

    AsyncSession is not safe for concurrent use across tasks, so each case gets a
    fresh session. If `db` is provided, cases run serially using that session
    (test convenience). Otherwise we open per-case sessions via session_factory or
    the default app session_scope.
    """
    sem = asyncio.Semaphore(concurrency)

    if db is not None:
        # Serial execution against a shared session (caller's responsibility).
        results: list[CaseResult] = []
        for c in cases:
            results.append(await run_case(db=db, case=c, use_judge=use_judge, llm=llm))
    else:
        from app.db import session_scope

        scope = session_factory or session_scope

        async def _bounded(c: EvalCase) -> CaseResult:
            async with sem:
                async with scope() as s:
                    return await run_case(db=s, case=c, use_judge=use_judge, llm=llm)

        results = list(await asyncio.gather(*(_bounded(c) for c in cases)))

    n = len(results)
    tool_acc = sum(1 for r in results if r.tools_match) / n if n else 0.0
    text_acc = sum(1 for r in results if r.text_match) / n if n else 0.0
    err_rate = sum(1 for r in results if r.error) / n if n else 0.0
    judge_scores = [r.judge_score for r in results if r.judge_score is not None]
    avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else None
    latencies = sorted(r.duration_ms for r in results)
    p50 = latencies[len(latencies) // 2] if latencies else 0.0
    p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)] if latencies else 0.0

    return EvalReport(
        cases=results,
        tool_accuracy=tool_acc,
        text_accuracy=text_acc,
        avg_judge_score=avg_judge,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        error_rate=err_rate,
    )
