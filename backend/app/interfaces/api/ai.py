from fastapi import APIRouter, Query, Request

from app.engine.contracts import JobCommand, StartJob
from app.interfaces.api.dependencies import context, write
from app.kernel.types import DomainError

router = APIRouter(prefix="/api/v1", tags=["ai-tasks"])


@router.get("/hr/ai-health")
@router.get("/biz/ai-health")
def health(request: Request):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        return {
            **s.engine.health(ctx),
            "worker_enabled": request.app.state.container.settings.ai_worker_enabled,
        }


@router.get("/hr/ai-jobs")
@router.get("/biz/ai-jobs")
def listing(request: Request, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        rows = s.engine.listing(ctx)
        return {"items": rows[(page - 1) * size : page * size], "total": len(rows)}


@router.post("/hr/ai-jobs")
@router.post("/biz/ai-jobs")
def start(request: Request, body: StartJob):
    ctx = context(request)
    if "/biz/" in request.url.path and body.component != "A6":
        raise DomainError("FORBIDDEN", "业务端仅支持本轮面评草稿", 403)
    with request.app.state.container.scope() as s:
        # Authorize before consulting idempotency so revoked access cannot replay a response.
        s.candidate.lock(ctx)
        result = write(request, ctx, s, body.model_dump(), lambda: s.engine.start(ctx, body))
        return s.engine.detail(ctx, result["id"])


@router.get("/hr/ai-jobs/{key}")
@router.get("/biz/ai-jobs/{key}")
def detail(request: Request, key: str):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        return s.engine.detail(ctx, key)


@router.post("/hr/ai-jobs/{key}/actions")
@router.post("/biz/ai-jobs/{key}/actions")
def command(request: Request, key: str, body: JobCommand):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.engine.access(ctx, s.engine.jobs.get(key))
        result = write(request, ctx, s, body.model_dump(), lambda: s.engine.command(ctx, key, body))
        return s.engine.detail(ctx, result["id"])
