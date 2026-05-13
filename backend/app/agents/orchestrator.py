"""Multi-agent orchestrator.

Routes a user input to the best specialist sub-agent (sales / service / marketing)
using a small classifier prompt, then runs that sub-agent's full tool loop.

This is intentionally thin: the heavy lifting lives in `runtime.run_agent`. The
orchestrator's job is dispatch + framing.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMClient, TextDelta, TurnEnd, get_llm_client
from app.agents.runtime import RuntimeError as RuntimeErrorEvent
from app.agents.runtime import RuntimeEvent, RuntimeTextDelta, run_agent
from app.models import AgentDefinition

_ROUTER_SYSTEM = """You are a router. Given a user request, output exactly one word:
either "sales", "service", or "marketing" -- whichever specialist should handle it.
Sales: leads, opportunities, deal stages, pricing.
Service: existing customer issues, refunds, account history.
Marketing: campaigns, content, outreach drafts.
Output the single word only. No punctuation."""

_VALID_ROLES = {"sales", "service", "marketing"}


async def route(user_input: str, llm: LLMClient | None = None) -> str:
    """Run a single classifier turn and return one of {sales, service, marketing}."""
    llm = llm or get_llm_client()
    accumulated = ""
    async for ev in llm.stream(
        system=_ROUTER_SYSTEM,
        messages=[{"role": "user", "content": user_input}],
        tools=[],
    ):
        if isinstance(ev, TextDelta):
            accumulated += ev.text
        elif isinstance(ev, TurnEnd):
            break
    word = accumulated.strip().lower().split()[0] if accumulated.strip() else "sales"
    return word if word in _VALID_ROLES else "sales"


async def run_orchestrated(
    *,
    db: AsyncSession,
    user_input: str,
    llm: LLMClient | None = None,
) -> AsyncIterator[RuntimeEvent]:
    """Pick a specialist sub-agent by role and run it.

    Yields a synthetic preamble explaining the routing choice, then forwards
    every event from the chosen sub-agent unchanged.
    """
    role = await route(user_input, llm=llm)
    print(f"[orchestrator] role classifier returned: {role!r}", flush=True)

    stmt = select(AgentDefinition).where(AgentDefinition.role == role).limit(1)
    sub_agent = (await db.execute(stmt)).scalar_one_or_none()
    print(f"[orchestrator] role={role!r} -> sub_agent={sub_agent.name if sub_agent else None}", flush=True)
    
    if sub_agent is None:
        sub_agent = (await db.execute(select(AgentDefinition).limit(1))).scalar_one_or_none()
        print(f"[orchestrator] fallback -> {sub_agent.name if sub_agent else None}", flush=True)

    if sub_agent is None:
        print("[orchestrator] no agents in DB, emitting error", flush=True)
        yield RuntimeErrorEvent(message="no agent definitions available")
        return

    yield RuntimeTextDelta(text=f"[orchestrator] routed to: {role} ({sub_agent.name})\n")

    async for ev in run_agent(db=db, agent=sub_agent, user_input=user_input, llm=llm):
        yield ev
