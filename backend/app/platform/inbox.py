from datetime import datetime

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.platform.records import EventRecord

GROUP = "position.requisition-approved.v1"


class InboxRecord(Base):
    __tablename__ = "inbox"
    __table_args__ = {"schema": "platform"}
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    consumer: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(Integer)
    next_attempt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))


def pending(session, now, limit):
    return list(
        session.scalars(
            select(EventRecord.event_id)
            .outerjoin(
                InboxRecord,
                (InboxRecord.event_id == EventRecord.event_id) & (InboxRecord.consumer == GROUP),
            )
            .where(
                EventRecord.type == "requisition.approved",
                (InboxRecord.event_id.is_(None))
                | ((InboxRecord.status == "retry") & (InboxRecord.next_attempt <= now)),
            )
            .order_by(EventRecord.occurred_at, EventRecord.event_id)
            .limit(limit)
        )
    )
