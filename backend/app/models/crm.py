"""CRM domain models.

A faithful-but-minimal mirror of Salesforce's core CRM object hierarchy.
All FKs are intentionally string IDs (UUID-like) so traces stay portable.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OpportunityStage(str, enum.Enum):
    PROSPECTING = "prospecting"
    QUALIFICATION = "qualification"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class LeadStatus(str, enum.Enum):
    NEW = "new"
    WORKING = "working"
    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), index=True)
    industry: Mapped[str | None] = mapped_column(String(100))
    annual_revenue: Mapped[float | None] = mapped_column(Float)
    employees: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="account", cascade="all,delete")
    opportunities: Mapped[list["Opportunity"]] = relationship(
        back_populates="account", cascade="all,delete"
    )


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(String(150))
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    account: Mapped[Account | None] = relationship(back_populates="contacts")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    company: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[LeadStatus] = mapped_column(Enum(LeadStatus), default=LeadStatus.NEW)
    source: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    stage: Mapped[OpportunityStage] = mapped_column(
        Enum(OpportunityStage), default=OpportunityStage.PROSPECTING
    )
    amount: Mapped[float | None] = mapped_column(Float)
    close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    account: Mapped[Account] = relationship(back_populates="opportunities")


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    activity_type: Mapped[str] = mapped_column(String(50))  # email | call | meeting | note
    related_to_id: Mapped[str | None] = mapped_column(String(36))  # polymorphic ref
    related_to_type: Mapped[str | None] = mapped_column(String(50))  # account|contact|opp|lead
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
