"""
Northwind Support: the synthetic company Blackbox's demo agents operate
against. All state lives here in SQLite — no real external integrations,
ever (Section 7).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]
    tier: Mapped[str] = mapped_column(default="standard")  # standard | premium
    created_at: Mapped[datetime]


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    item: Mapped[str]
    amount: Mapped[float]
    status: Mapped[str] = mapped_column(default="delivered")
    created_at: Mapped[datetime]


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    subject: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="open")  # open | pending | resolved
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime]


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    amount: Mapped[float]
    status: Mapped[str] = mapped_column(default="issued")
    approved_by: Mapped[str] = mapped_column(default="agent")
    created_at: Mapped[datetime]


class InternalDoc(Base):
    __tablename__ = "internal_docs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str] = mapped_column(default="policy")  # policy | runbook | faq
    created_at: Mapped[datetime]


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str]
    version: Mapped[str]
    deployed_by: Mapped[str]
    deployed_at: Mapped[datetime]
    status: Mapped[str] = mapped_column(default="succeeded")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str]
    action: Mapped[str]
    target: Mapped[str]
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime]


class SentEmail(Base):
    """No real external integration, ever (Section 7). send_email() writes
    here instead of touching a real mail transport, so the scenario stays
    fully synthetic while still letting a tool "exfiltrate" data for the
    injection scenario to be detected."""

    __tablename__ = "sent_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_agent_id: Mapped[str]
    to_address: Mapped[str]
    subject: Mapped[str]
    body: Mapped[str] = mapped_column(Text)
    is_internal_domain: Mapped[bool]
    created_at: Mapped[datetime]
