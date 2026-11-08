"""Durable AI proposals; business writes always pass the existing public commands."""

from datetime import timedelta

from app.engine.context import build
from app.engine.contracts import NODES
from app.engine.repository import instant
from app.engine.validation import INJECTION
from app.kernel.types import Ctx, DomainError, Principal, new_id
from app.modules.candidate.contracts import ApplicationCommand, CandidateCommand, Profile
from app.modules.position.contracts import PositionCommand

ACTIVE = {"queued", "running", "retry", "deferred", "review"}


class Engine:
    def __init__(self, services, jobs, gateway, clock, journal):
        self.s, self.jobs, self.gateway, self.clock, self.journal = (
            services,
            jobs,
            gateway,
            clock,
            journal,
        )

    def actor(self, job):
        user = self.s.org.get_user(job["actor_id"])
        if user.permission_version != job["permission_version"]:
            raise DomainError("PERMISSION_CHANGED", "任务发起人的权限已变化", 409)
        return Ctx(
            Principal(user.id, user.name, user.roles, user.departments, user.permission_version),
            job["trace_id"],
        )

    def access(self, ctx, job):
        self.s.candidate.lock(ctx)
        if job is None:
            raise DomainError("NOT_FOUND", "AI 任务不存在", 404)
        if job["component"] == "A2":
            for item in job["inputs"].get("candidates", []):
                person = self.s.candidate.authorize(ctx, item["candidate_id"])
                if (
                    person["id"] != item["candidate_id"]
                    or person["consent"] != "granted"
                    or person["do_not_contact"]
                ):
                    raise DomainError("CONSENT_REQUIRED", "匹配资料的授权已撤回，结果不再展示", 409)
        if job["component"] == "A6":
            iv = self.s.interview.authorize(ctx, job["object_id"])
            if not self.s.interview.assigned(iv, ctx.principal):
                raise DomainError("NOT_FOUND", "AI 任务不存在", 404)
        elif job["candidate_id"]:
            self.s.candidate.authorize(ctx, job["candidate_id"])
            if job["component"] == "A4" and not self.s.conversation.readable(
                ctx, job["candidate_id"], []
            ):
                raise DomainError("NOT_FOUND", "AI 任务不存在", 404)
            if job["application_id"]:
                self.s.application.authorize(ctx, job["application_id"])
        else:
            self.s.candidate.require_hr(ctx)
            if not self.s.position.get(ctx, job["position_id"])["canEdit"]:
                raise DomainError("NOT_FOUND", "AI 任务不存在", 404)
        return job

    def detail(self, ctx, key):
        job = self.access(ctx, self.jobs.get(key))
        return {
            k: v
            for k, v in job.items()
            if k not in {"permission_version", "lease", "partition_key", "prompt", "stamp"}
        }

    def listing(self, ctx):
        self.s.candidate.lock(ctx)
        result = []
        for job in self.jobs.all():
            try:
                self.access(ctx, job)
                result.append(
                    {
                        k: job[k]
                        for k in (
                            "id",
                            "version",
                            "component",
                            "object_id",
                            "status",
                            "created_at",
                            "updated_at",
                            "attempts",
                            "error_code",
                            "actor_id",
                        )
                    }
                )
            except DomainError:
                continue
        return list(reversed(result))

    def start(self, ctx, body, key=None):
        if body.candidate_ids is not None and body.component != "A2":
            raise DomainError("VALIDATION_ERROR", "只有简历匹配任务支持候选人名单")
        context = build(
            self.s, ctx, body.component, body.object_id, body.prompt, body.candidate_ids
        )
        config = self.s.automation.current()
        if not config["components"].get(body.component):
            raise DomainError("AI_DISABLED", "请先在自动化配置启用此组件", 409)
        if not self.gateway.configured(body.component):
            raise DomainError("AI_NOT_CONFIGURED", "此组件的 Dify 工作流或模型尚未配置", 503)
        if key and self.jobs.get(key):
            return {"id": key}
        now = self.clock.now().isoformat()
        job = {
            "id": key or new_id("AI"),
            "version": 1,
            "component": body.component,
            "object_id": body.object_id,
            "prompt": body.prompt,
            **context,
            "actor_id": ctx.principal.user_id,
            "permission_version": ctx.principal.permission_version,
            "trace_id": ctx.trace_id,
            "queue": "realtime" if body.component == "A4" else "batch",
            "status": "queued",
            "due_at": now,
            "created_at": now,
            "updated_at": now,
            "attempts": 0,
            "lease": None,
            "output": None,
            "runs": [],
            "history": [],
            "error_code": "",
            "shadow": config["mode"] == "shadow",
        }
        self.jobs.save(job)
        self.journal.record(ctx, "ai.queued", job["id"], 1, None, {"component": body.component})
        return {"id": job["id"]}

    def touch(self, job, status, ctx=None, code=""):
        previous = job["version"]
        job.update(
            version=previous + 1,
            status=status,
            updated_at=self.clock.now().isoformat(),
            error_code=code,
        )
        job["history"].append({"status": status, "at": job["updated_at"], "code": code})
        self.jobs.save(job, previous)
        if ctx:
            self.journal.record(
                ctx,
                "ai." + status,
                job["id"],
                job["version"],
                None,
                {"component": job["component"], "code": code},
            )

    def fresh(self, job):
        ctx = self.actor(job)
        self.access(ctx, job)
        config = self.s.automation.current()
        if not config["components"].get(job["component"]):
            raise DomainError("AI_DISABLED", "组件已关闭", 409)
        candidate_ids = (
            [c["candidate_id"] for c in job["inputs"].get("candidates", [])]
            if job["component"] == "A2"
            else None
        )
        current = build(
            self.s, ctx, job["component"], job["object_id"], job["prompt"], candidate_ids
        )
        if current["stamp"] != job["stamp"]:
            raise DomainError("AI_CONTEXT_CHANGED", "原文、权限、岗位或策略已变化，请重新生成", 409)
        return ctx

    def claim(self, queue):
        self.s.org.lock_configuration()
        now = self.clock.now()
        running = {
            j["partition_key"]
            for j in self.jobs.all()
            if j["status"] == "running" and instant(j["due_at"]) > now
        }
        for job in self.jobs.due(now, queue):
            if job["partition_key"] in running:
                continue
            try:
                ctx = self.fresh(job)
            except DomainError as exc:
                self.touch(job, "cancelled", code=exc.code)
                continue
            if job["status"] == "deferred":
                try:
                    with self.s.session.begin_nested():
                        self.execute(ctx, job)
                except DomainError as exc:
                    self.touch(job, "review", ctx, exc.code)
                continue
            if job["attempts"] >= 3:
                self.touch(job, "dead", ctx, "AI_ATTEMPTS_EXHAUSTED")
                continue
            job.update(
                attempts=job["attempts"] + 1,
                lease=new_id("LEASE"),
                due_at=(now + timedelta(seconds=400)).isoformat(),
            )
            self.touch(job, "running", ctx)
            return job
        return None

    def finish(self, key, lease, output=None, runs=None, error=None):
        self.s.org.lock_configuration()
        job = self.jobs.get(key)
        if not job or job["status"] != "running" or job["lease"] != lease:
            return  # Deleted/cancelled/leased again while the provider was running.
        try:
            ctx = self.fresh(job)
        except DomainError as exc:
            self.touch(job, "cancelled", code=exc.code)
            return
        job["runs"] += runs or []
        if error:
            job["due_at"] = (self.clock.now() + timedelta(seconds=3 ** job["attempts"])).isoformat()
            self.touch(job, "retry" if job["attempts"] < 3 else "dead", ctx, error)
            return
        job["output"] = output
        if job["shadow"]:
            self.touch(job, "shadow", ctx)
        elif self.auto_allowed(job):
            try:
                with self.s.session.begin_nested():
                    self.execute(ctx, job)
            except DomainError as exc:
                self.touch(job, "review", ctx, exc.code)
        else:
            self.touch(job, "review", ctx)

    def auto_allowed(self, job):
        component, data, output = job["component"], job["inputs"], job["output"]
        if component not in {"A4", "A5"} or not data["positions"]:
            return False
        confidence = output.get("confidence", output.get("self_confidence", 0))
        if confidence < self.s.automation.current()["high_threshold"]:
            return False
        if component == "A5" and output["conclusion"] != "advance":
            return False
        sensitive = bool(
            data.get("key_candidate")
            or data.get("confidential")
            or output.get("sensitive")
            or INJECTION.search(str(data))
        )
        if component == "A4" and (
            data.get("needs_human")
            or output["needs_human"]
            or output["intents"]
            or data["mode"] == "hr"
            or data.get("ai_paused")
        ):
            return False
        return all(
            self.s.automation.effective(
                NODES[component],
                {
                    **self.s.position.hiring_context(pid),
                    "series": self.s.position.hiring_context(pid)["fields"]["series"],
                },
                confidence,
                sensitive,
            )
            == 3
            for pid in data["positions"]
        )

    def execute(self, ctx, job):
        component, output = job["component"], job["output"]
        if component == "A1":
            pos = self.s.position.get(ctx, job["object_id"])
            self.s.position.command(
                ctx,
                job["object_id"],
                PositionCommand(
                    action="save_profile", expected_version=pos["version"], **output["fields"]
                ),
            )
        elif component == "A3":
            candidate = self.s.candidate.authorize(ctx, job["object_id"])
            fields = {k: v["value"] for k, v in output["fields"].items()}
            self.s.candidate.command(
                ctx,
                candidate["id"],
                CandidateCommand(
                    action="edit",
                    expected_version=candidate["version"],
                    profile=Profile(**{**candidate["profile"], **fields}),
                    reason="AI 提取经人工逐项核对",
                ),
            )
        elif component == "A4":
            due = self.s.conversation.ai_reply(
                ctx, job["candidate_id"], output["reply"], job["inputs"]["reply_to_id"], job["id"]
            )
            if due:
                job["due_at"] = due
                self.touch(job, "deferred", ctx)
                return
        elif component == "A5" and output["conclusion"] in {"advance", "reject"}:
            app, _ = self.s.application.authorize(ctx, job["object_id"])
            self.s.application.command(
                ctx,
                job["object_id"],
                ApplicationCommand(
                    action=output["conclusion"],
                    expected_version=app["version"],
                    reason="AI 证据评估：" + job["id"],
                    reason_code="requirements",
                ),
            )
        applied = component in {"A1", "A3", "A4"} or (
            component == "A5" and output["conclusion"] in {"advance", "reject"}
        )
        self.touch(job, "applied" if applied else "reviewed", ctx)

    def command(self, ctx, key, body):
        job = self.access(ctx, self.jobs.get(key))
        if body.expected_version != job["version"]:
            raise DomainError("VERSION_CONFLICT", "任务已变化，请刷新", 409)
        action = body.action
        if action in {"cancel", "reject"}:
            if job["status"] not in ACTIVE:
                raise DomainError("JOB_CLOSED", "该任务已结束", 409)
            job["review"] = {"by": ctx.principal.user_id, "reason": body.reason}
            self.touch(job, "cancelled" if action == "cancel" else "rejected", ctx)
        elif action == "retry":
            if job["status"] != "dead":
                raise DomainError("JOB_NOT_DEAD", "只有失败任务可重新排队", 409)
            self.fresh(job)
            job.update(attempts=0, lease=None, due_at=self.clock.now().isoformat())
            self.touch(job, "queued", ctx)
        else:
            if job["status"] != "review" or not body.verified:
                raise DomainError(
                    "REVIEW_REQUIRED", "请逐项核对原文证据后确认；影子结果不能执行", 409
                )
            self.fresh(job)
            job["review"] = {"by": ctx.principal.user_id, "reason": body.reason}
            self.execute(ctx, job)
        return {"id": key}

    def erase(self, ids):
        self.jobs.erase_candidates(ids)

    def health(self, ctx):
        self.s.candidate.lock(ctx)
        return {
            "components": {f"A{i}": self.gateway.configured(f"A{i}") for i in range(1, 8)},
            "mode": self.s.automation.current()["mode"],
            "enabled": self.s.automation.current()["components"],
        }
