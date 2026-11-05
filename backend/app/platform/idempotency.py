import hashlib
import json
from datetime import UTC, timedelta

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.kernel.types import DomainError
from app.platform.records import RequestRecord


class Idempotency:
    """The reservation, business writes, journal and response share one transaction."""

    def __init__(self, session, clock, crypto):
        self.session, self.clock, self.crypto = session, clock, crypto

    def run(self, actor: str, scope: str, key: str | None, payload: dict, operation):
        if not key or len(key) > 200:
            raise DomainError("VALIDATION_ERROR", "请提供不超过 200 字符的 Idempotency-Key", 400)
        digest = hashlib.sha256(f"{actor}\0{scope}\0{key}".encode()).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        insert = pg_insert if self.session.bind.dialect.name == "postgresql" else sqlite_insert
        now = self.clock.now()
        self.session.execute(
            insert(RequestRecord)
            .values(
                key=digest,
                fingerprint=fingerprint,
                expires_at=now + timedelta(hours=24),
            )
            .on_conflict_do_nothing(index_elements=["key"])
        )
        record = self.session.scalar(
            select(RequestRecord).where(RequestRecord.key == digest).with_for_update()
        )
        expires = (
            record.expires_at.replace(tzinfo=UTC)
            if record.expires_at.tzinfo is None
            else record.expires_at
        )
        if expires > now:
            if record.fingerprint != fingerprint:
                raise DomainError("IDEMPOTENCY_CONFLICT", "同一幂等键不能用于不同请求内容", 409)
            if record.response is not None:
                return self.crypto.decrypt(record.response, digest)
        result = jsonable_encoder(operation())
        record.fingerprint = fingerprint
        record.response = self.crypto.encrypt(result, digest)
        record.expires_at = now + timedelta(hours=24)
        self.session.flush()
        return result
