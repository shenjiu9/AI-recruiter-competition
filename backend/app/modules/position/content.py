"""Versioned position content. All mutations use the facade's lock and transaction."""

from copy import deepcopy

from app.kernel.types import DomainError, new_id


def check_language(text):
    if any(
        word in text
        for word in (
            "男性优先",
            "女性优先",
            "仅限男性",
            "仅限女性",
            "已婚已育",
            "未婚未育",
            "不要孕妇",
        )
    ):
        raise DomainError("POSITION_JD_INVALID", "请修改画像或 JD 中的歧视性表述")


def normalize(pos):
    """Read legacy encrypted payloads without changing their persisted version."""
    profile = pos["profile"]
    profile.setdefault("must_ask", "")
    profile.setdefault("plus_weights", ["medium"] * len(profile["plus"].splitlines()))
    if "profiles" not in pos:
        initial = {
            "version": 1,
            "must": pos["fields"]["requirements"],
            "plus": "",
            "redflag": "",
            "jd": pos["fields"]["duties"],
            "confirmedBy": None,
            "source": "requisition",
            "must_ask": "",
            "plus_weights": [],
        }
        versions = {1: initial}
        for entry in pos["history"]:
            if entry.get("profile"):
                snapshot = deepcopy(entry["profile"])
                snapshot.setdefault("must_ask", "")
                snapshot.setdefault("plus_weights", ["medium"] * len(snapshot["plus"].splitlines()))
                versions[snapshot["version"]] = snapshot
        versions[profile["version"]] = deepcopy(profile)
        pos["profiles"] = [versions[v] for v in sorted(versions)]
    if "active_profile" not in pos:
        confirmed = [p for p in pos["profiles"] if p["confirmedBy"]]
        pos["active_profile"] = deepcopy(confirmed[-1]) if confirmed else None
    pos.setdefault("shared_ids", [])
    pos.setdefault("comments", [])
    pos.setdefault("knowledge", [])
    pos.setdefault("close_request", None)
    pos.setdefault("jd_approval_required", False)
    pos.setdefault(
        "jd",
        {
            "version": 1,
            "content": profile["jd"],
            "author": pos["owner_id"],
            "approvedBy": None,
            "status": "draft",
        },
    )
    pos.setdefault("jd_versions", [deepcopy(pos["jd"])])
    pos.setdefault("active_jd", deepcopy(pos["jd"]) if pos["status"] != "to_publish" else None)
    pos.setdefault("interview_plans", [])
    return pos


def replace_version(versions, item):
    versions[:] = [v for v in versions if v["version"] != item["version"]] + [deepcopy(item)]


class PositionContent:
    def _lead(self, ctx, pos):
        return "recruiting_lead" in ctx.principal.roles and pos["dept"] in ctx.principal.departments

    def _save_profile(self, ctx, pos, command):
        if not command.must.strip() or not command.jd.strip():
            raise DomainError("PROFILE_REQUIRED", "必备条件与 JD 职责不能为空")
        plus = [line.strip() for line in command.plus.splitlines() if line.strip()]
        if command.plus_weights and len(plus) != len(command.plus_weights):
            raise DomainError("PROFILE_WEIGHTS_INVALID", "每行加分项须对应一个权重")
        profile = {
            "version": pos["profile"]["version"] + 1,
            "must": command.must.strip(),
            "plus": "\n".join(plus),
            "redflag": command.redflag.strip(),
            "must_ask": command.must_ask.strip(),
            "plus_weights": command.plus_weights or ["medium"] * len(plus),
            "jd": command.jd.strip(),
            "confirmedBy": None,
            "source": "manual",
            "author": ctx.principal.user_id,
            "at": self.clock.now().isoformat(),
        }
        check_language(" ".join(profile[k] for k in ("must", "plus", "redflag", "must_ask", "jd")))
        pos["profile"] = profile
        pos["profiles"].append(deepcopy(profile))
        if command.jd.strip() != pos["jd"]["content"]:
            self._save_jd(ctx, pos, command.jd)

    def _confirm_profile(self, ctx, pos):
        if pos["profile"]["confirmedBy"]:
            raise DomainError("INVALID_TRANSITION", "当前画像不能重复确认", 409)
        check_language(
            " ".join(
                pos["profile"].get(k, "") for k in ("must", "plus", "redflag", "must_ask", "jd")
            )
        )
        pos["profile"].update(
            confirmedBy=ctx.principal.user_id, confirmedAt=self.clock.now().isoformat()
        )
        pos["active_profile"] = deepcopy(pos["profile"])
        replace_version(pos["profiles"], pos["profile"])

    def current_profile(self, pos_id):
        pos = self.store.get(pos_id)
        if not pos or not normalize(pos)["active_profile"]:
            raise DomainError("PROFILE_NOT_ACTIVE", "岗位尚无生效画像", 409)
        profile = deepcopy(pos["active_profile"])
        # Stable item references for downstream evaluation, no internal salary fields.
        profile["items"] = []
        for kind, key in (
            ("must", "must"),
            ("plus", "plus"),
            ("redflag", "redflag"),
            ("ask", "must_ask"),
        ):
            lines = [line for line in profile.get(key, "").splitlines() if line.strip()]
            for i, line in enumerate(lines):
                profile["items"].append(
                    {
                        "id": f"{pos_id}:v{profile['version']}:{kind}:{i + 1}",
                        "kind": kind,
                        "text": line,
                        "weight": profile["plus_weights"][i] if kind == "plus" else None,
                    }
                )
        return profile

    def _save_jd(self, ctx, pos, content):
        if not content.strip():
            raise DomainError("JD_REQUIRED", "JD 不能为空")
        check_language(content)
        pos["jd"] = {
            "version": pos["jd"]["version"] + 1,
            "content": content.strip(),
            "author": ctx.principal.user_id,
            "approvedBy": None,
            "status": "draft",
            "at": self.clock.now().isoformat(),
        }
        pos["jd_versions"].append(deepcopy(pos["jd"]))

    def _jd_ready(self, pos):
        check_language(pos["jd"]["content"])
        if pos["jd_approval_required"]:
            jd = pos["jd"]
            if jd["status"] != "approved" or not jd["approvedBy"]:
                raise DomainError("JD_APPROVAL_REQUIRED", "当前 JD 版本尚未由招聘负责人审批")
            user = self.org.get_user(jd["approvedBy"])
            if "recruiting_lead" not in user.roles or pos["dept"] not in user.departments:
                raise DomainError("JD_APPROVER_INVALID", "JD 审批人权限已变化，请重新审批")

    def content_action(self, ctx, pos, c):
        action, editor, manager = c.action, self._editor(ctx, pos), self._manager(ctx, pos)
        lead = self._lead(ctx, pos)
        allowed = {
            "save_jd": editor,
            "apply_jd": editor,
            "configure_publish": lead,
            "approve_jd": lead,
            "reject_jd": lead,
            "save_kb": editor or manager,
            "retire_kb": editor or manager,
            "share": editor,
            "comment": editor or manager,
            "request_close": editor,
            "confirm_close": manager,
            "reject_close": manager,
            "save_interview_plan": editor,
            "amend_confirm_profile": manager,
        }
        if action not in allowed:
            return False
        if not allowed[action]:
            raise DomainError("FORBIDDEN", "当前角色不能执行此岗位操作", 403)
        if action == "amend_confirm_profile":
            self._save_profile(ctx, pos, c)
            self._confirm_profile(ctx, pos)
        elif action == "save_jd":
            self._save_jd(ctx, pos, c.jd)
        elif action == "configure_publish":
            pos["jd_approval_required"] = c.jd_approval_required
        elif action in {"approve_jd", "reject_jd"}:
            if pos["jd"]["author"] == ctx.principal.user_id:
                raise DomainError("SELF_APPROVAL", "不能审批本人编辑的 JD", 403)
            if action == "reject_jd" and not c.reason.strip():
                raise DomainError("REASON_REQUIRED", "驳回原因不能为空")
            pos["jd"].update(
                status="approved" if action == "approve_jd" else "rejected",
                approvedBy=ctx.principal.user_id if action == "approve_jd" else None,
                reason=c.reason.strip(),
                reviewedAt=self.clock.now().isoformat(),
            )
            replace_version(pos["jd_versions"], pos["jd"])
        elif action == "apply_jd":
            if pos["status"] not in {"open", "paused"}:
                raise DomainError("INVALID_TRANSITION", "发布前请通过发布岗位使 JD 生效", 409)
            self._jd_ready(pos)
            pos["active_jd"] = deepcopy(pos["jd"])
        elif action in {"save_kb", "retire_kb"}:
            old = next((e for e in pos["knowledge"] if e["id"] == c.entry_id and e["active"]), None)
            if (c.entry_id or action == "retire_kb") and not old:
                raise DomainError("KB_NOT_CURRENT", "知识库条目已变更或下线，请刷新", 409)
            if action == "save_kb":
                if not c.content.strip() or not c.source.strip():
                    raise DomainError("KB_REQUIRED", "知识内容和来源不能为空")
                pos["knowledge"].append(
                    {
                        "id": new_id("KB"),
                        "version": old["version"] + 1 if old else 1,
                        "previous_id": c.entry_id,
                        "content": c.content.strip(),
                        "source": c.source.strip(),
                        "disclosure": c.disclosure,
                        "active": True,
                        "author": ctx.principal.user_id,
                        "at": self.clock.now().isoformat(),
                    }
                )
            if old:
                old["active"] = False
        elif action == "share":
            if ctx.principal.user_id != pos["owner_id"] and not lead:
                raise DomainError("FORBIDDEN", "仅负责 HR 或招聘负责人可调整协作成员", 403)
            if len(set(c.shared_ids)) != len(c.shared_ids) or pos["owner_id"] in c.shared_ids:
                raise DomainError("SHARED_INVALID", "共享人员不能重复或包含负责 HR")
            for uid in c.shared_ids:
                user = self.org.get_user(uid)
                if (
                    not {"recruiter", "recruiting_lead", "hrbp"}.intersection(user.roles)
                    or pos["dept"] not in user.departments
                ):
                    raise DomainError("SHARED_INVALID", "共享成员须具备本部门招聘权限")
            pos["shared_ids"] = c.shared_ids
        elif action == "comment":
            if not c.content.strip():
                raise DomainError("COMMENT_REQUIRED", "留言不能为空")
            members = {pos["owner_id"], pos["manager_id"], *pos["shared_ids"]}
            if any(uid not in members for uid in c.mentions):
                raise DomainError("MENTION_INVALID", "只能提及岗位协作成员")
            pos["comments"].append(
                {
                    "id": new_id("COMMENT"),
                    "author": ctx.principal.user_id,
                    "content": c.content.strip(),
                    "mentions": c.mentions,
                    "at": self.clock.now().isoformat(),
                }
            )
        elif action == "request_close":
            if pos["status"] not in {"open", "paused"} or pos["close_request"]:
                raise DomainError("INVALID_TRANSITION", "当前状态不能申请关闭或已有待确认申请", 409)
            self._close_reason(c.reason)
            pos["close_request"] = {
                "requester": ctx.principal.user_id,
                "reason": c.reason,
                "at": self.clock.now().isoformat(),
            }
        elif action in {"confirm_close", "reject_close"}:
            request = pos["close_request"]
            if not request:
                raise DomainError("CLOSE_REQUEST_MISSING", "没有待确认关闭申请", 409)
            if request["requester"] == ctx.principal.user_id:
                raise DomainError("SELF_APPROVAL", "不能确认自己发起的关闭申请", 403)
            if action == "reject_close" and not c.reason.strip():
                raise DomainError("REASON_REQUIRED", "驳回原因不能为空")
            if action == "confirm_close":
                self._close(ctx, pos, request["reason"])
            pos["close_request"] = None
        elif action == "save_interview_plan":
            if not c.rounds:
                raise DomainError("PLAN_REQUIRED", "面试须配置 1 至 6 轮")
            for r in c.rounds:
                if not r.name.strip() or not r.criteria.strip():
                    raise DomainError("PLAN_REQUIRED", "轮次名称和评价项不能为空")
                if r.format != "ai" and not r.interviewers:
                    raise DomainError("INTERVIEWER_REQUIRED", "人工面试须指定面试官")
                for uid in r.interviewers:
                    user = self.org.get_user(uid)
                    if pos["dept"] not in user.departments or not {
                        "interviewer",
                        "hiring_manager",
                        "recruiter",
                        "recruiting_lead",
                    }.intersection(user.roles):
                        raise DomainError(
                            "INTERVIEWER_INVALID", "面试官须在职且具备部门范围和面试角色"
                        )
                if r.rule == "designated" and r.decision_by not in r.interviewers:
                    raise DomainError("DECIDER_INVALID", "指定决定人须在本轮面试官中")
            pos["interview_plans"].append(
                {
                    "version": len(pos["interview_plans"]) + 1,
                    "rounds": [r.model_dump() for r in c.rounds],
                    "author": ctx.principal.user_id,
                    "at": self.clock.now().isoformat(),
                }
            )
        return True

    def _close_reason(self, reason):
        if reason not in {"招满", "需求取消", "组织调整", "其他"}:
            raise DomainError("POSITION_CLOSE_INVALID", "请选择关闭原因")

    def _close(self, ctx, pos, reason):
        if pos["status"] not in {"open", "paused"}:
            raise DomainError("INVALID_TRANSITION", "只能关闭招聘中或已暂停岗位", 409)
        self._close_reason(reason)
        if self.applications:
            self.applications.close_position(ctx, pos["id"])
        for source in sorted(pos["sources"], key=lambda s: s["id"]):
            self.org.release_headcount(ctx, source["id"])
        pos["status"] = "closed"
        pos["closed_reason"] = reason
        pos["close_request"] = None

    def knowledge_for_reply(self, ctx, pos_id, asked=False, refs=None):
        pos = normalize(self._get(ctx, pos_id))
        entries = [e for e in pos["knowledge"] if e["active"]]
        levels = {"proactive", "asked"} if asked else {"proactive"}
        safe = [e for e in entries if e["disclosure"] in levels] if not pos["confidential"] else []
        if refs is not None and not set(refs).issubset({e["id"] for e in safe}):
            raise DomainError("KB_REFERENCE_INVALID", "知识引用已失效或不允许本次披露", 409)
        return {
            "entries": [
                {k: e[k] for k in ("id", "version", "content", "source", "disclosure")}
                for e in safe
            ],
            "needsHuman": not safe or any(e["disclosure"] == "handoff" for e in entries),
        }
