from sqlalchemy import delete, select, update

from app.kernel.types import DomainError


class EncryptedStore:
    """Versioned encrypted aggregates; callers hold the organization transaction lock."""

    def __init__(self, session, crypto, model):
        self.session, self.crypto, self.model = session, crypto, model

    def get(self, key):
        row = self.session.get(self.model, key, populate_existing=True)
        return self.crypto.decrypt(row.data, key) if row else None

    def all(self):
        return [self.crypto.decrypt(r.data, r.id) for r in self.session.scalars(select(self.model))]

    def save(self, data, previous=None):
        values = {"version": data["version"], "data": self.crypto.encrypt(data, data["id"])}
        if previous is None:
            self.session.add(self.model(id=data["id"], **values))
        elif (
            self.session.execute(
                update(self.model)
                .where(self.model.id == data["id"], self.model.version == previous)
                .values(**values)
            ).rowcount
            != 1
        ):
            raise DomainError("VERSION_CONFLICT", "记录已变化，请刷新核对", 409)
        self.session.flush()

    def erase(self, key):
        self.session.execute(delete(self.model).where(self.model.id == key))
