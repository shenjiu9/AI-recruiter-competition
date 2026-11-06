from sqlalchemy import Integer, LargeBinary, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base


class ConversationRecord(Base):
    __tablename__ = "conversation"
    __table_args__ = {"schema": "comm"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class SqlConversations:
    """Encrypted aggregate; every mutation holds the shared configuration transaction lock."""

    def __init__(self, session, crypto):
        self.session, self.crypto = session, crypto

    def get(self, cid):
        row = self.session.get(ConversationRecord, cid, populate_existing=True)
        return (
            self.crypto.decrypt(row.data, cid)
            if row
            else {
                "id": cid,
                "version": 0,
                "mode": "waiting_human",
                "owner_id": None,
                "messages": [],
                "links": [],
                "debounce_at": None,
            }
        )

    def save(self, c):
        row = self.session.get(ConversationRecord, c["id"])
        if not row:
            row = ConversationRecord(id=c["id"])
            self.session.add(row)
        row.version, row.data = c["version"], self.crypto.encrypt(c, c["id"])
        self.session.flush()

    def all(self):
        return [
            self.crypto.decrypt(r.data, r.id)
            for r in self.session.scalars(select(ConversationRecord))
        ]

    def erase(self, ids):
        self.session.execute(delete(ConversationRecord).where(ConversationRecord.id.in_(ids)))
