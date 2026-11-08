from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.interfaces.api.dependencies import context, write
from app.kernel.types import Ctx, DomainError
from app.modules.requisition.contracts import (
    ApprovalCommand,
    ApprovalNodeDTO,
    ConfirmationPreview,
    DraftPatch,
    PrecheckItem,
    RejectionCommand,
    RequisitionDetail,
    RequisitionPage,
    SubmitCommand,
    TransferCommand,
    VersionCommand,
)

router = APIRouter(prefix="/api/v1", tags=["requisitions"])
Context = Annotated[Ctx, Depends(context)]


@router.get("/hr/requisition-form/salary-options")
def form_salary_options(
    request: Request,
    ctx: Context,
    dept: str = Query(max_length=100),
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=100),
    requisition_id: str | None = None,
):
    with request.app.state.container.scope() as services:
        return services.requisition.form_salary_options(ctx, dept, page, size, requisition_id)


@router.get("/hr/requisition-form/departments")
def form_departments(request: Request, ctx: Context, requisition_id: str | None = None):
    with request.app.state.container.scope() as services:
        return services.requisition.form_departments(ctx, requisition_id)


@router.get("/hr/requisition-form/users")
def form_users(
    request: Request,
    ctx: Context,
    dept: str = Query(max_length=100),
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    selected: list[str] = Query(default=[], max_length=50),
    requisition_id: str | None = None,
):
    with request.app.state.container.scope() as services:
        return services.requisition.form_users(ctx, dept, q, page, size, selected, requisition_id)


@router.get("/hr/requisition-notifications")
def notifications(request: Request, ctx: Context):
    with request.app.state.container.scope() as services:
        return services.requisition.notifications(ctx)


@router.get("/hr/requisitions/{req_id}/transfer-candidates")
def transfer_candidates(
    request: Request,
    ctx: Context,
    req_id: str,
    q: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    with request.app.state.container.scope() as services:
        return services.requisition.transfer_candidates(ctx, req_id, q, page, size)


@router.post("/hr/requisitions/{req_id}/transfer", response_model=RequisitionDetail)
def transfer(request: Request, ctx: Context, req_id: str, command: TransferCommand):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            command.model_dump(),
            lambda: services.requisition.transfer(ctx, req_id, command),
        )


@router.get("/hr/requisitions", response_model=RequisitionPage)
def search(
    request: Request,
    ctx: Context,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = None,
):
    with request.app.state.container.scope() as services:
        return services.requisition.search(ctx, {"status": status}, (page, size))


@router.post("/hr/requisitions/precheck", response_model=list[PrecheckItem])
def precheck(request: Request, ctx: Context, fields: dict[str, str]):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            fields,
            lambda: services.requisition.precheck_fields(ctx, fields),
        )


@router.post("/hr/requisitions/approval-chain", response_model=list[ApprovalNodeDTO])
def chain(request: Request, ctx: Context, fields: dict[str, str]):
    with request.app.state.container.scope() as services:
        return write(
            request, ctx, services, fields, lambda: services.requisition.approval_chain(ctx, fields)
        )


@router.post("/hr/requisitions/ai-fill")
def ai_fill(request: Request, ctx: Context):
    raise DomainError("AI_DEGRADED", "AI 填表尚未配置，请手工填写；已填写的内容不会丢失", 503)


@router.post("/hr/requisitions/drafts", status_code=201, response_model=RequisitionDetail)
def draft(request: Request, ctx: Context, fields: dict[str, str]):
    with request.app.state.container.scope() as services:
        return write(
            request, ctx, services, fields, lambda: services.requisition.create_draft(ctx, fields)
        )


@router.post("/hr/requisitions", status_code=201, response_model=RequisitionDetail)
def create_and_submit(request: Request, ctx: Context, fields: dict[str, str]):
    with request.app.state.container.scope() as services:

        def operation():
            draft = services.requisition.create_draft(ctx, fields)
            return services.requisition.submit(ctx, draft["id"], draft["version"])

        return write(request, ctx, services, fields, operation)


@router.get("/hr/requisitions/{req_id}", response_model=RequisitionDetail)
def detail(request: Request, ctx: Context, req_id: str):
    with request.app.state.container.scope() as services:
        return services.requisition.get(ctx, req_id)


@router.patch("/hr/requisitions/{req_id}", response_model=RequisitionDetail)
def update_draft(request: Request, ctx: Context, req_id: str, command: DraftPatch):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            command.model_dump(),
            lambda: services.requisition.update_draft(
                ctx,
                req_id,
                command.fields,
                command.expected_version,
            ),
        )


@router.post("/hr/requisitions/{req_id}/submit", response_model=RequisitionDetail)
def submit(request: Request, ctx: Context, req_id: str, command: SubmitCommand):
    with request.app.state.container.scope() as services:

        def operation():
            version = command.expected_version
            if command.fields is not None:
                version = services.requisition.update_draft(ctx, req_id, command.fields, version)[
                    "version"
                ]
            return services.requisition.submit(ctx, req_id, version)

        return write(request, ctx, services, command.model_dump(), operation)


@router.post("/hr/requisitions/{req_id}/withdraw", response_model=RequisitionDetail)
def withdraw(request: Request, ctx: Context, req_id: str, command: VersionCommand):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            command.model_dump(),
            lambda: services.requisition.withdraw(ctx, req_id, command.expected_version),
        )


@router.post("/hr/requisitions/{req_id}/confirmation-preview", response_model=ConfirmationPreview)
def confirmation_preview(request: Request, ctx: Context, req_id: str, command: DraftPatch):
    with request.app.state.container.scope() as services:
        return services.requisition.confirmation_preview(
            ctx, req_id, command.fields, command.expected_version
        )


@router.post("/hr/requisitions/{req_id}/confirm", response_model=RequisitionDetail)
def confirm(request: Request, ctx: Context, req_id: str, command: DraftPatch):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            command.model_dump(),
            lambda: services.requisition.confirm(
                ctx, req_id, command.fields, command.expected_version
            ),
        )


@router.post("/hr/requisitions/{req_id}/approve", response_model=RequisitionDetail)
def approve(request: Request, ctx: Context, req_id: str, command: ApprovalCommand):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            command.model_dump(),
            lambda: services.requisition.approve(
                ctx,
                req_id,
                command.node_id,
                command.comment,
                command.expected_version,
            ),
        )


@router.post("/hr/requisitions/{req_id}/reject", response_model=RequisitionDetail)
def reject(request: Request, ctx: Context, req_id: str, command: RejectionCommand):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            command.model_dump(),
            lambda: services.requisition.reject(
                ctx,
                req_id,
                command.node_id,
                command.reason,
                command.expected_version,
            ),
        )


@router.get("/biz/inbox")
def inbox(request: Request, ctx: Context):
    with request.app.state.container.scope() as services:
        # First-batch inbox for requisition approvals; subsequent modules add their projections.
        page = 1
        items = []
        while True:
            found = services.requisition.search(ctx, {"status": "in_approval"}, (page, 100))
            for row in found["items"]:
                detail = services.requisition.get(ctx, row["id"])
                node = detail["chain"][detail["currentNode"]]
                if node["approver_id"] == ctx.principal.user_id:
                    items.append(
                        {
                            "id": row["id"],
                            "kind": "requisition_approval",
                            "title": row["title"],
                            "detail": f"{row['dept']} · {row['headcount']} 人 · {node['name']}",
                            "dueAt": (
                                datetime.fromisoformat(row["submittedAt"]) + timedelta(days=2)
                            ).isoformat(),
                            "version": row["version"],
                            "nodeId": node["id"],
                        }
                    )
            if page * 100 >= found["total"]:
                break
            page += 1
        return items
