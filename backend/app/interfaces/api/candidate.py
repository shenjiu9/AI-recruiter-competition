from hashlib import sha256
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.interfaces.api.dependencies import context, write
from app.kernel.types import Ctx, DomainError
from app.modules.candidate.contracts import (
    ApplicationCommand,
    AttachCommand,
    CandidateCommand,
    CreateCandidate,
)

router = APIRouter(prefix="/api/v1/hr", tags=["candidates"])
Context = Annotated[Ctx, Depends(context)]


@router.get("/candidates")
def search(
    request: Request,
    ctx: Context,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    query: str = Query("", max_length=100),
    state: Literal["", "active", "idle", "do_not_contact"] = "",
    city: str = Query("", max_length=80),
    source: str = Query("", max_length=40),
):
    with request.app.state.container.scope() as s:
        return s.candidate.search(ctx, page, size, query, state, city, source)


@router.post("/candidates")
def create(request: Request, ctx: Context, body: CreateCandidate):
    with request.app.state.container.scope() as s:
        s.candidate.authorize(ctx)
        result = write(request, ctx, s, body.model_dump(), lambda: s.candidate.create(ctx, body))
        return {**result, "candidate": s.candidate.get(ctx, result["id"])}


@router.post("/candidate-resumes")
async def upload(
    request: Request,
    ctx: Context,
    filename: str = Query(min_length=1, max_length=200),
    candidate_id: str | None = Query(None, max_length=64),
):
    def authorize():
        with request.app.state.container.scope() as s:
            s.candidate.authorize(ctx, candidate_id)

    await run_in_threadpool(authorize)
    chunks, length = [], 0
    async for chunk in request.stream():
        length += len(chunk)
        if length > 20 * 1024 * 1024:
            raise DomainError("FILE_SIZE", "单个简历不能超过 20 MB", 413)
        chunks.append(chunk)
    data = b"".join(chunks)

    def ingest():
        with request.app.state.container.scope() as s:
            s.candidate.authorize(ctx, candidate_id)
            result = write(
                request,
                ctx,
                s,
                {
                    "filename": filename,
                    "candidate_id": candidate_id,
                    "sha256": sha256(data).hexdigest(),
                },
                lambda: s.candidate.ingest(ctx, filename, data, candidate_id),
            )
            return {**result, "candidate": s.candidate.get(ctx, result["id"])}

    return await run_in_threadpool(ingest)


@router.get("/candidates/{cid}")
def detail(request: Request, ctx: Context, cid: str):
    with request.app.state.container.scope() as s:
        return s.candidate.get(ctx, cid)


@router.post("/candidates/{cid}/contacts")
def contacts(request: Request, ctx: Context, cid: str):
    with request.app.state.container.scope() as s:
        return s.candidate.contacts(ctx, cid)


@router.get("/candidates/{cid}/resumes/{rid}/file")
def download(request: Request, ctx: Context, cid: str, rid: str):
    with request.app.state.container.scope() as s:
        filename, data = s.candidate.download(ctx, cid, rid)
        return Response(
            data,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
                "X-Content-Type-Options": "nosniff",
            },
        )


@router.post("/candidates/{cid}/actions")
def candidate_action(request: Request, ctx: Context, cid: str, body: CandidateCommand):
    with request.app.state.container.scope() as s:
        s.candidate.authorize(ctx, cid)
        result = write(
            request, ctx, s, body.model_dump(), lambda: s.candidate.command(ctx, cid, body)
        )
        return result if result.get("deleted") else s.candidate.get(ctx, result["id"])


@router.post("/applications")
def attach(request: Request, ctx: Context, body: AttachCommand):
    with request.app.state.container.scope() as s:
        s.candidate.authorize(ctx, body.candidate_id)
        s.position.authorize_write(ctx, body.position_id)
        result = write(request, ctx, s, body.model_dump(), lambda: s.application.open(ctx, body))
        return s.application.get(ctx, result["id"])


@router.get("/positions/{pid}/applications")
def position_applications(request: Request, ctx: Context, pid: str):
    with request.app.state.container.scope() as s:
        return s.application.for_position(ctx, pid)


@router.post("/applications/{aid}/actions")
def application_action(request: Request, ctx: Context, aid: str, body: ApplicationCommand):
    with request.app.state.container.scope() as s:
        s.application.authorize(ctx, aid)
        result = write(
            request, ctx, s, body.model_dump(), lambda: s.application.command(ctx, aid, body)
        )
        return s.application.get(ctx, result["id"])
