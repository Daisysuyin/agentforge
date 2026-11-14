"""FastAPI application entrypoint.

Mounts:
  - /graphql        -- Strawberry GraphQL (queries, mutations)
  - /chat/{agent_id} -- Server-Sent Events streaming agent runtime
  - /chat/orchestrate -- Multi-agent orchestrator endpoint
  - /healthz         -- liveness check

GraphQL handles state. SSE handles streaming. Real-time without WebSocket complexity.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse
from strawberry.fastapi import GraphQLRouter

from app.agents import event_to_json, run_agent
from app.agents.orchestrator import run_orchestrated
from app.config import get_settings
from app.db import init_db, session_scope
from app.graphql import schema
from app.models import AgentDefinition

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="AgentForge", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

graphql_app: GraphQLRouter = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0", "llm_provider": settings.llm_provider}


# ---------------------------------------------------------------------------- #
# Streaming chat (SSE)
# ---------------------------------------------------------------------------- #
@app.get("/chat/orchestrate")
async def orchestrate_stream(request: Request, message: str):
    """Routes to the best specialist sub-agent and streams the result."""

    async def event_generator():
        async with session_scope() as db:
            async for ev in run_orchestrated(db=db, user_input=message):
                if await request.is_disconnected():
                    break
                yield {"event": ev.type, "data": event_to_json(ev)}

    return EventSourceResponse(event_generator())


@app.get("/chat/{agent_id}")
async def chat_stream(agent_id: str, request: Request, message: str):
    """Server-Sent Events stream of one agent run.

    Each event has `data: <json>\\n\\n`. Frontends consume via EventSource.
    """

    async def event_generator():
        async with session_scope() as db:
            agent = (
                await db.execute(select(AgentDefinition).where(AgentDefinition.id == agent_id))
            ).scalar_one_or_none()
            if agent is None:
                yield {"event": "error", "data": '{"message":"agent not found"}'}
                return
            async for ev in run_agent(db=db, agent=agent, user_input=message):
                if await request.is_disconnected():
                    break
                yield {"event": ev.type, "data": event_to_json(ev)}

    return EventSourceResponse(event_generator())


@app.post("/admin/reset")
async def admin_reset(request: Request) -> dict[str, str]:
    """Local-only demo reset; disabled by default and never available remotely."""
    if not settings.enable_demo_reset:
        raise HTTPException(status_code=404, detail="Not found")
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Demo reset requires a loopback client")
    from app.db import Base, engine
    from app.seed import seed_all

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_all()
    return {"status": "reset_and_seeded"}
