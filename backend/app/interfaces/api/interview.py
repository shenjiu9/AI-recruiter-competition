from fastapi import APIRouter, Query, Request

from app.interfaces.api.conversation import portal
from app.interfaces.api.dependencies import context, write
from app.modules.interview.contracts import Availability, Command

router = APIRouter(prefix="/api/v1", tags=["interview"])


@router.get("/hr/interviews")
@router.get("/biz/interviews")
def listing(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    position_id: str = "",
    application_id: str = "",
    candidate_id: str = "",
    state: str = "",
    mine: bool = False,
):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        rows = s.interview.list(
            ctx,
            position_id=position_id,
            application_id=application_id,
            candidate_id=candidate_id,
            state=state,
            mine=mine,
        )
        return {
            "items": rows[(page - 1) * size : page * size],
            "total": len(rows),
            "page": page,
            "size": size,
        }


@router.get("/hr/interviews/{iid}")
@router.get("/biz/interviews/{iid}")
def detail(request: Request, iid: str):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        return s.interview.dto(s.interview.authorize(ctx, iid), ctx)


@router.post("/hr/interviews/{iid}/actions")
@router.post("/biz/interviews/{iid}/actions")
def action(request: Request, iid: str, body: Command):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.interview.authorize(
            ctx, iid, edit=body.action not in {"feedback", "remark", "request_reschedule"}
        )
        result = write(
            request,
            ctx,
            s,
            body.model_dump(mode="json"),
            lambda: s.interview.command(ctx, iid, body),
        )
        return s.interview.dto(s.interview.authorize(ctx, result["id"]), ctx)


@router.get("/biz/interview-availability")
def preferences(request: Request):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        return s.interview.availability(ctx)


@router.post("/biz/interview-availability")
def save_preferences(request: Request, body: Availability):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.interview.availability(ctx)
        write(
            request,
            ctx,
            s,
            body.model_dump(),
            lambda: s.interview.availability(ctx, body) and {"id": ctx.principal.user_id},
        )
        return s.interview.availability(ctx)


@router.get("/candidate/interviews")
def candidate_interviews(request: Request):
    with request.app.state.container.scope() as s:
        s.org.lock_configuration()
        cid, _ = portal(s, request)
        return s.interview.list(cid=cid)


@router.post("/candidate/interviews/{iid}/actions")
def candidate_action(request: Request, iid: str, body: Command):
    with request.app.state.container.scope() as s:
        s.org.lock_configuration()
        cid, ctx = portal(s, request)
        s.interview.candidate_authorize(cid, iid)
        result = write(
            request,
            ctx,
            s,
            {"link": ctx.trace_id, **body.model_dump(mode="json")},
            lambda: s.interview.command(ctx, iid, body, cid),
        )
        return s.interview.dto(s.interview.candidate_authorize(cid, result["id"]), candidate=True)
