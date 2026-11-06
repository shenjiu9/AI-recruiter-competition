from sqlalchemy import Boolean, Integer, LargeBinary, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import DomainError
from app.platform.database import Base


class PositionRecord(Base):
    __tablename__ = "position"
    __table_args__ = {"schema": "pos"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    dept: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20))
    confidential: Mapped[bool] = mapped_column(Boolean)
    signature: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class GenerationRecord(Base):
    __tablename__ = "generation"
    __table_args__ = {"schema": "pos"}
    requisition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    position_id: Mapped[str | None] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class SqlPositions:
    def __init__(self, session, crypto):
        self.session, self.crypto = session, crypto

    def get(self, pos_id):
        row = self.session.get(PositionRecord, pos_id, populate_existing=True)
        return self.crypto.decrypt(row.data, row.id) if row else None

    def all(self):
        return [
            self.crypto.decrypt(r.data, r.id)
            for r in self.session.scalars(select(PositionRecord).order_by(PositionRecord.id))
        ]

    def save(self, pos, previous=None):
        values = dict(
            version=pos["version"],
            dept=pos["dept"],
            status=pos["status"],
            confidential=pos["confidential"],
            signature=pos["signature"],
            data=self.crypto.encrypt(pos, pos["id"]),
        )
        if previous is None:
            self.session.add(PositionRecord(id=pos["id"], **values))
        else:
            result = self.session.execute(
                update(PositionRecord)
                .where(PositionRecord.id == pos["id"], PositionRecord.version == previous)
                .values(**values)
                .execution_options(autoflush=False)
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "岗位已更新，请刷新后重试", 409)
        self.session.flush()

    def generation(self, req_id):
        row = self.session.get(GenerationRecord, req_id, populate_existing=True)
        return self.crypto.decrypt(row.data, req_id) if row else None

    def save_generation(self, task, previous=None):
        values = dict(
            position_id=task.get("position_id"),
            version=task["version"],
            data=self.crypto.encrypt(task, task["id"]),
        )
        if previous is None:
            self.session.add(GenerationRecord(requisition_id=task["id"], **values))
        else:
            result = self.session.execute(
                update(GenerationRecord)
                .where(
                    GenerationRecord.requisition_id == task["id"],
                    GenerationRecord.version == previous,
                )
                .values(**values)
                .execution_options(autoflush=False)
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "岗位生成任务已处理，请刷新", 409)
        self.session.flush()
