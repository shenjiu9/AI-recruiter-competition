from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import Ctx, new_id
from app.platform.database import Base


class EventRecord(Base):
    __tablename__ = "event"
    __table_args__ = {"schema": "platform"}
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    schema_version: Mapped[int] = mapped_column(default=1)
    partition_key: Mapped[str] = mapped_column(String(80), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    origin_event_id: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class AuditRecord(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "platform"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(64), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trace_id: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)


class RequestRecord(Base):
    __tablename__ = "idempotency"
    __table_args__ = {"schema": "platform"}
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[bytes | None] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status_code: Mapped[int] = mapped_column(Integer, default=200)


class SqlJournal:
    def __init__(self, session, clock):
        self.session, self.clock = session, clock

    def record(
        self,
        ctx: Ctx,
        action: str,
        object_id: str,
        version: int,
        before: dict | None,
        after: dict,
        event: bool = True,
    ) -> None:
        self.session.add(
            AuditRecord(
                id=new_id("AUD"),
                actor_id=ctx.principal.user_id,
                action=action,
                object_id=object_id,
                at=self.clock.now(),
                trace_id=ctx.trace_id,
                before=before,
                after=after,
            )
        )
        if event:
            self.session.add(
                EventRecord(
                    event_id=new_id("EVT"),
                    type=action,
                    partition_key=object_id,
                    occurred_at=self.clock.now(),
                    trace_id=ctx.trace_id,
                    payload={
                        f"{'position' if action == 'kb.changed' else action.split('.')[0]}_id": object_id,
                        "version": version,
                    },
                )
            )
