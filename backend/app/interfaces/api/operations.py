from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.engine.repository import JobRecord
from app.interfaces.api.dependencies import context
from app.kernel.types import DomainError
from app.platform.inbox import InboxRecord

router = APIRouter(prefix="/api/v1/hr", tags=["operations"])


@router.get("/operations")
def operations(request: Request):
    ctx = context(request)
    container = request.app.state.container
    with container.scope() as s:
        s.candidate.lock(ctx)
        if "admin" not in ctx.principal.roles:
            raise DomainError("FORBIDDEN", "运行状态仅限管理员查看", 403)
        # Aggregate metadata only: never return candidate data, prompts or secrets.
        jobs = dict(
            s.session.execute(
                select(JobRecord.status, func.count()).group_by(JobRecord.status)
            ).all()
        )
        receipts = dict(
            s.session.execute(
                select(InboxRecord.status, func.count()).group_by(InboxRecord.status)
            ).all()
        )
        oldest = s.session.scalar(
            select(func.min(JobRecord.due_at)).where(
                JobRecord.status.in_(["queued", "retry", "deferred", "running"])
            )
        )
        if oldest is not None and oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=container.clock.now().tzinfo)
        return {
            "jobs": jobs,
            "event_receipts": receipts,
            "oldest_due_delay_seconds": max(
                0, int((container.clock.now() - oldest).total_seconds())
            )
            if oldest
            else 0,
            "ai_worker_enabled": container.settings.ai_worker_enabled,
            "dify_configured": {
                f"A{i}": container.ai_gateway.configured(f"A{i}") for i in range(1, 8)
            },
            "external_services": {
                "feishu": "not_configured",
                "meeting": "manual_confirmation",
                "email_sms": "not_configured",
                "channels": "not_configured",
            },
        }
