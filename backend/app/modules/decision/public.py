from app.kernel.types import Ctx, DomainError, Principal
from app.modules.hiring.public import fingerprint

SYSTEM = Ctx(Principal("system:decision", "决策待办", (), ()), "decision-worker")


class DecisionFacade:
    def __init__(
        self, store, hiring, applications, interviews, positions, candidates, org, clock, journal
    ):
        self.store, self.hiring, self.applications, self.interviews = (
            store,
            hiring,
            applications,
            interviews,
        )
        self.positions, self.candidates, self.org, self.clock, self.journal = (
            positions,
            candidates,
            org,
            clock,
            journal,
        )

    def specs(self):
        specs = []
        apps = self.applications.hiring_applications()
        for h in self.hiring.records():
            pos = self.positions.hiring_context(h["position_id"])
            if (
                h["status"] in {"deciding", "pending"}
                and pos["status"] != "closed"
                and not pos["frozen"]
            ):
                specs.append(
                    {
                        "kind": "hire_review" if h["status"] == "deciding" else "hire_approval",
                        "object_id": h["id"],
                        "application_id": h["application_id"],
                        "position_id": pos["id"],
                        "stamp": fingerprint([h["version"], pos["version"]]),
                        "title": "请查看面评汇总后决定录用"
                        if h["status"] == "deciding"
                        else "录用审批待处理",
                        "due_at": h["due_at"],
                        "href": "/hiring/" + h["id"],
                        "options": ["dismiss"],
                    }
                )
            if h["status"] in {"accepted", "joined"}:
                family = self.candidates.family(h["candidate_id"])
                for app in apps:
                    if (
                        app["candidate_id"] in family
                        and app["id"] != h["application_id"]
                        and not app["outcome"]
                        and app["stage"] != "hired"
                    ):
                        p = self.positions.hiring_context(app["position_id"])
                        if p["status"] == "closed" or p["frozen"]:
                            continue
                        specs.append(
                            {
                                "kind": "other_application",
                                "object_id": app["id"],
                                "application_id": app["id"],
                                "position_id": app["position_id"],
                                "stamp": fingerprint([h["id"], app["version"], p["version"]]),
                                "title": "候选人已接受其他录用，是否终止本次应聘",
                                "due_at": h["due_at"],
                                "href": "/candidates/" + app["candidate_id"],
                                "options": ["terminate", "keep"],
                            }
                        )
        for app in apps:
            if app["stage"] != "interview" or app["outcome"]:
                continue
            pos = self.positions.hiring_context(app["position_id"])
            if pos["status"] == "closed" or pos["frozen"]:
                continue
            rounds = self.interviews.pending_rejection(app["id"])
            if rounds and rounds[-1]["result"] == "needs_hr_decision":
                iv = rounds[-1]
                specs.append(
                    {
                        "kind": "interview_reject",
                        "object_id": iv["id"],
                        "application_id": app["id"],
                        "position_id": app["position_id"],
                        "stamp": fingerprint([app["version"], pos["version"], iv["version"]]),
                        "title": "面评未通过，请 HR 决定是否淘汰",
                        "due_at": self.hiring.calendar.deadline(app["started_at"], 2).isoformat(),
                        "href": "/interviews/" + iv["id"],
                        "options": ["reject", "keep"],
                    }
                )
        for pos in self.positions.hiring_positions():
            if pos["status"] == "open" and pos["hired"] >= pos["planned"]:
                specs.append(
                    {
                        "kind": "position_full",
                        "object_id": pos["id"],
                        "application_id": None,
                        "position_id": pos["id"],
                        "stamp": fingerprint([pos["version"], pos["hired"]]),
                        "title": "岗位已招满，建议核对后关闭",
                        "due_at": None,
                        "href": "/positions/" + pos["id"],
                        "options": ["dismiss"],
                    }
                )
        return specs

    def sync(self):
        self.org.lock_configuration()
        self.hiring.sync()
        specs = self.specs()
        current = {}
        for spec in specs:
            key = "CARD-" + fingerprint([spec["kind"], spec["object_id"], spec["stamp"]])[:48]
            current[key] = spec
            if not self.store.get(key):
                self.store.save(
                    {
                        **spec,
                        "id": key,
                        "version": 1,
                        "state": "open",
                        "origin": "rule",
                        "confidence": None,
                        "created_at": self.clock.now().isoformat(),
                        "resolution": None,
                    }
                )
                self.journal.record(
                    SYSTEM, "decision_card.created", key, 1, None, {"kind": spec["kind"]}
                )
        for card in self.store.all():
            if card["state"] == "open" and card["id"] not in current:
                self.finish(SYSTEM, card, "invalidated", "对象情况已变化")

    def finish(self, ctx, card, state, reason):
        old = card["version"]
        card.update(
            version=old + 1,
            state=state,
            resolution={
                "actor": ctx.principal.user_id,
                "reason": reason,
                "at": self.clock.now().isoformat(),
            },
        )
        self.store.save(card, old)
        self.journal.record(
            ctx, "decision_card." + state, card["id"], card["version"], None, {"state": state}
        )

    def authorize(self, ctx, key):
        self.candidates.lock(ctx)
        card = self.store.get(key)
        if not card:
            raise DomainError("NOT_FOUND", "卡片不存在", 404)
        if card["kind"].startswith("hire_"):
            self.hiring.authorize(ctx, card["object_id"])
        else:
            pos = self.positions.get(ctx, card["position_id"])
            if not self.candidates.hr(ctx) or not pos["canEdit"]:
                raise DomainError("NOT_FOUND", "卡片不在可见范围", 404)
        return card

    def listing(self, ctx, state="open"):
        rows = []
        for card in self.store.all():
            if state and card["state"] != state:
                continue
            try:
                self.authorize(ctx, card["id"])
                rows.append(
                    {
                        **card,
                        "overdue": bool(
                            card["due_at"] and self.clock.now().isoformat() > card["due_at"]
                        ),
                    }
                )
            except DomainError:
                continue
        return sorted(rows, key=lambda c: (c["due_at"] or "9999", c["id"]))

    def resolve(self, ctx, key, command):
        card = self.authorize(ctx, key)
        if card["state"] != "open" or card["version"] != command.expected_version:
            raise DomainError("CARD_STALE", "情况已变化或卡片已处理，请刷新", 409)
        if command.option not in card["options"]:
            raise DomainError("OPTION_INVALID", "请打开详情处理该事项；不能从卡片直接决定录用")
        if card["kind"].startswith("hire_"):
            h, pos = self.hiring.authorize(ctx, card["object_id"])
            manager, _, approver = self.hiring.permissions(ctx, h, pos)
            current = next((n for n in h["chain"] if n["status"] == "pending"), None)
            if not (
                manager
                if card["kind"] == "hire_review"
                else approver and current and current["user_id"] == ctx.principal.user_id
            ):
                raise DomainError("FORBIDDEN", "只有本次决定人或当前审批人可处理卡片", 403)
        if command.option in {"reject", "terminate"}:
            self.applications.hiring_transition(
                ctx,
                card["application_id"],
                "reject" if command.option == "reject" else "withdraw",
                command.reason,
            )
        self.finish(ctx, card, "resolved", command.reason)
        return {"id": key}

    def erase_application(self, aid):
        for card in self.store.all():
            if card["application_id"] == aid:
                self.store.erase(card["id"])
