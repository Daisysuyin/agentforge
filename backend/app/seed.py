"""Seed the mock CRM and create default specialist agents.

Run via: `python -m app.seed`. Idempotent on a fresh database; will skip if data exists.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import init_db, session_scope
from app.models import (
    Account,
    Activity,
    AgentDefinition,
    Contact,
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
)


_ACCOUNTS = [
    {
        "name": "Globex Industries",
        "industry": "Manufacturing",
        "annual_revenue": 45_000_000,
        "employees": 320,
    },
    {
        "name": "Initech Software",
        "industry": "Technology",
        "annual_revenue": 12_500_000,
        "employees": 85,
    },
    {
        "name": "Northwind Solutions",
        "industry": "Logistics",
        "annual_revenue": 78_000_000,
        "employees": 540,
    },
    {
        "name": "Acme Health",
        "industry": "Healthcare",
        "annual_revenue": 210_000_000,
        "employees": 1_200,
    },
]

_CONTACTS = [
    ("Anna", "Reyes", "anna@globex.example", "VP Engineering", "Globex Industries"),
    ("Bill", "Lumbergh", "bill@initech.example", "Director of Operations", "Initech Software"),
    ("Priya", "Singh", "priya@northwind.example", "Head of Procurement", "Northwind Solutions"),
    ("Marcus", "Webb", "marcus@acmehealth.example", "CTO", "Acme Health"),
    ("Linh", "Tran", "linh@globex.example", "Sr. Solutions Architect", "Globex Industries"),
]

_OPPORTUNITIES = [
    ("Globex Renewal", "Globex Industries", OpportunityStage.QUALIFICATION, 125_000),
    ("Initech Expansion", "Initech Software", OpportunityStage.PROPOSAL, 48_000),
    ("Northwind Multi-Year", "Northwind Solutions", OpportunityStage.NEGOTIATION, 310_000),
    ("Acme Pilot", "Acme Health", OpportunityStage.PROSPECTING, 25_000),
]

_LEADS = [
    ("Sarah", "Chen", "sarah@example.com", "Hexagon Labs", "website"),
    ("David", "Park", "david@example.com", "Vortex Capital", "referral"),
    ("Maya", "Patel", "maya@example.com", "Lumen Studios", "linkedin"),
]


# --- agents ----------------------------------------------------------------- #
_AGENTS = [
    {
        "name": "Sales SDR",
        "role": "sales",
        "description": "Lead capture, opportunity progression, pricing questions.",
        "system_prompt": (
            "You are AgentForge's Sales SDR agent. You help reps capture inbound leads, "
            "answer pricing questions, and progress opportunities. Always confirm before "
            "you advance an opportunity past 'negotiation'. When a tool returns an error, "
            "explain it plainly and suggest a next step."
        ),
        "tool_names": [
            "create_lead",
            "find_contact",
            "find_account",
            "advance_opportunity_stage",
            "search_knowledge_base",
        ],
        "guardrails": {"max_amount": 500_000, "blocked_companies": ["Hooli"]},
    },
    {
        "name": "Customer Service",
        "role": "service",
        "description": "Existing-customer questions, account history, refunds.",
        "system_prompt": (
            "You are AgentForge's Customer Service agent. You answer policy questions "
            "from the knowledge base and summarise account history. Never quote pricing "
            "you cannot find in the KB."
        ),
        "tool_names": [
            "find_contact",
            "find_account",
            "search_knowledge_base",
            "summarize_account_history",
            "draft_email",
        ],
        "guardrails": {},
    },
    {
        "name": "Marketing",
        "role": "marketing",
        "description": "Campaign drafting and outbound email composition.",
        "system_prompt": (
            "You are AgentForge's Marketing agent. You draft outreach emails for review. "
            "Always draft, never send. Personalise using account history when available."
        ),
        "tool_names": [
            "find_contact",
            "find_account",
            "summarize_account_history",
            "draft_email",
            "search_knowledge_base",
        ],
        "guardrails": {},
    },
]


async def seed_all() -> None:
    await init_db()

    async with session_scope() as db:
        # Skip if accounts already exist
        existing = (await db.execute(select(Account).limit(1))).scalar_one_or_none()
        if existing is not None:
            print("Database already seeded -- skipping.")
            return

        # Accounts
        accounts: dict[str, Account] = {}
        for spec in _ACCOUNTS:
            a = Account(**spec)
            db.add(a)
            accounts[a.name] = a
        await db.flush()

        # Contacts
        for first, last, email, title, account_name in _CONTACTS:
            db.add(
                Contact(
                    first_name=first,
                    last_name=last,
                    email=email,
                    title=title,
                    account_id=accounts[account_name].id,
                )
            )

        # Opportunities
        for name, account_name, stage, amount in _OPPORTUNITIES:
            db.add(
                Opportunity(
                    name=name,
                    account_id=accounts[account_name].id,
                    stage=stage,
                    amount=amount,
                    close_date=datetime.now(timezone.utc) + timedelta(days=45),
                )
            )

        # Leads
        for first, last, email, company, source in _LEADS:
            db.add(
                Lead(
                    first_name=first,
                    last_name=last,
                    email=email,
                    company=company,
                    source=source,
                    status=LeadStatus.NEW,
                )
            )

        # Activities
        for account_name in ("Globex Industries", "Northwind Solutions"):
            db.add(
                Activity(
                    subject=f"QBR with {account_name}",
                    body="Quarterly business review notes...",
                    activity_type="meeting",
                    related_to_id=accounts[account_name].id,
                    related_to_type="account",
                )
            )

        # Agents
        for spec in _AGENTS:
            db.add(AgentDefinition(**spec))

    print("Seeded mock CRM and 3 specialist agents.")


if __name__ == "__main__":
    asyncio.run(seed_all())
