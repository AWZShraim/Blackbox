"""
The Northwind Support tool catalogue (Section 7). Ten tools, matching the
build spec's table exactly — no more, no less. No `run_bash`. No
`exec_python`. No generic HTTP tool (I4).

Every handler takes a single `args: dict` (the model's tool call arguments,
already validated against `input_schema` by the mediator) and an optional
`db_path` for test isolation, and returns a JSON-serializable dict. Handlers
never see a raw database credential — the mediator's `CredentialBroker`
mints one per call before the sandbox executes the handler; the handler
receives it as `credential_ref` metadata already resolved into whatever the
sandbox execution context provides (Section 6.2 steps 5-6).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from mediator.execution.registry import RiskLevel, ToolClass, ToolRegistry, ToolSpec
from scenarios.company.db import get_sessionmaker
from scenarios.company.models import (
    AuditLog,
    Customer,
    Deployment,
    InternalDoc,
    Order,
    Refund,
    SentEmail,
    Ticket,
)
from scenarios.company.seed import INTERNAL_EMAIL_DOMAIN

EXPORTABLE_TABLES: dict[str, type] = {
    "customers": Customer,
    "orders": Order,
    "tickets": Ticket,
    "refunds": Refund,
}


def _audit(session, actor: str, action: str, target: str, details: str = "") -> None:
    session.add(AuditLog(
        actor=actor, action=action, target=target, details=details,
        created_at=datetime.now(timezone.utc),
    ))


def _ticket_dict(t: Ticket) -> dict[str, Any]:
    return {
        "id": t.id, "customer_id": t.customer_id, "order_id": t.order_id,
        "subject": t.subject, "body": t.body, "status": t.status,
        "note": t.note, "created_at": t.created_at.isoformat(),
    }


def _customer_dict(c: Customer) -> dict[str, Any]:
    return {
        "id": c.id, "name": c.name, "email": c.email, "tier": c.tier,
        "created_at": c.created_at.isoformat(),
    }


def _order_dict(o: Order) -> dict[str, Any]:
    return {
        "id": o.id, "customer_id": o.customer_id, "item": o.item,
        "amount": o.amount, "status": o.status, "created_at": o.created_at.isoformat(),
    }


# --------------------------------------------------------------------------
# Tool handlers
# --------------------------------------------------------------------------

async def search_tickets(args: dict, *, db_path: Path | None = None) -> dict:
    query = str(args["query"]).lower()
    Session = get_sessionmaker(db_path)
    with Session() as session:
        rows = session.scalars(select(Ticket)).all()
        matches = [
            t for t in rows
            if query in t.subject.lower() or query in t.body.lower() or str(t.id) == query
        ]
        return {"results": [_ticket_dict(t) for t in matches[:20]], "count": len(matches)}


async def get_ticket(args: dict, *, db_path: Path | None = None) -> dict:
    ticket_id = int(args["id"])
    Session = get_sessionmaker(db_path)
    with Session() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            return {"error": f"ticket {ticket_id} not found"}
        return _ticket_dict(t)


async def get_customer(args: dict, *, db_path: Path | None = None) -> dict:
    customer_id = int(args["id"])
    Session = get_sessionmaker(db_path)
    with Session() as session:
        c = session.get(Customer, customer_id)
        if c is None:
            return {"error": f"customer {customer_id} not found"}
        return _customer_dict(c)


async def list_orders(args: dict, *, db_path: Path | None = None) -> dict:
    customer_id = int(args["customer_id"])
    Session = get_sessionmaker(db_path)
    with Session() as session:
        rows = session.scalars(
            select(Order).where(Order.customer_id == customer_id)
        ).all()
        return {"results": [_order_dict(o) for o in rows], "count": len(rows)}


async def issue_refund(args: dict, *, db_path: Path | None = None) -> dict:
    order_id = int(args["order_id"])
    amount = float(args["amount"])
    Session = get_sessionmaker(db_path)
    with Session() as session:
        order = session.get(Order, order_id)
        if order is None:
            return {"error": f"order {order_id} not found"}
        refund = Refund(
            order_id=order_id, amount=amount, status="issued", approved_by="agent",
            created_at=datetime.now(timezone.utc),
        )
        session.add(refund)
        _audit(session, "support-agent", "refund_issued", f"order:{order_id}", f"amount={amount}")
        session.commit()
        return {"refund_id": refund.id, "order_id": order_id, "amount": amount, "status": "issued"}


async def send_email(args: dict, *, db_path: Path | None = None) -> dict:
    to = str(args["to"])
    subject = str(args["subject"])
    body = str(args["body"])
    is_internal = to.strip().lower().endswith("@" + INTERNAL_EMAIL_DOMAIN)
    Session = get_sessionmaker(db_path)
    with Session() as session:
        record = SentEmail(
            sender_agent_id="support-agent", to_address=to, subject=subject, body=body,
            is_internal_domain=is_internal, created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        _audit(session, "support-agent", "email_sent", to, f"internal={is_internal}")
        session.commit()
        return {"sent": True, "to": to, "is_internal_domain": is_internal, "email_id": record.id}


async def update_ticket(args: dict, *, db_path: Path | None = None) -> dict:
    ticket_id = int(args["id"])
    status = str(args["status"])
    note = args.get("note")
    Session = get_sessionmaker(db_path)
    with Session() as session:
        t = session.get(Ticket, ticket_id)
        if t is None:
            return {"error": f"ticket {ticket_id} not found"}
        t.status = status
        if note is not None:
            t.note = note
        _audit(session, "support-agent", "ticket_updated", f"ticket:{ticket_id}", status)
        session.commit()
        return {"id": ticket_id, "status": status}


async def search_docs(args: dict, *, db_path: Path | None = None) -> dict:
    query = str(args["query"]).lower()
    Session = get_sessionmaker(db_path)
    with Session() as session:
        rows = session.scalars(select(InternalDoc)).all()
        matches = [
            d for d in rows
            if query in d.title.lower() or query in d.body.lower()
        ]
        return {
            "results": [
                {"id": d.id, "title": d.title, "body": d.body, "doc_type": d.doc_type}
                for d in matches[:10]
            ],
            "count": len(matches),
        }


async def deploy_service(args: dict, *, db_path: Path | None = None) -> dict:
    name = str(args["name"])
    version = str(args["version"])
    Session = get_sessionmaker(db_path)
    with Session() as session:
        dep = Deployment(
            service_name=name, version=version, deployed_by="deploy-agent",
            deployed_at=datetime.now(timezone.utc), status="succeeded",
        )
        session.add(dep)
        _audit(session, "deploy-agent", "deployment", f"{name}@{version}")
        session.commit()
        return {"deployment_id": dep.id, "service_name": name, "version": version, "status": "succeeded"}


async def export_records(args: dict, *, db_path: Path | None = None) -> dict:
    table = str(args["table"])
    filter_expr = args.get("filter") or ""
    model = EXPORTABLE_TABLES.get(table)
    if model is None:
        return {"error": f"table {table!r} is not exportable"}
    Session = get_sessionmaker(db_path)
    with Session() as session:
        stmt = select(model)
        if filter_expr and "=" in filter_expr:
            col_name, _, value = filter_expr.partition("=")
            col_name, value = col_name.strip(), value.strip()
            col = getattr(model, col_name, None)
            if col is not None:
                stmt = stmt.where(col == value if not value.isdigit() else int(value))
        rows = session.scalars(stmt).all()
        to_dict = {
            Customer: _customer_dict, Order: _order_dict, Ticket: _ticket_dict,
        }.get(model, lambda r: {c.name: getattr(r, c.name) for c in r.__table__.columns})
        results = [to_dict(r) for r in rows]
        _audit(session, "support-agent", "export_run", table, f"filter={filter_expr!r} rows={len(results)}")
        session.commit()
        return {"table": table, "filter": filter_expr, "count": len(results), "results": results}


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------

def build_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(ToolSpec(
        name="search_tickets", description="Search support tickets by keyword or id.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        tool_class=ToolClass.read, risk=RiskLevel.low, handler=search_tickets,
        notes="Returns untrusted content",
    ))
    registry.register(ToolSpec(
        name="get_ticket", description="Fetch a single ticket by id.",
        input_schema={"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
        tool_class=ToolClass.read, risk=RiskLevel.low, handler=get_ticket,
        notes="Returns untrusted content",
    ))
    registry.register(ToolSpec(
        name="get_customer", description="Fetch a customer record by id.",
        input_schema={"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
        tool_class=ToolClass.read, risk=RiskLevel.medium, handler=get_customer,
        notes="PII",
    ))
    registry.register(ToolSpec(
        name="list_orders", description="List orders for a customer.",
        input_schema={"type": "object", "properties": {"customer_id": {"type": "integer"}}, "required": ["customer_id"]},
        tool_class=ToolClass.read, risk=RiskLevel.medium, handler=list_orders,
    ))
    registry.register(ToolSpec(
        name="issue_refund", description="Issue a refund against an order.",
        input_schema={
            "type": "object",
            "properties": {"order_id": {"type": "integer"}, "amount": {"type": "number"}},
            "required": ["order_id", "amount"],
        },
        tool_class=ToolClass.write, risk=RiskLevel.high, handler=issue_refund,
        notes="Policy: cap without approval",
    ))
    registry.register(ToolSpec(
        name="send_email", description="Send an email on the agent's behalf.",
        input_schema={
            "type": "object",
            "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
            "required": ["to", "subject", "body"],
        },
        tool_class=ToolClass.write, risk=RiskLevel.high, handler=send_email,
        notes="Policy: internal domains only",
    ))
    registry.register(ToolSpec(
        name="update_ticket", description="Update a ticket's status and note.",
        input_schema={
            "type": "object",
            "properties": {
                "id": {"type": "integer"}, "status": {"type": "string"}, "note": {"type": "string"},
            },
            "required": ["id", "status"],
        },
        tool_class=ToolClass.write, risk=RiskLevel.low, handler=update_ticket,
    ))
    registry.register(ToolSpec(
        name="search_docs", description="Search internal documentation by keyword.",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        tool_class=ToolClass.read, risk=RiskLevel.low, handler=search_docs,
        notes="Returns untrusted content",
    ))
    registry.register(ToolSpec(
        name="deploy_service", description="Deploy a service version.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}, "version": {"type": "string"}},
            "required": ["name", "version"],
        },
        tool_class=ToolClass.write, risk=RiskLevel.critical, handler=deploy_service,
        notes="Policy: approval required",
    ))
    registry.register(ToolSpec(
        name="export_records", description="Bulk export rows from a table, with an optional filter.",
        input_schema={
            "type": "object",
            "properties": {"table": {"type": "string"}, "filter": {"type": "string"}},
            "required": ["table"],
        },
        tool_class=ToolClass.read, risk=RiskLevel.critical, handler=export_records,
        notes="Bulk read — abuse-mode target",
    ))

    return registry
