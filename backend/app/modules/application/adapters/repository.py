from sqlalchemy import Integer, LargeBinary, String, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import DomainError
from app.platform.database import Base


class ApplicationRecord(Base):
    __tablename__ = "application"
    __table_args__ = {"schema": "appl"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    position_id: Mapped[str] = mapped_column(String(64), index=True)
    active_key: Mapped[str | None] = mapped_column(String(140), unique=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class SqlApplications:
    def __init__(self, session, crypto):
        self.session, self.crypto = session, crypto

    def all(self):
        return [
            self.crypto.decrypt(r.data, r.id)
            for r in self.session.scalars(select(ApplicationRecord).order_by(ApplicationRecord.id))
        ]

    def get(self, aid):
        row = self.session.get(ApplicationRecord, aid, populate_existing=True)
        return self.crypto.decrypt(row.data, aid) if row else None

    def save(self, app, previous=None):
        values = dict(
            candidate_id=app["candidate_id"],
            position_id=app["position_id"],
            version=app["version"],
            active_key=None if app["outcome"] else app["canonical_id"] + ":" + app["position_id"],
            data=self.crypto.encrypt(app, app["id"]),
        )
        if previous is None:
            self.session.add(ApplicationRecord(id=app["id"], **values))
        else:
            result = self.session.execute(
                update(ApplicationRecord)
                .where(ApplicationRecord.id == app["id"], ApplicationRecord.version == previous)
                .values(**values)
                .execution_options(autoflush=False)
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "应聘记录已更新，请刷新", 409)
        self.session.flush()

    def erase(self, ids):
        self.session.execute(
            delete(ApplicationRecord).where(ApplicationRecord.candidate_id.in_(ids))
        )
