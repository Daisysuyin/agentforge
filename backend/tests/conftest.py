"""Pytest fixtures: in-memory DB, seeded data."""
from __future__ import annotations

import asyncio
import os

import pytest
import pytest_asyncio

# Force in-memory SQLite + mock LLM before importing the app
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["LLM_PROVIDER"] = "mock"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session():
    """Fresh in-memory database per test."""
    # Re-create engine for isolation
    from app.config import get_settings
    from app.db import Base, SessionLocal

    get_settings.cache_clear()
    settings = get_settings()
    settings.database_url = "sqlite+aiosqlite:///:memory:"

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    # ensure model classes register on Base
    from app.models import agent, crm  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as session:
        yield session
        await session.commit()

    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_session(db_session):
    """db_session + a single agent and one account/contact for tool tests."""
    from app.models import Account, AgentDefinition, Contact

    account = Account(name="Acme Corp", industry="Tech")
    db_session.add(account)
    await db_session.flush()

    contact = Contact(
        first_name="Anna",
        last_name="Reyes",
        email="anna@example.com",
        title="VP",
        account_id=account.id,
    )
    db_session.add(contact)

    agent = AgentDefinition(
        name="Test Agent",
        description="Test fixture agent",
        system_prompt="You are a test agent.",
        tool_names=["create_lead", "find_contact", "search_knowledge_base"],
        role="sales",
        guardrails={},
    )
    db_session.add(agent)
    await db_session.flush()

    return db_session, agent, account, contact
