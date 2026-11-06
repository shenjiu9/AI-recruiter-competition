import base64
import hashlib
import hmac

from sqlalchemy import Integer, LargeBinary, String, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column

from app.kernel.types import DomainError
from app.platform.database import Base


class CandidateRecord(Base):
    __tablename__ = "candidate"
    __table_args__ = {"schema": "cand"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    phone_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    email_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    merged_into: Mapped[str | None] = mapped_column(String(64), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)


class ResumeRecord(Base):
    __tablename__ = "resume"
    __table_args__ = {"schema": "cand"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    blob: Mapped[bytes] = mapped_column(LargeBinary)


class IdentityRecord(Base):
    __tablename__ = "candidate_identity"
    __table_args__ = {"schema": "cand"}
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(64), index=True)


class SqlCandidates:
    def __init__(self, session, crypto, key):
        self.session, self.crypto = session, crypto
        self.key = base64.urlsafe_b64decode(key)

    def digest(self, value):
        return (
            hmac.new(self.key, ("candidate-identity:" + value).encode(), hashlib.sha256).hexdigest()
            if value
            else None
        )

    def get(self, cid):
        row = self.session.get(CandidateRecord, cid, populate_existing=True)
        return self.crypto.decrypt(row.data, row.id) if row else None

    def all(self):
        return [
            self.crypto.decrypt(r.data, r.id)
            for r in self.session.scalars(select(CandidateRecord).order_by(CandidateRecord.id))
        ]

    def matches(self, profile, excluding=()):
        digests = [self.digest(profile[k]) for k in ("phone", "email") if profile[k]]
        ids = self.session.scalars(
            select(IdentityRecord.candidate_id).where(IdentityRecord.digest.in_(digests))
        )
        return [self.get(cid) for cid in set(ids) if cid not in excluding]

    def register_identity(self, cid, profile):
        for key in ("phone", "email"):
            digest = self.digest(profile[key])
            if digest and self.session.get(IdentityRecord, digest) is None:
                self.session.add(IdentityRecord(digest=digest, candidate_id=cid))
        self.session.flush()

    def save(self, candidate, previous=None):
        values = dict(
            version=candidate["version"],
            phone_hash=self.digest(candidate["profile"]["phone"]),
            email_hash=self.digest(candidate["profile"]["email"]),
            merged_into=candidate.get("merged_into"),
            data=self.crypto.encrypt(candidate, candidate["id"]),
        )
        if previous is None:
            self.session.add(CandidateRecord(id=candidate["id"], **values))
        else:
            result = self.session.execute(
                update(CandidateRecord)
                .where(CandidateRecord.id == candidate["id"], CandidateRecord.version == previous)
                .values(**values)
                .execution_options(autoflush=False)
            )
            if result.rowcount != 1:
                raise DomainError("VERSION_CONFLICT", "候选人已更新，请刷新后核对", 409)
        self.session.flush()

        self.register_identity(candidate["id"], candidate["profile"])

    def resumes(self, ids):
        return [
            self.crypto.decrypt(r.data, r.id)
            for r in self.session.scalars(
                select(ResumeRecord).where(ResumeRecord.candidate_id.in_(ids))
            )
        ]

    def save_resume(self, rid, cid, data, blob):
        self.session.add(
            ResumeRecord(
                id=rid,
                candidate_id=cid,
                data=self.crypto.encrypt(data, rid),
                blob=self.crypto.encrypt(
                    {"base64": base64.b64encode(blob).decode()}, rid + ":file"
                ),
            )
        )
        self.session.flush()

    def file(self, rid):
        r = self.session.get(ResumeRecord, rid)
        return base64.b64decode(self.crypto.decrypt(r.blob, rid + ":file")["base64"]) if r else None

    def erase(self, ids):
        self.session.execute(delete(IdentityRecord).where(IdentityRecord.candidate_id.in_(ids)))
        self.session.execute(delete(ResumeRecord).where(ResumeRecord.candidate_id.in_(ids)))
        self.session.execute(delete(CandidateRecord).where(CandidateRecord.id.in_(ids)))

    def save_resume_metadata(self, data):
        row = self.session.get(ResumeRecord, data["id"])
        row.data = self.crypto.encrypt(data, data["id"])
        self.session.flush()
