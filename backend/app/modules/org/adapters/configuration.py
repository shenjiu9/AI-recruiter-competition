from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import DomainError
from app.modules.org.adapters.repository import DepartmentRecord, UserRecord
from app.platform.database import Base


class ConfigurationLock(Base):
    __tablename__ = "configuration_lock"
    __table_args__ = {"schema": "org"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)


class ConfigurationRevision(Base):
    __tablename__ = "configuration_revision"
    __table_args__ = {"schema": "org"}
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict] = mapped_column(JSON)


class SqlConfiguration:
    def __init__(self, session):
        self.session = session

    def lock(self):
        if self.session.bind.dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        self.session.execute(
            insert(ConfigurationLock).values(id=1, version=0).on_conflict_do_nothing()
        )
        self.session.execute(
            update(ConfigurationLock)
            .where(ConfigurationLock.id == 1)
            .values(version=ConfigurationLock.version + 1)
        )

    def users(self):
        return [
            self._user_row(r)
            for r in self.session.scalars(
                select(UserRecord).order_by(UserRecord.id).execution_options(populate_existing=True)
            )
        ]

    def user(self, user_id):
        row = self.session.get(UserRecord, user_id, populate_existing=True)
        return self._user_row(row)

    def _user_row(self, row):
        return (
            None
            if row is None
            else {
                k: getattr(row, k)
                for k in (
                    "id",
                    "name",
                    "roles",
                    "departments",
                    "active",
                    "version",
                    "directory_roles",
                    "directory_departments",
                )
            }
        )

    def departments(self):
        return [
            {
                "id": r.id,
                "parent_id": r.parent_id,
                "version": r.version,
                "policy": {
                    key: r.policy.get(key)
                    for key in ("manager_id", "director_id", "hrbp_id", "hc_owner_id", "hrd_id")
                },
            }
            for r in self.session.scalars(
                select(DepartmentRecord)
                .order_by(DepartmentRecord.id)
                .execution_options(populate_existing=True)
            )
        ]

    def save(self, kind, object_id, expected, values):
        table = UserRecord if kind == "permissions" else DepartmentRecord
        result = self.session.execute(
            update(table)
            .where(table.id == object_id, table.version == expected)
            .values(**values, version=expected + 1)
            .returning(table.id)
        )
        if result.scalar_one_or_none() is None:
            raise DomainError("VERSION_CONFLICT", "配置已被修改，请刷新后重新核对", 409)

    def revision(self, kind, object_id, version, data, actor, at):
        self.session.add(
            ConfigurationRevision(
                kind=kind, object_id=object_id, version=version, data=data, actor_id=actor, at=at
            )
        )

    def history(self, kind, object_id):
        return [
            {"version": r.version, "actor_id": r.actor_id, "at": r.at.isoformat(), "data": r.data}
            for r in self.session.scalars(
                select(ConfigurationRevision)
                .where(
                    ConfigurationRevision.kind == kind, ConfigurationRevision.object_id == object_id
                )
                .order_by(ConfigurationRevision.version.desc())
            )
        ]
