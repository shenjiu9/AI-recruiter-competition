from datetime import datetime, timedelta

from app.kernel.types import DomainError, new_id

STAGES = ["reach", "talking", "ai_eval", "interview", "manager_eval", "hired"]


class ApplicationFacade:
    def __init__(self, store, candidates, positions, clock, journal):
        self.conversations = None
        self.store, self.candidates, self.positions, self.clock, self.journal = (
            store,
            candidates,
            positions,
            clock,
            journal,
        )

    def for_candidates(self, ids):
        return [a for a in self.store.all() if a["candidate_id"] in ids]

    def visible(self, ctx, app):
        try:
            self.positions.get(ctx, app["position_id"])
            return True
        except DomainError as exc:
            if exc.status != 404:
                raise
            return False

    def dto(self, ctx, app, brief=False):
        summary = {
            "id": app["id"],
            "position_id": app["position_id"],
            "position_name": app["position_name"],
            "started_at": app["started_at"],
            "outcome": app["outcome"],
            "restricted": brief,
        }
        if brief:
            return summary
        pos = self.positions.get(ctx, app["position_id"])
        c = self.candidates.canonical(app["candidate_id"])
        result = {
            **app,
            **summary,
            "candidate_id": c["id"],
            "candidate_name": c["profile"]["name"],
            "can_edit": pos["canEdit"],
            "can_rollback": pos["canLead"] or ctx.principal.user_id == pos["ownerId"],
        }
        if not self.candidates.hr(ctx):
            for key in ("evidence", "forced_attach_reason", "history"):
                result.pop(key, None)
            result = self.candidates.mask_tree(result)
        return result

    def authorize(self, ctx, aid):
        self.candidates.lock(ctx)
        app = self.store.get(aid)
        if not app or not self.visible(ctx, app):
            raise DomainError("NOT_FOUND", "应聘记录不存在或不在可见范围内", 404)
        pos = self.positions.get(ctx, app["position_id"])
        if not pos["canEdit"]:
            raise DomainError("FORBIDDEN", "仅岗位负责 HR、共享 HR 或招聘负责人可操作应聘记录", 403)
        return app, pos

    def cooldown(self, cid, position):
        latest = None
        for app in self.for_candidates(self.candidates.family(cid)):
            if app["outcome"] != "rejected":
                continue
            same = app["position_id"] == position["id"] or (
                app["series"]
                and app["series"] == position["series"]
                and app["level"] == position["level"]
            )
            until = datetime.fromisoformat(app["ended_at"]) + timedelta(days=182)
            if same and until > self.clock.now() and (latest is None or until > latest):
                latest = until
        return latest.isoformat() if latest else None

    def open(self, ctx, command):
        c = self.candidates.authorize(ctx, command.candidate_id)
        pos = self.positions.application_context(ctx, command.position_id)
        if not pos["canEdit"]:
            raise DomainError("FORBIDDEN", "仅岗位招聘成员可以挂入候选人", 403)
        if pos["status"] != "open":
            raise DomainError("POSITION_NOT_OPEN", "仅招聘中的岗位可以挂人", 409)
        if not self.candidates.contactable(c["id"]):
            raise DomainError("NOT_CONTACTABLE", "候选人已要求不再联系或撤回授权", 409)
        apps = self.for_candidates(self.candidates.family(c["id"]))
        if any(a["position_id"] == pos["id"] and not a["outcome"] for a in apps):
            raise DomainError("ACTIVE_APPLICATION_EXISTS", "候选人已在本岗位流程中", 409)
        if any(a["stage"] == "hired" and not a["outcome"] for a in apps):
            raise DomainError("ALREADY_HIRED", "候选人已录用，请先处理录用结果", 409)
        until = self.cooldown(c["id"], pos)
        if command.source == "candidate" and not command.evidence:
            raise DomainError("EVIDENCE_REQUIRED", "登记主动投递须填写投递证据")
        if until and command.source != "candidate" and not command.reason:
            raise DomainError(
                "COOLDOWN",
                f"候选人处于冷却期至 {until[:10]}，强制挂入须填原因",
                409,
                {"until": until},
            )
        app = {
            "id": new_id("APP"),
            "candidate_id": c["id"],
            "canonical_id": c["id"],
            "position_id": pos["id"],
            "position_name": pos["name"],
            "series": pos["series"],
            "level": pos["level"],
            "version": 1,
            "stage": "reach",
            "furthest_stage": "reach",
            "outcome": None,
            "started_at": self.clock.now().isoformat(),
            "ended_at": None,
            "source": command.source,
            "forced_attach_reason": command.reason if until else "",
            "evidence": command.evidence,
            "previous_rejection_until": until,
            "history": [],
            "reason": "",
            "reason_code": "",
            "outcome_stage": None,
            "notice_status": "not_requested",
            "notice_at": None,
            "owner_id": pos["ownerId"],
        }
        self.store.save(app)
        self.journal.record(ctx, "application.created", app["id"], 1, None, {"stage": "reach"})
        if until and command.reason:
            self.journal.record(
                ctx, "application.force_attach", app["id"], 1, None, {}, event=False
            )
        return {"id": app["id"], "candidate_id": c["id"]}

    def save(self, ctx, app, action, previous_stage=None):
        old = app["version"]
        app["version"] += 1
        app["history"].append(
            {
                "action": action,
                "from_stage": previous_stage or app["stage"],
                "to_stage": app["stage"],
                "actor": ctx.principal.user_id,
                "at": self.clock.now().isoformat(),
                "reason": app["reason"],
            }
        )
        self.store.save(app, old)
        self.journal.record(
            ctx,
            "application." + action,
            app["id"],
            app["version"],
            None,
            {"stage": app["stage"], "outcome": app["outcome"]},
        )

    def command(self, ctx, aid, command):
        from app.modules.candidate.contracts import AttachCommand

        app, pos = self.authorize(ctx, aid)
        if app["version"] != command.expected_version:
            raise DomainError("VERSION_CONFLICT", "应聘记录已更新，请刷新", 409)
        action = command.action
        if action == "undo_reject":
            if app["outcome"] != "rejected" or app["notice_status"] == "sent":
                raise DomainError("INVALID_TRANSITION", "当前不能撤销淘汰", 409)
            if pos["status"] == "closed":
                raise DomainError("POSITION_CLOSED", "已关闭岗位不能恢复应聘", 409)
            if any(
                a["id"] != aid and a["position_id"] == app["position_id"] and not a["outcome"]
                for a in self.for_candidates(self.candidates.family(app["canonical_id"]))
            ):
                raise DomainError("ACTIVE_APPLICATION_EXISTS", "该候选人已有新的进行中记录", 409)
            if not command.reason:
                raise DomainError("REASON_REQUIRED", "撤销须填写原因")
            app.update(
                outcome=None,
                ended_at=None,
                notice_status="cancelled",
                notice_at=None,
                reason=command.reason,
            )
            self.conversations.cancel_notice(ctx, app["canonical_id"], aid)
            self.save(ctx, app, "reopened")
            return {"id": aid}
        if app["outcome"] or pos["status"] == "closed":
            raise DomainError("INVALID_TRANSITION", "已结束的应聘记录只读", 409)
        if (
            pos["status"] == "paused"
            and self.positions.application_context(ctx, pos["id"])["pause_mode"] == "freeze"
        ):
            if action in {"advance", "rollback"}:
                raise DomainError("POSITION_FROZEN", "岗位已冻结，应聘阶段暂不能变更", 409)
        old_stage = app["stage"]
        app["reason"] = command.reason
        if action == "advance":
            index = STAGES.index(app["stage"])
            next_stage = STAGES[index + 1] if index < len(STAGES) - 1 else None
            if command.target_stage and command.target_stage != next_stage:
                raise DomainError("INVALID_TRANSITION", "只能推进至下一阶段", 409)
            if next_stage in {"manager_eval", "hired", None}:
                raise DomainError("WORKFLOW_REQUIRED", "需由面试完成或录用审批流程推进该阶段", 409)
            if next_stage == "ai_eval":
                self.candidates.evaluation_input(app["canonical_id"])
            app["stage"] = next_stage
            if STAGES.index(next_stage) > STAGES.index(app["furthest_stage"]):
                app["furthest_stage"] = next_stage
            self.save(ctx, app, "stage_changed", old_stage)
        elif action == "rollback":
            if not (pos["canLead"] or pos["ownerId"] == ctx.principal.user_id):
                raise DomainError("FORBIDDEN", "仅负责 HR 或招聘负责人可以回退", 403)
            if (
                not command.reason
                or not command.target_stage
                or STAGES.index(command.target_stage) >= STAGES.index(app["stage"])
            ):
                raise DomainError("INVALID_TRANSITION", "请选择较早阶段并填写回退原因", 409)
            app["stage"] = command.target_stage
            self.save(ctx, app, "stage_changed", old_stage)
        else:
            if not command.reason or (action == "reject" and not command.reason_code):
                raise DomainError("REASON_REQUIRED", "请填写终止原因；淘汰须选择原因分类")
            if command.notify and action != "reject":
                raise DomainError(
                    "DELIVERY_NOT_READY", "通知发送将在沟通模块接入；当前可选择不发送通知"
                )
            app.update(
                outcome={"reject": "rejected", "withdraw": "withdrawn", "transfer": "transferred"}[
                    action
                ],
                ended_at=self.clock.now().isoformat(),
                outcome_stage=app["stage"],
                reason_code=command.reason_code,
            )
            if command.notify:
                app["notice_at"] = self.conversations.queue_notice(ctx, app)
                app["notice_status"] = "queued"
            self.save(ctx, app, "ended")
            if action == "transfer":
                self.open(
                    ctx,
                    AttachCommand(
                        candidate_id=app["canonical_id"],
                        position_id=command.target_position_id,
                        reason=command.reason,
                    ),
                )
        return {"id": aid}

    def get(self, ctx, aid):
        app = self.store.get(aid)
        if not app or not self.visible(ctx, app):
            raise DomainError("NOT_FOUND", "应聘记录不存在", 404)
        return self.dto(ctx, app)

    def for_position(self, ctx, pid):
        self.positions.get(ctx, pid)
        return [self.dto(ctx, a) for a in self.store.all() if a["position_id"] == pid]

    def counts(self, pid):
        apps = [a for a in self.store.all() if a["position_id"] == pid]
        return {
            "total": len(apps),
            "active": sum(not a["outcome"] for a in apps),
            "hired": sum(a["stage"] == "hired" and not a["outcome"] for a in apps),
            "stages": {
                stage: sum(a["stage"] == stage and not a["outcome"] for a in apps)
                for stage in STAGES
            },
        }

    def close_position(self, ctx, pid):
        for app in self.store.all():
            if app["position_id"] == pid and not app["outcome"]:
                app.update(
                    outcome="position_closed",
                    ended_at=self.clock.now().isoformat(),
                    outcome_stage=app["stage"],
                    reason="岗位关闭",
                    notice_status="cancelled",
                )
                self.save(ctx, app, "ended")

    def rekey(self, ids, canonical_id):
        apps = self.store.all()
        occupied = {
            a["position_id"]
            for a in apps
            if a["canonical_id"] == canonical_id
            and a["candidate_id"] not in ids
            and not a["outcome"]
        }
        for app in apps:
            if app["candidate_id"] not in ids:
                continue
            if not app["outcome"] and app["position_id"] in occupied:
                raise DomainError(
                    "MERGE_ACTIVE_CONFLICT",
                    "两个档案在同一岗位均有进行中记录，请先终止其中一条",
                    409,
                )
            app["canonical_id"] = canonical_id
            old = app["version"]
            app["version"] += 1
            self.store.save(app, old)

    def erase(self, ids):
        self.store.erase(ids)

    def public_statuses(self, cid):
        labels = {
            "reach": "沟通中",
            "talking": "沟通中",
            "ai_eval": "评估中",
            "interview": "面试中",
            "manager_eval": "等待结果",
            "hired": "已通过，HR 会联系您沟通后续",
        }
        return [
            {
                "id": a["id"],
                "position_name": a["position_name"],
                "status": "已结束"
                if a["notice_status"] == "sent" or a["outcome"] in {"withdrawn", "transferred"}
                else labels.get(a["stage"], "等待结果"),
            }
            for a in self.for_candidates(self.candidates.family(cid))
        ]

    def deliver_notice(self, ctx, aid):
        app, _ = self.authorize(ctx, aid)
        if app["outcome"] != "rejected" or app["notice_status"] != "queued":
            raise DomainError("NOTICE_CANCELLED", "应聘结果已变更")
        app.update(notice_status="sent", notice_at=self.clock.now().isoformat())
        self.save(ctx, app, "notice_delivered")

    def cancel_delivery(self, ctx, aid):
        app = self.store.get(aid)
        if app and app["notice_status"] == "queued":
            app.update(notice_status="cancelled", notice_at=None)
            self.save(ctx, app, "notice_cancelled")
