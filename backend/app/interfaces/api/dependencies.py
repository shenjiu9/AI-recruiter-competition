from fastapi import Request

from app.kernel.types import Ctx, DomainError


def context(request: Request) -> Ctx:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise DomainError("UNAUTHENTICATED", "请先登录", 401)
    with request.app.state.container.scope() as services:
        principal = services.auth.current_principal(authorization[7:])
    return Ctx(principal, request.state.trace_id)


def write(request, ctx, services, payload, operation):
    return services.idempotency.run(
        ctx.principal.user_id,
        request.method + ":" + request.url.path,
        request.headers.get("Idempotency-Key"),
        payload,
        operation,
    )
