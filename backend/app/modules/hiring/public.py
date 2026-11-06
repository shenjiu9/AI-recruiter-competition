import json
import re
from copy import deepcopy
from hashlib import sha256

from app.kernel.types import Ctx, DomainError, Principal

SYSTEM = Ctx(Principal("system:hiring", "录用待办", (), ()), "hiring-worker")
HIRED = {"approved", "handed_over", "accepted", "joined"}


def fingerprint(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class HiringFacade:
    def __init__(
        self,
        store,
        applications,
        candidates,
        positions,
        interviews,
        org,
        automation,
        calendar,
        clock,
        journal,
    ):
        self.store, self.applications, self.candidates, self.positions = (
            store,
            applications,
            candidates,
            positions,
        )
        self.interviews, self.org, self.automation, self.calendar, self.clock, self.journal = (
            interviews,
            org,
            automation,
            calendar,
            clock,
            journal,
        )
        self.decisions = None

    def save(self, ctx, h, action):
        old = h["version"]
        h["version"] += 1
        h["history"].append(
            {"action": action, "actor": ctx.principal.user_id, "at": self.clock.now().isoformat()}
        )
        self.store.save(h, old)
        self.journal.record(
            ctx, "hire." + action, h["id"], h["version"], None, {"status": h["status"]}
        )

    def records(self):
        return self.store.all()

    def guard_merge(self, ids):
        if any(
            h["candidate_id"] in ids and h["status"] in HIRED | {"pending"}
            for h in self.store.all()
        ):
            raise DomainError("HIRE_ACTIVE", "请先处理在途录用，不能合并或拆分档案", 409)

    def context_stamp(self, app, pos):
        c = self.candidates.canonical(app["candidate_id"])
        return fingerprint(
            [
                app["version"],
                pos["version"],
                c["version"] if c else 0,
                self.interviews.hiring_summary(app["id"]),
            ]
        )

    def sync(self):
        self.org.lock_configuration()
        for app in self.applications.hiring_applications():
            key = "HIRE-" + app["id"]
            h = self.store.get(key)
            eligible = app["stage"] == "manager_eval" and not app["outcome"]
            if not eligible:
                if h and h["status"] in {"deciding", "pending"}:
                    h["status"] = "cancelled"
                    self.save(SYSTEM, h, "invalidated")
                continue
            pos = self.positions.hiring_context(app["position_id"])
            stamp = self.context_stamp(app, pos)
            if h is None:
                h = {
                    "id": key,
                    "version": 1,
                    "application_id": app["id"],
                    "candidate_id": app["candidate_id"],
                    "position_id": app["position_id"],
                    "status": "deciding",
                    "context": stamp,
                    "facts": None,
                    "chain": [],
                    "history": [],
                    "reminders": [],
                    "decision_by": None,
                    "created_at": self.clock.now().isoformat(),
                    "due_at": self.calendar.deadline(self.clock.now().isoformat(), 2).isoformat(),
                    "handoff": None,
                    "result": None,
                    "source_id": None,
                }
                self.store.save(h)
                self.journal.record(
                    SYSTEM, "hire.review_created", key, 1, None, {"status": "deciding"}
                )
            elif h["status"] in {"deciding", "pending", "cancelled", "rejected"} and (
                h["context"] != stamp or h["status"] == "cancelled"
            ):
                h["history"].append(
                    {
                        "action": "previous_review",
                        "facts": h["facts"],
                        "chain": h["chain"],
                        "at": self.clock.now().isoformat(),
                    }
                )
                h.update(
                    status="deciding",
                    context=stamp,
                    facts=None,
                    chain=[],
                    decision_by=None,
                    due_at=self.calendar.deadline(self.clock.now().isoformat(), 2).isoformat(),
                )
                self.save(SYSTEM, h, "context_changed")
        for h in self.store.all():
            if (
                h["status"] in {"deciding", "pending", "handed_over", "accepted"}
                and self.clock.now().isoformat() >= h["due_at"]
            ):
                key = h["due_at"]
                if not any(r["key"] == key for r in h["reminders"]):
                    h["reminders"].append(
                        {
                            "key": key,
                            "kind": "decision"
                            if h["status"] in {"deciding", "pending"}
                            else "result",
                            "delivery": "in_app",
                            "at": self.clock.now().isoformat(),
                        }
                    )
                    h["due_at"] = self.calendar.deadline(
                        self.clock.now().isoformat(), 5
                    ).isoformat()
                    self.save(SYSTEM, h, "reminded")

    def permissions(self, ctx, h, pos):
        p = ctx.principal
        scoped = pos["dept"] in p.departments
        manager = scoped and "hiring_manager" in p.roles and p.user_id == pos["manager_id"]
        hr = (
            scoped
            and self.candidates.hr(ctx)
            and (p.user_id in {pos["owner_id"], *pos["shared_ids"]} or "recruiting_lead" in p.roles)
        )
        approver = False
        for node in h["chain"]:
            if node["user_id"] == p.user_id:
                try:
                    self.org.check_approver(p.user_id, pos["dept"], node["role"])
                    approver = True
                except DomainError:
                    pass
        return manager, hr, approver

    def authorize(self, ctx, key):
        self.candidates.lock(ctx)
        if ctx.principal.user_id.startswith(("ai:", "system:")):
            raise DomainError("HUMAN_REQUIRED", "录用必须由人处理", 403)
        h = self.store.get(key)
        if not h:
            raise DomainError("NOT_FOUND", "录用记录不存在", 404)
        pos = self.positions.hiring_context(h["position_id"])
        if not any(self.permissions(ctx, h, pos)):
            raise DomainError("NOT_FOUND", "录用记录不存在或无权查看", 404)
        return h, pos

    def stamp(self, ctx, h, pos):
        app = self.applications.interview_context(h["application_id"])
        return fingerprint([ctx.principal.user_id, h["version"], self.context_stamp(app, pos)])

    def dto(self, ctx, h, pos):
        manager, hr, approver = self.permissions(ctx, h, pos)
        c = self.candidates.canonical(h["candidate_id"])
        financial = hr or (approver and "hrd" in ctx.principal.roles)
        summary = self.interviews.hiring_summary(h["application_id"])
        totals = {}
        for iv in summary:
            for f in iv["feedback"].values():
                for k, v in f["scores"].items():
                    totals.setdefault(k, []).append(v)
        facts = deepcopy(h["facts"])
        if facts and not financial:
            facts = {
                k: v
                for k, v in facts.items()
                if k in {"expected_start", "offer_owner", "salary_over", "prepared_at"}
            }
        current = next((n for n in h["chain"] if n["status"] == "pending"), None)
        return {
            k: h[k]
            for k in (
                "id",
                "version",
                "application_id",
                "position_id",
                "candidate_id",
                "status",
                "chain",
                "due_at",
                "reminders",
                "result",
            )
        } | {
            "candidate_name": c["profile"]["name"],
            "department": pos["dept"],
            "position_name": pos["fields"]["title"],
            "remaining": max(0, pos["planned"] - pos["hired"]),
            "facts": facts,
            "feedback": self.candidates.mask_tree(summary),
            "averages": {k: round(sum(v) / len(v), 2) for k, v in totals.items()},
            "can_prepare": hr and h["status"] == "deciding",
            "can_decide": manager and h["status"] == "deciding",
            "can_approve": bool(
                approver
                and current
                and current["user_id"] == ctx.principal.user_id
                and h["status"] == "pending"
            ),
            "can_withdraw": (hr or manager) and h["status"] == "pending",
            "can_handover": hr and h["status"] == "approved",
            "can_result": hr and h["status"] in {"handed_over", "accepted"},
            "review_stamp": self.stamp(ctx, h, pos),
            "handoff": h["handoff"] if hr else None,
            "ai_advice": None,
            "history": [
                {k: v for k, v in r.items() if k in {"action", "actor", "at", "reason"}}
                for r in h["history"]
            ],
        }

    def listing(self, ctx, pid="", cid=""):
        self.candidates.lock(ctx)
        rows = []
        for h in self.store.all():
            if (
                pid
                and h["position_id"] != pid
                or cid
                and h["candidate_id"] not in self.candidates.family(cid)
            ):
                continue
            try:
                _, p = self.authorize(ctx, h["id"])
                rows.append(self.dto(ctx, h, p))
            except DomainError:
                continue
        return sorted(rows, key=lambda h: (h["due_at"], h["id"]))

    def chain(self, h, pos):
        config = self.automation.current()
        policy = self.org.policy(pos["dept"])
        grade = re.search(r"\d+", pos["fields"]["level"])
        roles = list(config["approval_nodes"])
        if h["facts"]["salary_over"] or (grade and int(grade.group()) >= config["hrd_grade"]):
            roles.append("salary")
        nodes = []
        for role in roles:
            uid = {"director": policy.director_id, "hrbp": policy.hrbp_id, "salary": policy.hrd_id}[
                role
            ]
            if uid == h["decision_by"]:
                raise DomainError(
                    "SELF_APPROVAL", "录用决定人与审批人相同，请管理员配置独立审批人", 409
                )
            user = self.org.check_approver(uid, pos["dept"], role)
            if any(n["user_id"] == uid for n in nodes) and role != "salary":
                continue
            nodes.append({"role": role, "user_id": uid, "name": user.name, "status": "pending"})
        h["policy_version"] = config["version"]
        return nodes

    def finalize(self, ctx, h, pos):
        self.applications.hiring_transition(ctx, h["application_id"], "hire")
        counts = self.allocations(pos["id"])
        source = next((s for s in pos["sources"] if counts.get(s["id"], 0) < s["count"]), None)
        if not source:
            raise DomainError("HIRE_CAPACITY", "需求名额不足", 409)
        h.update(status="approved", source_id=source["id"])
        c = self.candidates.canonical(h["candidate_id"])
        h["handoff"] = {
            "candidate": deepcopy(c["profile"]),
            "position": deepcopy(pos["fields"]),
            "facts": deepcopy(h["facts"]),
            "feedback": self.interviews.hiring_summary(h["application_id"]),
            "chain": deepcopy(h["chain"]),
            "owner_id": pos["owner_id"],
            "generated_at": self.clock.now().isoformat(),
            "delivery": "not_sent",
        }

    def command(self, ctx, key, command):
        h, pos = self.authorize(ctx, key)
        if h["version"] != command.expected_version:
            raise DomainError("VERSION_CONFLICT", "录用记录或上下文已变化，请刷新", 409)
        manager, hr, approver = self.permissions(ctx, h, pos)
        a = command.action
        if a in {"prepare", "decide", "approve"}:
            app = self.applications.interview_context(h["application_id"])
            if (
                app["stage"] != "manager_eval"
                or app["outcome"]
                or pos["status"] == "closed"
                or pos["frozen"]
            ):
                raise DomainError("HIRE_NOT_READY", "应聘已变更或岗位已关闭 / 冻结", 409)
            if not self.candidates.contactable(h["candidate_id"]):
                raise DomainError("CONSENT_REQUIRED", "请先处理候选人授权和不再联系状态", 409)
        if a == "prepare":
            if not hr or h["status"] != "deciding":
                raise DomainError("FORBIDDEN", "仅负责 HR 可准备待决定记录", 403)
            if (
                not command.verified
                or command.salary_k is None
                or not command.evidence
                or not command.expected_start
            ):
                raise DomainError("FACTS_REQUIRED", "须核实期望月薪、薪资月数、到岗日期及证据")
            if command.expected_start < self.clock.now().date():
                raise DomainError("DATE_INVALID", "预计到岗日不能早于今天")
            owner = self.org.get_user(command.offer_owner)
            if (
                not set(owner.roles).intersection({"recruiter", "recruiting_lead", "hrbp"})
                or pos["dept"] not in owner.departments
            ):
                raise DomainError("OWNER_INVALID", "移交负责人须具备本部门招聘权限")
            salary = self.org.salary_check(
                pos["fields"]["series"],
                pos["fields"]["level"],
                pos["fields"]["city"],
                (command.salary_k, command.salary_k, command.salary_months),
            )
            if any(c["status"] == "block" for c in salary["checks"]):
                raise DomainError("SALARY_CONFIG_REQUIRED", "职级薪资表缺少生效配置，请先维护", 409)
            h["facts"] = {
                "salary_k": command.salary_k,
                "salary_months": command.salary_months,
                "expected_start": command.expected_start.isoformat(),
                "offer_owner": command.offer_owner,
                "evidence": command.evidence,
                "salary_over": salary["over"],
                "salary_refs": salary["refs"],
                "prepared_at": self.clock.now().isoformat(),
            }
        elif a == "decide":
            if not manager or h["status"] != "deciding":
                raise DomainError("FORBIDDEN", "录用决定只能由岗位用人经理本人完成", 403)
            if not command.verified or command.review_stamp != self.stamp(ctx, h, pos):
                raise DomainError("REVIEW_REQUIRED", "请打开最新面评汇总并核实后再决定", 409)
            if command.decision == "hire":
                if not h["facts"]:
                    raise DomainError("FACTS_REQUIRED", "请 HR 先核实薪资与移交信息", 409)
                h["decision_by"] = ctx.principal.user_id
                salary = self.org.salary_check(
                    pos["fields"]["series"],
                    pos["fields"]["level"],
                    pos["fields"]["city"],
                    (h["facts"]["salary_k"], h["facts"]["salary_k"], h["facts"]["salary_months"]),
                )
                if any(c["status"] == "block" for c in salary["checks"]):
                    raise DomainError(
                        "SALARY_CONFIG_REQUIRED", "提交时薪资配置已失效，请 HR 重新核实", 409
                    )
                h["facts"].update(salary_over=salary["over"], salary_refs=salary["refs"])
                h["chain"] = self.chain(h, pos)
                h["status"] = "pending"
                if not h["chain"]:
                    self.finalize(ctx, h, pos)
            elif command.decision == "reject" and command.reason:
                self.applications.hiring_transition(
                    ctx, h["application_id"], "reject", command.reason
                )
                h["status"] = "rejected"
            elif command.decision == "extra_round" and command.extra_round and command.reason:
                app = self.applications.hiring_transition(
                    ctx, h["application_id"], "extra_round", command.reason
                )
                self.interviews.extra_round(ctx, app, command.extra_round)
                h["status"] = "cancelled"
            else:
                raise DomainError(
                    "DECISION_REQUIRED", "请选择决定；不录用或追加面试须填写原因及轮次"
                )
        elif a in {"approve", "reject"}:
            current = next((n for n in h["chain"] if n["status"] == "pending"), None)
            if (
                h["status"] != "pending"
                or not approver
                or not current
                or current["user_id"] != ctx.principal.user_id
            ):
                raise DomainError("FORBIDDEN", "仅当前审批人可处理", 403)
            if not command.verified or command.review_stamp != self.stamp(ctx, h, pos):
                raise DomainError("REVIEW_REQUIRED", "请查看最新面评和审批内容后确认", 409)
            if a == "reject" and not command.reason:
                raise DomainError("REASON_REQUIRED", "驳回须填写原因")
            current.update(
                status="approved" if a == "approve" else "rejected",
                at=self.clock.now().isoformat(),
                reason=command.reason,
            )
            if a == "reject":
                h["status"] = "deciding"
                h["history"].append(
                    {
                        "action": "approval_rejected",
                        "chain": deepcopy(h["chain"]),
                        "reason": command.reason,
                        "at": self.clock.now().isoformat(),
                    }
                )
            elif all(n["status"] == "approved" for n in h["chain"]):
                self.finalize(ctx, h, pos)
        elif a == "withdraw":
            if not (manager or hr) or h["status"] != "pending" or not command.reason:
                raise DomainError("INVALID_TRANSITION", "仅经理或负责 HR 可填写原因撤回审批", 409)
            h["history"].append(
                {
                    "action": "approval_withdrawn",
                    "chain": deepcopy(h["chain"]),
                    "at": self.clock.now().isoformat(),
                }
            )
            h["status"] = "deciding"
        elif a == "handover":
            if not hr or h["status"] != "approved" or not command.verified or not command.evidence:
                raise DomainError("HANDOFF_REQUIRED", "负责 HR 须核实实际移交并填写凭证", 409)
            owner_id = command.offer_owner or h["facts"]["offer_owner"]
            owner = self.org.get_user(owner_id)
            if (
                not set(owner.roles).intersection({"recruiter", "recruiting_lead", "hrbp"})
                or pos["dept"] not in owner.departments
            ):
                raise DomainError("OWNER_INVALID", "移交负责人已失去权限，请重新选择")
            h["facts"]["offer_owner"] = owner_id
            h["handoff"]["facts"]["offer_owner"] = owner_id
            h["handoff"].update(
                delivery="manual_confirmed",
                evidence=command.evidence,
                delivered_at=self.clock.now().isoformat(),
            )
            h.update(
                status="handed_over",
                due_at=self.calendar.deadline(self.clock.now().isoformat(), 5).isoformat(),
            )
        elif a == "result":
            if not hr or h["status"] not in {"handed_over", "accepted"} or not command.verified:
                raise DomainError("INVALID_TRANSITION", "仅负责 HR 可核实并回填已移交记录", 409)
            if command.result == "accepted":
                if (
                    h["status"] != "handed_over"
                    or not command.expected_start
                    or command.expected_start < self.clock.now().date()
                ):
                    raise DomainError("DATE_REQUIRED", "接受后须填写有效的预计入职日")
            elif command.result == "joined":
                if h["status"] != "accepted":
                    raise DomainError("INVALID_TRANSITION", "请先登记已接受", 409)
                self.applications.hiring_transition(ctx, h["application_id"], "joined")
            elif command.result in {"declined", "no_show"} and command.reason:
                self.applications.hiring_transition(
                    ctx, h["application_id"], command.result, command.reason
                )
            else:
                raise DomainError("RESULT_REQUIRED", "请选择结果；失败结果须填写原因")
            h.update(
                status=command.result,
                result={
                    "value": command.result,
                    "reason": command.reason,
                    "expected_start": command.expected_start.isoformat()
                    if command.expected_start
                    else None,
                    "at": self.clock.now().isoformat(),
                },
                due_at=self.calendar.deadline(self.clock.now().isoformat(), 5).isoformat(),
            )
        self.save(ctx, h, a)
        if a == "result" and h["status"] in {"declined", "no_show"} and pos["status"] == "closed":
            self.release_closed_capacity(ctx, pos)
        return {"id": h["id"]}

    def allocations(self, pid):
        counts = {}
        for h in self.store.all():
            if h["position_id"] == pid and h["status"] in HIRED and h["source_id"]:
                counts[h["source_id"]] = counts.get(h["source_id"], 0) + 1
        return counts

    def export(self, ctx, key):
        from app.modules.hiring.export import workbook

        h, pos = self.authorize(ctx, key)
        if not self.permissions(ctx, h, pos)[1] or not h["handoff"]:
            raise DomainError("FORBIDDEN", "仅负责 HR 可导出已生成的移交单", 403)
        data = h["handoff"]
        rows = [
            ("录用移交单", key),
            ("当前状态", h["status"]),
            ("姓名", data["candidate"]["name"]),
            ("电话", data["candidate"].get("phone")),
            ("邮箱", data["candidate"].get("email")),
            ("岗位", pos["fields"]["title"]),
            ("职级", data["position"]["level"]),
            ("城市", data["position"]["city"]),
            ("汇报对象", data["position"].get("reportTo")),
            ("期望月薪（K）", data["facts"]["salary_k"]),
            ("薪资月数", data["facts"]["salary_months"]),
            ("预计到岗日", data["facts"]["expected_start"]),
            ("移交负责人", self.org.identity(data["facts"]["offer_owner"])["name"]),
            ("移交状态", data["delivery"]),
            ("交接凭证", data.get("evidence", "")),
        ]
        for iv in data["feedback"]:
            for f in iv["feedback"].values():
                rows.extend(
                    [
                        (iv["round_name"], f["author"]),
                        ("结论", f["recommendation"]),
                        ("评分", json.dumps(f["scores"], ensure_ascii=False)),
                        ("优势", f["strengths"]),
                        ("顾虑", f["concerns"]),
                    ]
                )
        rows.extend(("审批：" + n["name"], n["status"]) for n in data["chain"])
        self.journal.record(ctx, "hire.handoff_exported", key, h["version"], None, {}, False)
        return workbook(rows)

    def release_closed_capacity(self, ctx, pos):
        counts = self.allocations(pos["id"])
        for source in pos["sources"]:
            self.org.release_headcount(ctx, source["id"], retain=counts.get(source["id"], 0))

    def erase(self, ids):
        if self.decisions:
            for app in self.applications.hiring_applications():
                if app["candidate_id"] in ids:
                    self.decisions.erase_application(app["id"])
        for h in self.store.all():
            if h["candidate_id"] in ids:
                if h["status"] in HIRED:
                    raise DomainError(
                        "HIRE_ACTIVE", "请先核实在途录用或入职资料保留要求，不能直接删除", 409
                    )
                if self.decisions:
                    self.decisions.erase_application(h["application_id"])
                self.store.erase(h["id"])
