import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.interfaces.api.dependencies import context, write
from app.kernel.types import DomainError
from app.modules.conversation.contracts import Command

router = APIRouter(prefix="/api/v1", tags=["conversation"])


def portal(s, request):
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise DomainError("LINK_INVALID", "请使用招聘 HR 提供的专属链接", 401)
    return s.conversation.verify(authorization[7:])


@router.get("/hr/candidates/{cid}/conversation")
def hr_conversation(request: Request, cid: str):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        return s.conversation.snapshot(cid, ctx)


@router.post("/hr/candidates/{cid}/conversation")
def hr_command(request: Request, cid: str, body: Command):
    ctx = context(request)
    with request.app.state.container.scope() as s:
        cid = s.conversation.authorize(ctx, cid)["id"]
        if body.action == "issue_link" and not s.conversation.readable(ctx, cid, []):
            raise DomainError("FORBIDDEN", "当前权限不能生成或读取候选人专属链接", 403)
        result = write(
            request, ctx, s, body.model_dump(), lambda: s.conversation.command(ctx, cid, body)
        )
        return {
            "conversation": s.conversation.snapshot(cid, ctx),
            **(s.conversation.link_result(cid, result["link_id"]) if result.get("link_id") else {}),
        }


@router.get("/candidate/session")
def candidate_session(request: Request):
    with request.app.state.container.scope() as s:
        s.org.lock_configuration()
        cid, _ = portal(s, request)
        return s.conversation.snapshot(cid)


@router.post("/candidate/actions")
def candidate_command(request: Request, body: Command):
    with request.app.state.container.scope() as s:
        s.org.lock_configuration()
        cid, ctx = portal(s, request)
        # Bind retries to the capability as well as the identity; never cache private DTOs.
        write(
            request,
            ctx,
            s,
            {"link": ctx.trace_id, **body.model_dump()},
            lambda: s.conversation.command(ctx, cid, body, portal=True),
        )
        return s.conversation.snapshot(cid)


def revision(request, cid=None):
    with request.app.state.container.scope() as s:
        if cid:
            ctx = context(request)
            data = s.conversation.snapshot(cid, ctx)
        else:
            s.org.lock_configuration()
            candidate_id, _ = portal(s, request)
            data = s.conversation.snapshot(candidate_id)
        return {
            "id": data["id"],
            "version": data["version"],
            "candidate_version": data["candidate_version"],
        }


async def stream(request, cid, once):
    initial = await asyncio.to_thread(revision, request, cid)

    async def events():
        data = initial
        previous = None
        for _ in range(60):
            if await request.is_disconnected():
                break
            current = json.dumps(data)
            if current != previous:
                yield "data: " + current + "\n\n"
                previous = current
            else:
                yield ": heartbeat\n\n"
            if once:
                break
            await asyncio.sleep(1)
            try:
                data = await asyncio.to_thread(revision, request, cid)
            except DomainError:
                break

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


@router.get("/hr/stream")
async def hr_stream(request: Request, candidate_id: str, once: bool = False):
    return await stream(request, candidate_id, once)


@router.get("/candidate/stream")
async def candidate_stream(request: Request, once: bool = False):
    return await stream(request, None, once)
