from sqlalchemy import Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base


class HireRecord(Base):
    __tablename__ = "hire"
    __table_args__ = {"schema": "hire"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)
