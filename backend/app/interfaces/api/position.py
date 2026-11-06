from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.interfaces.api.dependencies import context, write
from app.kernel.types import Ctx
from app.modules.position.contracts import GenerationCommand, PositionCommand

router = APIRouter(prefix="/api/v1/hr", tags=["positions"])
Context = Annotated[Ctx, Depends(context)]


@router.get("/positions")
def search(
    request: Request,
    ctx: Context,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Literal["to_publish", "open", "paused", "closed"] | None = None,
    view: Literal["all", "mine", "participating"] = "all",
    query: str = Query("", max_length=100),
    dept: str = Query("", max_length=100),
    owner: str = Query("", max_length=64),
    city: str = Query("", max_length=100),
):
    with request.app.state.container.scope() as services:
        return services.position.search(ctx, page, size, status, view, query, dept, owner, city)


@router.get("/positions/{pos_id}/knowledge-preview")
def knowledge_preview(request: Request, ctx: Context, pos_id: str, asked: bool = False):
    with request.app.state.container.scope() as services:
        return services.position.knowledge_for_reply(ctx, pos_id, asked)


@router.get("/positions/{pos_id}")
def detail(request: Request, ctx: Context, pos_id: str):
    with request.app.state.container.scope() as services:
        return services.position.get(ctx, pos_id)


@router.post("/positions/{pos_id}/actions")
def action(request: Request, ctx: Context, pos_id: str, command: PositionCommand):
    with request.app.state.container.scope() as services:
        services.position.authorize_write(ctx, pos_id)
        return write(
            request,
            ctx,
            services,
            command.model_dump(),
            lambda: services.position.command(ctx, pos_id, command),
        )


@router.get("/requisitions/{req_id}/position")
def generation(request: Request, ctx: Context, req_id: str):
    with request.app.state.container.scope() as services:
        return services.position.generation(ctx, req_id)


@router.post("/requisitions/{req_id}/position")
def resolve(request: Request, ctx: Context, req_id: str, command: GenerationCommand):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            command.model_dump(),
            lambda: services.position.resolve_generation(ctx, req_id, command),
        )
