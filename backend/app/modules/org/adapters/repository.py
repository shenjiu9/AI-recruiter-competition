from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.org.contracts import DepartmentPolicy, UserDTO
from app.platform.database import Base


class UserRecord(Base):
    __tablename__ = "user"
    __table_args__ = {"schema": "org"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    roles: Mapped[list] = mapped_column(JSON)
    departments: Mapped[list] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DepartmentRecord(Base):
    __tablename__ = "department"
    __table_args__ = {"schema": "org"}
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    policy: Mapped[dict] = mapped_column(JSON)


class SqlDirectory:
    def __init__(self, session):
        self.session = session

    def get_user(self, user_id):
        record = self.session.get(UserRecord, user_id)
        if record and record.active:
            return UserDTO(record.id, record.name, tuple(record.roles), tuple(record.departments))
        return None

    def policy(self, dept_id):
        record = self.session.get(DepartmentRecord, dept_id)
        return DepartmentPolicy(id=dept_id, **record.policy) if record else None
