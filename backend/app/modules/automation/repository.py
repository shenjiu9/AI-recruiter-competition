from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base


class AutomationRecord(Base):
    __tablename__ = "configuration"
    __table_args__ = {"schema": "automation"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
