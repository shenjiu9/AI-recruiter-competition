from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, LargeBinary, String, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import DomainError
from app.platform.database import Base


class JobRecord(Base):
    __tablename__ = "job"
    __table_args__ = (Index("ix_job_due", "queue", "status", "due_at"), {"schema": "engine"})
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    partition_key: Mapped[str] = mapped_column(String(80), index=True)
    queue: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[bytes] = mapped_column(LargeBinary)


def instant(value):
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


class Jobs:
    def __init__(self, session, crypto):
        self.session, self.crypto = session, crypto

    def get(self, key):
        row = self.session.get(JobRecord, key, populate_existing=True)
        return self.crypto.decrypt(row.data, key) if row else None

    def erase_candidates(self, ids):
        keys = [
            j["id"]
            for j in self.all()
            if j["candidate_id"] in ids
            or any(c["candidate_id"] in ids for c in j["inputs"].get("candidates", []))
        ]
        if keys:
            self.session.execute(delete(JobRecord).where(JobRecord.id.in_(keys)))

    def all(self):
        return [
            self.crypto.decrypt(r.data, r.id)
            for r in self.session.scalars(
                select(JobRecord).order_by(JobRecord.due_at, JobRecord.id)
            )
        ]

    def due(self, now, queue):
        return [
            self.crypto.decrypt(r.data, r.id)
            for r in self.session.scalars(
                select(JobRecord)
                .where(
                    JobRecord.queue == queue,
                    JobRecord.status.in_(["queued", "retry", "running", "deferred"]),
                    JobRecord.due_at <= now,
                )
                .order_by(JobRecord.due_at, JobRecord.id)
                .limit(100)
            )
        ]

    def save(self, value, previous=None):
        fields = {
            "version": value["version"],
            "partition_key": value["partition_key"],
            "queue": value["queue"],
            "status": value["status"],
            "due_at": instant(value["due_at"]),
            "data": self.crypto.encrypt(value, value["id"]),
        }
        if previous is None:
            self.session.add(JobRecord(id=value["id"], **fields))
        elif (
            self.session.execute(
                update(JobRecord)
                .where(JobRecord.id == value["id"], JobRecord.version == previous)
                .values(**fields)
            ).rowcount
            != 1
        ):
            raise DomainError("VERSION_CONFLICT", "AI 任务已更新，请刷新", 409)
        self.session.flush()
