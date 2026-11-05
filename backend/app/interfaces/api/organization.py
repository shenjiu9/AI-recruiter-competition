from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from app.interfaces.api.dependencies import context, write
from app.kernel.types import Ctx
from app.modules.org.contracts import ApprovalPolicyCommand, ApprovalTrial, PermissionCommand

router = APIRouter(prefix="/api/v1/admin/organization", tags=["organization"])
Context = Annotated[Ctx, Depends(context)]


@router.get("/departments")
def departments(request: Request, ctx: Context):
    with request.app.state.container.scope() as services:
        return services.org.configuration.departments(ctx)


@router.get("/users")
def users(
    request: Request,
    ctx: Context,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str = Query("", max_length=100),
):
    with request.app.state.container.scope() as services:
        return services.org.configuration.users(ctx, page, size, q)


@router.post("/users/{user_id}/permissions")
def permissions(request: Request, ctx: Context, user_id: str, command: PermissionCommand):
    with request.app.state.container.scope() as services:
        services.org.configuration.authorize(ctx, write=True)
        return write(
            request,
            ctx,
            services,
            command.model_dump(),
            lambda: services.org.configuration.save_permissions(ctx, user_id, command),
        )


@router.post("/approval")
def approval(
    request: Request,
    ctx: Context,
    command: ApprovalPolicyCommand,
    dept: str = Query(min_length=1, max_length=100),
):
    with request.app.state.container.scope() as services:
        services.org.configuration.authorize(ctx, write=True)
        return write(
            request,
            ctx,
            services,
            {"dept": dept, **command.model_dump()},
            lambda: services.org.configuration.save_policy(ctx, dept, command),
        )


@router.get("/history")
def history(
    request: Request,
    ctx: Context,
    kind: Literal["permissions", "approval"],
    object_id: str = Query(min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    with request.app.state.container.scope() as services:
        return services.org.configuration.history(ctx, kind, object_id, page, size)


@router.post("/trial")
def trial(
    request: Request,
    ctx: Context,
    command: ApprovalTrial,
    dept: str = Query(min_length=1, max_length=100),
):
    with request.app.state.container.scope() as services:
        return services.org.configuration.trial(ctx, dept, command)
