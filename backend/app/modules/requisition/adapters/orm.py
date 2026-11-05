from datetime import datetime

from sqlalchemy import Boolean, DateTime, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base


class RequisitionRecord(Base):
    __tablename__ = "requisition"
    __table_args__ = {"schema": "req"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int]
    creator_id: Mapped[str] = mapped_column(String(64), index=True)
    manager_id: Mapped[str] = mapped_column(String(64))
    dept: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    confidential: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class AccessRecord(Base):
    __tablename__ = "requisition_access"
    __table_args__ = {"schema": "req"}
    requisition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
