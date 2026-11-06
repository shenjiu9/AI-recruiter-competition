from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import DomainError, new_id
from app.platform.database import Base


class DirectoryChangeRecord(Base):
    __tablename__ = "directory_change"
    __table_args__ = {"schema": "req"}
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    source_version: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSON)


class TransferNoticeRecord(Base):
    __tablename__ = "transfer_notice"
    __table_args__ = {"schema": "req"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    requisition_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SqlTransfers:
    def __init__(self, session):
        self.session = session

    def accept(self, event, at):
        previous = self.session.get(DirectoryChangeRecord, event["event_id"])
        if previous:
            if previous.data != event:
                raise DomainError("EVENT_CONFLICT", "同一目录事件编号不能改变内容", 409)
            return False
        latest = self.change_for(event["user_id"])
        if latest and latest["source_version"] >= event["source_version"]:
            raise DomainError("EVENT_STALE", "目录事件已过期或版本重复", 409)
        self.session.add(
            DirectoryChangeRecord(
                event_id=event["event_id"],
                user_id=event["user_id"],
                source_version=event["source_version"],
                received_at=at,
                data=event,
            )
        )
        self.session.flush()
        return True

    def change_for(self, user_id):
        record = self.session.scalar(
            select(DirectoryChangeRecord)
            .where(DirectoryChangeRecord.user_id == user_id)
            .order_by(DirectoryChangeRecord.source_version.desc())
            .limit(1)
        )
        if not record:
            return None
        at = record.received_at
        return {**record.data, "received_at": at.replace(tzinfo=UTC) if at.tzinfo is None else at}

    def notify(self, req, action, recipients, at):
        for user_id in sorted(set(recipients) - {None}):
            self.session.add(
                TransferNoticeRecord(
                    id=new_id("NTC"), user_id=user_id, requisition_id=req.id, action=action, at=at
                )
            )

    def notices(self, user_id):
        query = select(TransferNoticeRecord).where(TransferNoticeRecord.user_id == user_id)
        return self.session.scalars(
            query.order_by(TransferNoticeRecord.at.desc(), TransferNoticeRecord.id.desc()).limit(
                100
            )
        )
