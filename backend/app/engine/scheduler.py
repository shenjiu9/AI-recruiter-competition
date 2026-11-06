from hashlib import sha256

from sqlalchemy import select

from app.engine.contracts import StartJob
from app.kernel.types import Ctx, DomainError, Principal
from app.platform.inbox import InboxRecord
from app.platform.records import AuditRecord, EventRecord

GROUP = "ai.events.v1"
EVENTS = {
    "application.stage_changed": "A5",
    "candidate.resume_added": "A3",
    "candidate.consent": "A3",
}


def actor(s, user_id, trace_id):
    user = s.org.get_user(user_id)
    return Ctx(
        Principal(user.id, user.name, user.roles, user.departments, user.permission_version),
        trace_id,
    )


def enqueue(s, ctx, component, object_id, origin):
    key = "AI-auto-" + sha256((component + ":" + origin).encode()).hexdigest()[:48]
    if s.engine.jobs.get(key):
        return
    if any(
        j["component"] == component
        and j["object_id"] == object_id
        and j["status"] in {"queued", "running", "retry", "deferred", "review"}
        for j in s.engine.jobs.all()
    ):
        return
    s.engine.start(ctx, StartJob(component=component, object_id=object_id), key)


def schedule(s, queue):
    s.org.lock_configuration()
    config = s.automation.current()
    if config["mode"] == "manual":
        return
    if queue == "realtime":
        if not config["components"]["A4"] or not s.engine.gateway.configured("A4"):
            return
        for item in s.conversation.ai_requests():
            try:
                pos = s.position.hiring_context(item["position_id"])
                with s.session.begin_nested():
                    enqueue(
                        s,
                        actor(s, pos["owner_id"], item["message_id"]),
                        "A4",
                        item["candidate_id"],
                        item["message_id"],
                    )
            except DomainError:
                continue
        return
    events = s.session.scalars(
        select(EventRecord)
        .outerjoin(
            InboxRecord,
            (InboxRecord.event_id == EventRecord.event_id) & (InboxRecord.consumer == GROUP),
        )
        .where(EventRecord.type.in_(EVENTS), InboxRecord.event_id.is_(None))
        .order_by(EventRecord.occurred_at, EventRecord.event_id)
        .limit(100)
    ).all()
    for event in events:
        component = EVENTS[event.type]
        code = None
        try:
            if not config["components"][component] or not s.engine.gateway.configured(component):
                continue
            audit = s.session.scalar(
                select(AuditRecord).where(
                    AuditRecord.trace_id == event.trace_id,
                    AuditRecord.action == event.type,
                    AuditRecord.object_id == event.partition_key,
                )
            )
            if audit is None or audit.actor_id.startswith("candidate:"):
                continue
            with s.session.begin_nested():
                enqueue(
                    s,
                    actor(s, audit.actor_id, event.trace_id),
                    component,
                    event.partition_key,
                    event.event_id,
                )
        except DomainError as exc:
            code = exc.code
        finally:
            s.session.add(
                InboxRecord(
                    event_id=event.event_id,
                    consumer=GROUP,
                    status="skipped" if code else "done",
                    attempts=1,
                    error_code=code,
                )
            )
