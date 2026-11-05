from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.interfaces.api.dependencies import context, write
from app.kernel.types import Ctx
from app.modules.org.contracts import HeadcountCommand, SalaryBandCommand

router = APIRouter(prefix="/api/v1/admin", tags=["headcount"])
Context = Annotated[Ctx, Depends(context)]


@router.get("/salary-bands")
def salary_bands(
    request: Request, ctx: Context, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)
):
    with request.app.state.container.scope() as services:
        return services.org.salary_list(ctx, page, size)


@router.get("/salary-bands/{band_id}/history")
def salary_history(request: Request, ctx: Context, band_id: str):
    with request.app.state.container.scope() as services:
        return services.org.salary_history(ctx, band_id)


@router.post("/salary-bands")
def salary_save(request: Request, ctx: Context, command: SalaryBandCommand):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            command.model_dump(mode="json"),
            lambda: services.org.save_salary(ctx, command),
        )


@router.get("/headcount")
def headcount(request: Request, ctx: Context, year: int = Query(ge=2020, le=2100)):
    with request.app.state.container.scope() as services:
        return services.org.headcount_list(ctx, year)


@router.post("/headcount")
def save(
    request: Request, ctx: Context, command: HeadcountCommand, dept: str = Query(max_length=100)
):
    with request.app.state.container.scope() as services:
        return write(
            request,
            ctx,
            services,
            {"dept": dept, **command.model_dump(mode="json")},
            lambda: services.org.save_headcount(ctx, dept, command),
        )
