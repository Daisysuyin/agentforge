"""Concrete CRM tools.

Each tool declares args via Pydantic (so JSON schema is auto-generated for the LLM),
then implements `run`. Tools are auto-registered via @register on import.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.agents.tools.base import Tool, ToolContext, register
from app.models import (
    Account,
    Activity,
    Contact,
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
)


# ---------------------------------------------------------------------------- #
# create_lead
# ---------------------------------------------------------------------------- #
class _CreateLeadArgs(BaseModel):
    first_name: str = Field(..., description="Lead's first name")
    last_name: str = Field(..., description="Lead's last name")
    email: str | None = Field(None, description="Email address if known")
    company: str | None = Field(None, description="Company name")
    source: str | None = Field(None, description="Lead source, e.g. 'website', 'referral'")
    notes: str | None = Field(None, description="Free-form notes")


@register
class CreateLeadTool(Tool):
    name = "create_lead"
    description = (
        "Create a new sales lead in the CRM. Use this when a user wants to capture "
        "an inbound prospect. Returns the new lead's id and core fields."
    )
    Args = _CreateLeadArgs

    async def run(self, args: _CreateLeadArgs, ctx: ToolContext) -> dict[str, Any]:  # type: ignore[override]
        # Guardrail: block if blocked_companies is configured
        guard = ctx.guardrails or {}
        if args.company and args.company.lower() in {c.lower() for c in guard.get("blocked_companies", [])}:
            raise PermissionError(f"Company '{args.company}' is on the blocklist for this agent")

        lead = Lead(
            first_name=args.first_name,
            last_name=args.last_name,
            email=args.email,
            company=args.company,
            source=args.source,
            notes=args.notes,
            status=LeadStatus.NEW,
        )
        ctx.db.add(lead)
        await ctx.db.flush()
        return {
            "id": lead.id,
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "email": lead.email,
            "company": lead.company,
            "status": lead.status.value,
        }


# ---------------------------------------------------------------------------- #
# find_contact
# ---------------------------------------------------------------------------- #
class _FindContactArgs(BaseModel):
    email: EmailStr | None = Field(None, description="Exact email match")
    query: str | None = Field(None, description="Free text matched against name fields")
    limit: int = Field(5, ge=1, le=25)


@register
class FindContactTool(Tool):
    name = "find_contact"
    description = "Search contacts by email (exact) or free-text name. Returns up to `limit` matches."
    Args = _FindContactArgs

    async def run(self, args: _FindContactArgs, ctx: ToolContext) -> dict[str, Any]:  # type: ignore[override]
        stmt = select(Contact).options(selectinload(Contact.account))
        if args.email:
            stmt = stmt.where(Contact.email == args.email)
        elif args.query:
            q = f"%{args.query}%"
            stmt = stmt.where(or_(Contact.first_name.ilike(q), Contact.last_name.ilike(q), Contact.email.ilike(q)))
        else:
            return {"matches": [], "note": "no email or query provided"}
        stmt = stmt.limit(args.limit)
        rows = (await ctx.db.execute(stmt)).scalars().all()
        return {
            "matches": [
                {
                    "id": c.id,
                    "name": f"{c.first_name} {c.last_name}",
                    "email": c.email,
                    "title": c.title,
                    "account_name": c.account.name if c.account else None,
                }
                for c in rows
            ]
        }


# ---------------------------------------------------------------------------- #
# find_account
# ---------------------------------------------------------------------------- #
class _FindAccountArgs(BaseModel):
    name: str = Field(..., description="Account name (substring match)")
    limit: int = Field(5, ge=1, le=25)


@register
class FindAccountTool(Tool):
    name = "find_account"
    description = "Look up accounts by name (case-insensitive substring match)."
    Args = _FindAccountArgs

    async def run(self, args: _FindAccountArgs, ctx: ToolContext) -> dict[str, Any]:  # type: ignore[override]
        stmt = select(Account).where(Account.name.ilike(f"%{args.name}%")).limit(args.limit)
        rows = (await ctx.db.execute(stmt)).scalars().all()
        return {
            "matches": [
                {
                    "id": a.id,
                    "name": a.name,
                    "industry": a.industry,
                    "annual_revenue": a.annual_revenue,
                    "employees": a.employees,
                }
                for a in rows
            ]
        }


# ---------------------------------------------------------------------------- #
# advance_opportunity_stage
# ---------------------------------------------------------------------------- #
_STAGE_ORDER = [
    OpportunityStage.PROSPECTING,
    OpportunityStage.QUALIFICATION,
    OpportunityStage.PROPOSAL,
    OpportunityStage.NEGOTIATION,
    OpportunityStage.CLOSED_WON,
]


class _AdvanceOppArgs(BaseModel):
    opportunity_id: str | None = Field(None, description="Exact opportunity id; preferred")
    query: str | None = Field(None, description="If id unknown, search by opp or account name")
    target_stage: (
        Literal[
            "prospecting", "qualification", "proposal", "negotiation", "closed_won", "closed_lost"
        ]
        | None
    ) = Field(None, description="Optional explicit target. If omitted, advance one step.")


@register
class AdvanceOpportunityStageTool(Tool):
    name = "advance_opportunity_stage"
    description = (
        "Move an opportunity to the next stage in the sales pipeline. "
        "If `target_stage` is omitted, advances by exactly one step."
    )
    Args = _AdvanceOppArgs

    async def run(self, args: _AdvanceOppArgs, ctx: ToolContext) -> dict[str, Any]:  # type: ignore[override]
        opp: Opportunity | None = None
        if args.opportunity_id:
            opp = (await ctx.db.execute(select(Opportunity).where(Opportunity.id == args.opportunity_id))).scalar_one_or_none()
        elif args.query:
            stmt = (
                select(Opportunity)
                .options(selectinload(Opportunity.account))
                .join(Account)
                .where(or_(Opportunity.name.ilike(f"%{args.query}%"), Account.name.ilike(f"%{args.query}%")))
                .limit(1)
            )
            opp = (await ctx.db.execute(stmt)).scalar_one_or_none()
        if opp is None:
            return {"ok": False, "error": "opportunity not found"}

        # Guardrail: max_amount cap
        guard = ctx.guardrails or {}
        if (cap := guard.get("max_amount")) is not None and opp.amount and opp.amount > cap:
            raise PermissionError(
                f"Opportunity amount ${opp.amount:,.0f} exceeds agent cap ${cap:,.0f}"
            )

        prev_stage = opp.stage
        if args.target_stage:
            opp.stage = OpportunityStage(args.target_stage)
        else:
            try:
                idx = _STAGE_ORDER.index(opp.stage)
                opp.stage = _STAGE_ORDER[min(idx + 1, len(_STAGE_ORDER) - 1)]
            except ValueError:
                # Already closed_lost or unknown -- no-op
                pass
        await ctx.db.flush()
        return {
            "id": opp.id,
            "name": opp.name,
            "previous_stage": prev_stage.value,
            "new_stage": opp.stage.value,
            "amount": opp.amount,
        }


# ---------------------------------------------------------------------------- #
# draft_email
# ---------------------------------------------------------------------------- #
class _DraftEmailArgs(BaseModel):
    to_contact_id: str | None = Field(None, description="Recipient contact id")
    to_email: str | None = Field(None, description="Recipient email if no contact_id")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body, plain text or markdown")
    log_as_activity: bool = Field(True, description="Log as Activity on the contact's account")


@register
class DraftEmailTool(Tool):
    name = "draft_email"
    description = (
        "Compose an email draft for review. Optionally logs as an Activity in the CRM. "
        "This does NOT send the email -- it stages it for human approval."
    )
    Args = _DraftEmailArgs

    async def run(self, args: _DraftEmailArgs, ctx: ToolContext) -> dict[str, Any]:  # type: ignore[override]
        recipient_email = args.to_email
        related_to_id: str | None = None
        related_to_type: str | None = None
        if args.to_contact_id:
            contact = (await ctx.db.execute(select(Contact).where(Contact.id == args.to_contact_id))).scalar_one_or_none()
            if contact is None:
                return {"ok": False, "error": "contact not found"}
            recipient_email = contact.email
            related_to_id = contact.id
            related_to_type = "contact"

        if args.log_as_activity:
            ctx.db.add(
                Activity(
                    subject=f"Email draft: {args.subject}",
                    body=args.body,
                    activity_type="email",
                    related_to_id=related_to_id,
                    related_to_type=related_to_type,
                )
            )
            await ctx.db.flush()

        return {
            "to": recipient_email,
            "subject": args.subject,
            "body": args.body,
            "logged_as_activity": args.log_as_activity,
            "status": "drafted_for_review",
        }


# ---------------------------------------------------------------------------- #
# search_knowledge_base
# ---------------------------------------------------------------------------- #
# Tiny in-process corpus -- in production this is a vector store with embeddings.
_KB_CORPUS: list[dict[str, str]] = [
    {
        "id": "kb-001",
        "title": "Pricing tiers",
        "body": (
            "AgentForge Cloud has three tiers: Starter ($49/seat/mo, 5 agents), "
            "Growth ($199/seat/mo, 50 agents, multi-agent), and Enterprise (custom, SSO, audit log)."
        ),
    },
    {
        "id": "kb-002",
        "title": "SLA",
        "body": (
            "Enterprise customers get 99.9% uptime SLA, 24/7 support, and a dedicated CSM. "
            "Growth tier gets 99.5% uptime with business-hours support."
        ),
    },
    {
        "id": "kb-003",
        "title": "Refund policy",
        "body": (
            "Annual contracts can be refunded prorated within the first 30 days. "
            "Monthly subscriptions are non-refundable but can be cancelled any time."
        ),
    },
    {
        "id": "kb-004",
        "title": "Discount approval",
        "body": (
            "Discounts up to 15% require AE approval. 15-25% requires Sales Manager approval. "
            "Anything above 25% requires VP approval."
        ),
    },
]


class _KBArgs(BaseModel):
    query: str = Field(..., description="Natural language search query")
    top_k: int = Field(3, ge=1, le=10)


@register
class SearchKnowledgeBaseTool(Tool):
    name = "search_knowledge_base"
    description = "Search the internal knowledge base (pricing, SLA, policy). Returns top_k matches."
    Args = _KBArgs

    async def run(self, args: _KBArgs, ctx: ToolContext) -> dict[str, Any]:  # type: ignore[override]
        # Toy keyword scoring; production would be embedding cosine sim.
        terms = [t for t in args.query.lower().split() if len(t) > 2]
        scored: list[tuple[int, dict]] = []
        for doc in _KB_CORPUS:
            text = (doc["title"] + " " + doc["body"]).lower()
            score = sum(text.count(t) for t in terms)
            if score:
                scored.append((score, doc))
        scored.sort(key=lambda x: -x[0])
        return {"matches": [d for _, d in scored[: args.top_k]]}


# ---------------------------------------------------------------------------- #
# summarize_account_history
# ---------------------------------------------------------------------------- #
class _SummarizeAccountArgs(BaseModel):
    account_id: str = Field(..., description="Account id to summarise")
    lookback_days: int = Field(90, ge=1, le=365)


@register
class SummarizeAccountHistoryTool(Tool):
    name = "summarize_account_history"
    description = "Pull recent activity, opportunities, and contacts for an account into a digest."
    Args = _SummarizeAccountArgs

    async def run(self, args: _SummarizeAccountArgs, ctx: ToolContext) -> dict[str, Any]:  # type: ignore[override]
        account = (
            await ctx.db.execute(
                select(Account)
                .options(selectinload(Account.contacts), selectinload(Account.opportunities))
                .where(Account.id == args.account_id)
            )
        ).scalar_one_or_none()
        if account is None:
            return {"ok": False, "error": "account not found"}

        cutoff = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
        activity_stmt = (
            select(Activity)
            .where(Activity.related_to_id.in_([account.id, *[c.id for c in account.contacts]]))
            .where(Activity.created_at >= cutoff)
            .order_by(Activity.created_at.desc())
            .limit(20)
        )
        recent_activities = (await ctx.db.execute(activity_stmt)).scalars().all()

        return {
            "account": {
                "id": account.id,
                "name": account.name,
                "industry": account.industry,
                "annual_revenue": account.annual_revenue,
            },
            "open_opportunities": [
                {"id": o.id, "name": o.name, "stage": o.stage.value, "amount": o.amount}
                for o in account.opportunities
                if o.stage not in (OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST)
            ],
            "contacts": [
                {"id": c.id, "name": f"{c.first_name} {c.last_name}", "title": c.title}
                for c in account.contacts
            ],
            "recent_activities": [
                {"subject": a.subject, "type": a.activity_type, "at": a.created_at.isoformat()}
                for a in recent_activities
            ],
            "lookback_days": args.lookback_days,
        }
