from sqlalchemy import JSON, Boolean, Integer, String, select
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
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    directory_roles: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    directory_departments: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")


class DepartmentRecord(Base):
    __tablename__ = "department"
    __table_args__ = {"schema": "org"}
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    policy: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    parent_id: Mapped[str | None] = mapped_column(String(100))


class SqlDirectory:
    def __init__(self, session):
        self.session = session
        self._hierarchy = None

    def get_user(self, user_id):
        record = self.session.get(UserRecord, user_id, populate_existing=True)
        if record and record.active:
            return UserDTO(
                record.id,
                record.name,
                tuple(sorted(set(record.roles) | set(record.directory_roles))),
                tuple(
                    self.expand_scope(set(record.departments) | set(record.directory_departments))
                ),
                record.version,
            )
        return None

    def identity(self, user_id):
        record = self.session.get(UserRecord, user_id, populate_existing=True)
        return (
            {
                "id": record.id,
                "name": record.name,
                "active": record.active,
                "version": record.version,
            }
            if record
            else None
        )

    def user_ids(self, query):
        # Search is restricted to eligible candidates by the requisition service.
        return [
            r.id
            for r in self.session.scalars(
                select(UserRecord).where(UserRecord.active.is_(True)).order_by(UserRecord.id)
            )
            if query.casefold() in (r.id + " " + r.name).casefold()
        ]

    def expand_scope(self, roots):
        # Exact identifiers, never string-prefix authorization. Visited nodes also bound bad source cycles.
        scope = set(roots)
        if self._hierarchy is None:
            self._hierarchy = list(
                self.session.execute(select(DepartmentRecord.id, DepartmentRecord.parent_id))
            )
        while True:
            added = {dept for dept, parent in self._hierarchy if parent in scope} - scope
            if not added:
                return sorted(scope)
            scope.update(added)

    def policy(self, dept_id):
        record = self.session.get(DepartmentRecord, dept_id)
        return DepartmentPolicy(id=dept_id, **record.policy) if record else None
