"""
Postgres store (Section 6.3, Section 9): the hot, queryable trace store.
SQLAlchemy async against asyncpg. common/schema.py stays the source of
truth — rows here are a straightforward JSONB-backed projection of it, so
the store never has its own opinion about what a Session or Step looks
like. 30-day retention is an operational TTL policy applied outside this
module (a scheduled job / lifecycle rule), not logic this file owns.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from common.schema import Session, Step, Trace


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"

    session_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String, index=True)
    agent_version: Mapped[str] = mapped_column(String)
    human_id: Mapped[str] = mapped_column(String, index=True)
    human_context: Mapped[dict] = mapped_column(JSONB)
    task_description: Mapped[str] = mapped_column(String)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)
    containment: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scenario_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class StepRow(Base):
    __tablename__ = "steps"

    step_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sessions.session_id"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    parent_step_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    post_containment: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (Index("ix_steps_session_sequence", "session_id", "sequence"),)


_SESSION_MUTABLE_FIELDS = (
    "agent_id", "agent_version", "human_id", "human_context", "task_description",
    "started_at", "ended_at", "status", "containment", "scenario_id",
)


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        self._engine = create_async_engine(database_url, future=True)
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )

    async def create_tables(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def upsert_session(self, session: Session) -> None:
        dumped = session.model_dump(mode="json")
        async with self._sessionmaker() as db:
            existing = await db.get(SessionRow, session.session_id)
            if existing is None:
                db.add(SessionRow(
                    session_id=session.session_id, agent_id=session.agent_id,
                    agent_version=session.agent_version, human_id=session.human_id,
                    human_context=dumped["human_context"], task_description=session.task_description,
                    started_at=session.started_at, ended_at=session.ended_at,
                    status=session.status.value, containment=dumped["containment"],
                    scenario_id=session.scenario_id,
                ))
            else:
                existing.agent_id = session.agent_id
                existing.agent_version = session.agent_version
                existing.human_id = session.human_id
                existing.human_context = dumped["human_context"]
                existing.task_description = session.task_description
                existing.started_at = session.started_at
                existing.ended_at = session.ended_at
                existing.status = session.status.value
                existing.containment = dumped["containment"]
                existing.scenario_id = session.scenario_id
            await db.commit()

    async def insert_step(self, step: Step) -> None:
        """Steps are append-only and never updated, but delivery is
        fire-and-forget over HTTP (I2) — a retried POST must not blow up
        the drain loop, so a duplicate step_id is a silent no-op rather
        than an IntegrityError."""
        dumped = step.model_dump(mode="json")
        stmt = pg_insert(StepRow).values(
            step_id=step.step_id, session_id=step.session_id, sequence=step.sequence,
            type=step.type.value, started_at=step.started_at, duration_ms=step.duration_ms,
            parent_step_id=step.parent_step_id, payload=dumped["payload"],
            post_containment=step.post_containment,
        ).on_conflict_do_nothing(index_elements=["step_id"])
        async with self._sessionmaker() as db:
            await db.execute(stmt)
            await db.commit()

    async def get_session(self, session_id: uuid.UUID) -> Session | None:
        async with self._sessionmaker() as db:
            row = await db.get(SessionRow, session_id)
        return _session_from_row(row) if row is not None else None

    async def get_trace(self, session_id: uuid.UUID) -> Trace | None:
        async with self._sessionmaker() as db:
            session_row = await db.get(SessionRow, session_id)
            if session_row is None:
                return None
            result = await db.execute(
                select(StepRow).where(StepRow.session_id == session_id).order_by(StepRow.sequence)
            )
            step_rows = result.scalars().all()
        return Trace(session=_session_from_row(session_row), steps=[_step_from_row(r) for r in step_rows])

    async def list_sessions(
        self, *, human_id: str | None = None, agent_id: str | None = None,
        scenario_id: str | None = None, limit: int = 50,
    ) -> list[Session]:
        async with self._sessionmaker() as db:
            stmt = select(SessionRow).order_by(SessionRow.started_at.desc()).limit(limit)
            if human_id:
                stmt = stmt.where(SessionRow.human_id == human_id)
            if agent_id:
                stmt = stmt.where(SessionRow.agent_id == agent_id)
            if scenario_id:
                stmt = stmt.where(SessionRow.scenario_id == scenario_id)
            result = await db.execute(stmt)
            rows = result.scalars().all()
        return [_session_from_row(r) for r in rows]

    async def search_steps_by_content_identifier(self, identifier: str, *, limit: int = 100) -> list[Step]:
        """Backs the Investigator's content-identifier search/pivot
        (Section 6.5), e.g. `ticket:8814` — matches the provenance
        `source_identifier` of any tool_result step."""
        async with self._sessionmaker() as db:
            stmt = (
                select(StepRow)
                .where(StepRow.type == "tool_result")
                .where(StepRow.payload["provenance"]["source_identifier"].astext == identifier)
                .order_by(StepRow.started_at.desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            rows = result.scalars().all()
        return [_step_from_row(r) for r in rows]


def _session_from_row(row: SessionRow) -> Session:
    return Session.model_validate({
        "session_id": row.session_id, "agent_id": row.agent_id, "agent_version": row.agent_version,
        "human_id": row.human_id, "human_context": row.human_context, "task_description": row.task_description,
        "started_at": row.started_at, "ended_at": row.ended_at, "status": row.status,
        "containment": row.containment, "scenario_id": row.scenario_id,
    })


def _step_from_row(row: StepRow) -> Step:
    return Step.model_validate({
        "step_id": row.step_id, "session_id": row.session_id, "sequence": row.sequence, "type": row.type,
        "started_at": row.started_at, "duration_ms": row.duration_ms, "parent_step_id": row.parent_step_id,
        "payload": row.payload, "post_containment": row.post_containment,
    })
