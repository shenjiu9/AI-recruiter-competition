from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.interfaces.api.dependencies import context, write
from app.modules.automation.public import AutomationCommand
from app.modules.hiring.contracts import CardCommand, HireCommand

router = APIRouter(prefix="/api/v1", tags=["hiring-decisions"])


@router.get("/hr/hiring/{key}/handoff.xlsx")
def handoff_export(request: Request, key: str):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        return Response(
            s.hiring.export(ctx, key),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": 'attachment; filename="hire-handoff.xlsx"',
                "Cache-Control": "no-store",
            },
        )


@router.get("/hr/hiring")
@router.get("/biz/hiring")
def listing(
    request: Request,
    position_id: str = "",
    candidate_id: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.decision.sync()
        rows = s.hiring.listing(ctx, position_id, candidate_id)
        return {"items": rows[(page - 1) * size : page * size], "total": len(rows)}


@router.get("/hr/hiring/{key}")
@router.get("/biz/hiring/{key}")
def detail(request: Request, key: str):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.decision.sync()
        return s.hiring.dto(ctx, *s.hiring.authorize(ctx, key))


@router.post("/hr/hiring/{key}/actions")
@router.post("/biz/hiring/{key}/actions")
def command(request: Request, key: str, body: HireCommand):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.decision.sync()
        s.hiring.authorize(ctx, key)
        result = write(
            request, ctx, s, body.model_dump(mode="json"), lambda: s.hiring.command(ctx, key, body)
        )
        s.decision.sync()
        return s.hiring.dto(ctx, *s.hiring.authorize(ctx, result["id"]))


@router.get("/hr/decision-cards")
@router.get("/biz/decision-cards")
def cards(
    request: Request,
    state: str = "open",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.decision.sync()
        rows = s.decision.listing(ctx, state)
        return {"items": rows[(page - 1) * size : page * size], "total": len(rows)}


@router.post("/hr/decision-cards/{key}/resolve")
@router.post("/biz/decision-cards/{key}/resolve")
def resolve(request: Request, key: str, body: CardCommand):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.decision.sync()
        s.decision.authorize(ctx, key)
        result = write(
            request, ctx, s, body.model_dump(), lambda: s.decision.resolve(ctx, key, body)
        )
        s.decision.sync()
        return s.decision.authorize(ctx, result["id"])


@router.get("/hr/workbench-live")
@router.get("/biz/workbench-live")
def workbench(request: Request):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.decision.sync()
        return s.query.workbench(ctx)


@router.get("/hr/automation-live")
def automation(
    request: Request,
    scope: Literal["global", "series", "position"] = "global",
    target: str = "",
    dept: str = "",
):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        return s.automation.get(ctx, scope, target, dept)


@router.post("/hr/automation-live")
def configure(request: Request, body: AutomationCommand):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        s.automation.key(ctx, body.scope, body.target, body.dept)
        write(request, ctx, s, body.model_dump(), lambda: s.automation.configure(ctx, body))
        return s.automation.get(ctx, body.scope, body.target, body.dept)
