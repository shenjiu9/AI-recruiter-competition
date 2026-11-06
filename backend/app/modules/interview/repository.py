from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import DomainError, new_id
from app.platform.database import Base


class InterviewRecord(Base):
    __tablename__ = "interview"
    __table_args__ = {"schema": "iv"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    application_id: Mapped[str] = mapped_column(String(64), index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class ReservationRecord(Base):
    __tablename__ = "reservation"
    __table_args__ = {"schema": "iv"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    interview_id: Mapped[str] = mapped_column(String(64), index=True)
    resource: Mapped[str] = mapped_column(String(80), index=True)
    slot_id: Mapped[str] = mapped_column(String(64))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AvailabilityRecord(Base):
    __tablename__ = "availability"
    __table_args__ = {"schema": "iv"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class SqlInterviews:
    def __init__(self, session, crypto):
        self.session, self.crypto = session, crypto

    def get(self, iid):
        row = self.session.get(InterviewRecord, iid, populate_existing=True)
        return self.crypto.decrypt(row.data, iid) if row else None

    def all(self):
        return [
            self.crypto.decrypt(r.data, r.id) for r in self.session.scalars(select(InterviewRecord))
        ]

    def save(self, iv, previous=None):
        values = dict(
            application_id=iv["application_id"],
            candidate_id=iv["candidate_id"],
            version=iv["version"],
            data=self.crypto.encrypt(iv, iv["id"]),
        )
        if previous is None:
            self.session.add(InterviewRecord(id=iv["id"], **values))
        else:
            r = self.session.execute(
                update(InterviewRecord)
                .where(InterviewRecord.id == iv["id"], InterviewRecord.version == previous)
                .values(**values)
            )
            if r.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "面试记录已更新，请刷新", 409)
        self.session.flush()

    def availability(self, uid):
        row = self.session.get(AvailabilityRecord, uid)
        return (
            self.crypto.decrypt(row.data, uid)
            if row
            else {
                "version": 0,
                "weekdays": [0, 1, 2, 3, 4],
                "start_hour": 9,
                "end_hour": 18,
                "daily_limit": 5,
                "weekly_limit": 20,
                "buffer_minutes": 10,
            }
        )

    def save_availability(self, uid, value):
        row = self.session.get(AvailabilityRecord, uid)
        if not row:
            row = AvailabilityRecord(id=uid)
            self.session.add(row)
        row.data = self.crypto.encrypt(value, uid)
        self.session.flush()

    def expire(self, now):
        self.session.execute(delete(ReservationRecord).where(ReservationRecord.expires_at <= now))

    def release(self, iid):
        self.session.execute(delete(ReservationRecord).where(ReservationRecord.interview_id == iid))

    def overlaps(self, resource, start, end, excluding=""):
        return (
            self.session.scalar(
                select(ReservationRecord.id)
                .where(
                    ReservationRecord.resource == resource,
                    ReservationRecord.start_at < end,
                    ReservationRecord.end_at > start,
                    ReservationRecord.interview_id != excluding,
                )
                .limit(1)
            )
            is not None
        )

    def reserve(self, iid, resource, slot_id, start, end, expires):
        self.session.add(
            ReservationRecord(
                id=new_id("RSV"),
                interview_id=iid,
                resource=resource,
                slot_id=slot_id,
                start_at=start,
                end_at=end,
                expires_at=expires,
            )
        )
        self.session.flush()

    def erase(self, ids):
        for iv in self.all():
            if iv["candidate_id"] in ids:
                self.release(iv["id"])
        self.session.execute(delete(InterviewRecord).where(InterviewRecord.candidate_id.in_(ids)))
