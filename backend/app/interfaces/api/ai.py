from fastapi import APIRouter, Query, Request

from app.engine.contracts import Ask, JobCommand, StartJob
from app.engine.intent import plan, route_text
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


@router.post("/hr/ai-intents")
def ask(request: Request, body: Ask):
    """Turn one natural-language sentence into an AI task and start it when unambiguous."""
    ctx = context(request)
    container = request.app.state.container
    with container.scope() as s:
        s.candidate.authorize(ctx)  # HR only, before spending a model call.
    # The router call happens with no transaction open, like every other model call.
    route, source = route_text(container.ai_gateway, body.text, ctx.trace_id)
    with container.scope() as s:
        s.candidate.lock(ctx)
        result = write(
            request,
            ctx,
            s,
            body.model_dump(),
            lambda: plan(s, ctx, body.text, route, source),
        )
        if result.get("job_id"):
            result = {**result, "job": s.engine.detail(ctx, result["job_id"])}
        return result
