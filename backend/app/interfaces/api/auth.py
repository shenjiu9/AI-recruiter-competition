from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.interfaces.api.dependencies import context
from app.kernel.types import Ctx

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class DevLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(max_length=64)
    password: str = Field(min_length=1, max_length=200)


@router.get("/config")
def config(request: Request):
    return {"developmentLogin": request.app.state.container.settings.dev_auth_enabled}


@router.post("/dev-login")
def login(request: Request, body: DevLogin):
    with request.app.state.container.scope() as services:
        return services.auth.dev_login(body.user_id, body.password)


@router.get("/me")
def me(ctx: Annotated[Ctx, Depends(context)]):
    p = ctx.principal
    return {"userId": p.user_id, "name": p.name, "roles": p.roles}
