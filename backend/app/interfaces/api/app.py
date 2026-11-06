import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException

from app.interfaces.api.auth import router as auth_router
from app.interfaces.api.candidate import router as candidate_router
from app.interfaces.api.conversation import router as conversation_router
from app.interfaces.api.interview import router as interview_router
from app.interfaces.api.org import router as org_router
from app.interfaces.api.organization import router as organization_router
from app.interfaces.api.position import router as pos_router
from app.interfaces.api.requisition import router as req_router
from app.kernel.types import DomainError


def create_api(container):
    @asynccontextmanager
    async def lifespan(app):
        from app.conversation_worker import run_once as conversation_tick
        from app.position_worker import run_once

        stop = asyncio.Event()

        async def work():
            while not stop.is_set():
                try:
                    if container.settings.position_worker_enabled:
                        await asyncio.to_thread(run_once, container)
                    if container.settings.conversation_worker_enabled:
                        await asyncio.to_thread(conversation_tick, container)
                except Exception as exc:
                    logging.getLogger("recruiter").warning(
                        "position_worker_unavailable type=%s", type(exc).__name__
                    )
                try:
                    await asyncio.wait_for(stop.wait(), timeout=2)
                except TimeoutError:
                    pass

        task = (
            asyncio.create_task(work())
            if (
                container.settings.position_worker_enabled
                or container.settings.conversation_worker_enabled
            )
            else None
        )
        try:
            yield
        finally:
            stop.set()
            if task:
                await task

    app = FastAPI(title="AI 招聘系统比赛版", version="0.1.0", lifespan=lifespan)
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Trace-ID"],
    )

    @app.middleware("http")
    async def trace(request: Request, call_next):
        request.state.trace_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Trace-ID"] = request.state.trace_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def error(request, code, message, status, details=None):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or {},
                    "trace_id": getattr(request.state, "trace_id", None),
                }
            },
        )

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return error(request, exc.code, exc.message, exc.status, exc.details)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Do not reflect request bodies (potential passwords/PII) into logs or errors.
        fields = [".".join(str(x) for x in e["loc"]) for e in exc.errors()]
        return error(request, "VALIDATION_ERROR", "参数格式错误", 400, {"fields": fields})

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(
            request,
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "接口不存在或尚未实现" if exc.status_code == 404 else str(exc.detail),
            exc.status_code,
        )

    @app.exception_handler(OperationalError)
    async def database_error(request, exc):
        return error(request, "DEPENDENCY_UNAVAILABLE", "数据库暂时不可用，请稍后重试", 503)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        logging.getLogger("recruiter").error(
            "unhandled_error trace_id=%s type=%s", request.state.trace_id, type(exc).__name__
        )
        return error(request, "INTERNAL_ERROR", "服务暂时无法完成请求，请稍后重试", 500)

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready():
        with container.db.engine.connect() as connection:
            table = (
                "platform.alembic_version"
                if connection.dialect.name == "postgresql"
                else "alembic_version"
            )
            connection.execute(text(f"SELECT version_num FROM {table}"))
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(org_router)
    app.include_router(organization_router)
    app.include_router(req_router)
    app.include_router(pos_router)
    app.include_router(candidate_router)
    app.include_router(conversation_router)
    app.include_router(interview_router)
    return app
