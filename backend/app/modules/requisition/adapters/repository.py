from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, or_, select, update

from app.kernel.types import DomainError
from app.modules.requisition.adapters.orm import AccessRecord, RequisitionRecord
from app.modules.requisition.domain.model import Requisition


class SqlRepository:
    def __init__(self, session, crypto):
        self.session, self.crypto = session, crypto

    def _values(self, req):
        payload = {
            "fields": req.fields,
            "mode": req.mode,
            "chain": req.chain,
            "history": req.history,
            "hc_approver": req.hc_approver,
            "current_node": req.current_node,
            "submitted_at": req.submitted_at.isoformat() if req.submitted_at else None,
        }
        return dict(
            version=req.version,
            creator_id=req.creator_id,
            manager_id=req.manager_id,
            dept=req.dept,
            status=req.status,
            confidential=req.fields.get("confidential") == "1",
            created_at=req.created_at,
            data=self.crypto.encrypt(payload, req.id),
        )

    def _entity(self, record):
        payload = self.crypto.decrypt(record.data, record.id)
        submitted = payload.pop("submitted_at")
        created = record.created_at
        return Requisition(
            id=record.id,
            version=record.version,
            creator_id=record.creator_id,
            manager_id=record.manager_id,
            dept=record.dept,
            status=record.status,
            created_at=created.replace(tzinfo=UTC) if created.tzinfo is None else created,
            submitted_at=datetime.fromisoformat(submitted) if submitted else None,
            **payload,
        )

    def _access(self, req):
        self.session.execute(delete(AccessRecord).where(AccessRecord.requisition_id == req.id))
        users = {req.creator_id, req.manager_id, *(n["approver_id"] for n in req.chain)}
        users.update(x.strip() for x in req.fields.get("visibleTo", "").split(",") if x.strip())
        self.session.add_all(AccessRecord(requisition_id=req.id, user_id=u) for u in users)

    def get(self, req_id):
        record = self.session.get(RequisitionRecord, req_id)
        return self._entity(record) if record else None

    def add(self, req):
        self.session.add(RequisitionRecord(id=req.id, **self._values(req)))
        self._access(req)
        self.session.flush()

    def save(self, req, expected_version):
        result = self.session.execute(
            update(RequisitionRecord)
            .execution_options(autoflush=False)
            .where(
                RequisitionRecord.id == req.id,
                RequisitionRecord.version == expected_version,
            )
            .values(**self._values(req))
        )
        if result.rowcount != 1:
            raise DomainError("VERSION_CONFLICT", "需求已被其他人修改，请刷新后重试", 409)
        self._access(req)
        self.session.flush()

    def search(self, principal, page, size, status):
        visible = select(AccessRecord.requisition_id).where(
            AccessRecord.user_id == principal.user_id
        )
        scope = RequisitionRecord.id.in_(visible)
        if {"recruiter", "recruiting_lead", "hrbp"}.intersection(principal.roles):
            scope = or_(
                scope,
                and_(
                    RequisitionRecord.dept.in_(principal.departments),
                    RequisitionRecord.confidential.is_(False),
                ),
            )
        filters = [scope]
        if status:
            filters.append(RequisitionRecord.status == status)
        total = self.session.scalar(
            select(func.count()).select_from(RequisitionRecord).where(*filters)
        )
        records = self.session.scalars(
            select(RequisitionRecord)
            .where(*filters)
            .order_by(
                RequisitionRecord.created_at.desc(),
                RequisitionRecord.id,
            )
            .offset((page - 1) * size)
            .limit(size)
        )
        return [self._entity(r) for r in records], total
