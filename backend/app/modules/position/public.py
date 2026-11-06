from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from typing import Protocol

from app.kernel.types import Ctx, DomainError, Principal, new_id
from app.modules.position.calendar import WorkCalendar
from app.modules.position.content import PositionContent, normalize

READ_ROLES = {"recruiter", "recruiting_lead", "hrbp", "hiring_manager", "hrd", "headcount_owner"}
HR_ROLES = {"recruiter", "recruiting_lead", "hrbp"}


class Requisitions(Protocol):
    def get(self, ctx, req_id): ...
    def approved_snapshot(self, req_id, version): ...
    def set_position_readers(self, req_id, user_ids): ...


class PositionFacade(PositionContent):
    def __init__(self, store, requisitions: Requisitions, org, clock, journal, calendar=None):
        self.calendar = calendar or WorkCalendar()
        self.store, self.requisitions, self.org, self.clock, self.journal = (
            store,
            requisitions,
            org,
            clock,
            journal,
        )

    def _visible(self, ctx, pos):
        p = ctx.principal
        return bool(READ_ROLES.intersection(p.roles)) and (
            (
                p.user_id in pos["access"]
                or (
                    pos["dept"] in p.departments
                    and bool(HR_ROLES.intersection(p.roles))
                    and (p.user_id == pos["owner_id"] or p.user_id in pos.get("shared_ids", []))
                )
            )
            or (
                not pos["confidential"]
                and pos["dept"] in p.departments
                and bool({"recruiting_lead", "hrbp", "hiring_manager"}.intersection(p.roles))
            )
        )

    def _get(self, ctx, pos_id):
        pos = self.store.get(pos_id)
        if not pos or not self._visible(ctx, pos):
            raise DomainError("NOT_FOUND", "岗位不存在或不在可见范围内", 404)
        return normalize(pos)

    def _editor(self, ctx, pos):
        p = ctx.principal
        return (
            pos["dept"] in p.departments
            and bool(HR_ROLES.intersection(p.roles))
            and (
                p.user_id == pos["owner_id"]
                or p.user_id in pos.get("shared_ids", [])
                or "recruiting_lead" in p.roles
            )
        )

    def _manager(self, ctx, pos):
        return (
            ctx.principal.user_id == pos["manager_id"]
            and "hiring_manager" in ctx.principal.roles
            and pos["dept"] in ctx.principal.departments
        )

    def _name(self, uid):
        identity = self.org.identity(uid) if uid else None
        return identity["name"] if identity else (uid or "待指定")

    def dto(self, ctx, pos):
        normalize(pos)
        return {
            "id": pos["id"],
            "version": pos["version"],
            "name": pos["fields"]["title"],
            "dept": pos["dept"],
            "city": pos["fields"]["city"],
            "level": pos["fields"]["level"],
            "status": pos["status"],
            "ownerHr": self._name(pos["owner_id"]),
            "ownerId": pos["owner_id"],
            "hiringManager": self._name(pos["manager_id"]),
            "managerId": pos["manager_id"],
            "planned": sum(s["count"] for s in pos["sources"]),
            "hired": 0,
            "expectedOnboard": pos["fields"]["expectedOnboard"],
            "confidential": pos["confidential"],
            "requisitionIds": [s["id"] for s in pos["sources"]],
            "profile": pos["profile"],
            "activeProfile": pos["active_profile"],
            "profiles": pos["profiles"],
            "jd": pos["jd"],
            "jdVersions": pos["jd_versions"],
            "activeJd": pos["active_jd"],
            "jdApprovalRequired": pos["jd_approval_required"],
            "knowledge": pos["knowledge"],
            "sharedIds": pos["shared_ids"],
            "sharedMembers": [{"id": uid, "name": self._name(uid)} for uid in pos["shared_ids"]],
            "comments": [{**c, "authorName": self._name(c["author"])} for c in pos["comments"]],
            "closeRequest": pos["close_request"],
            "interviewPlans": pos["interview_plans"],
            "canLead": self._lead(ctx, pos),
            "canCollaborate": self._editor(ctx, pos) or self._manager(ctx, pos),
            "canShare": self._lead(ctx, pos) or ctx.principal.user_id == pos["owner_id"],
            "canApproveJd": self._lead(ctx, pos) and ctx.principal.user_id != pos["jd"]["author"],
            "history": [
                {
                    **h,
                    "actorName": "系统"
                    if h["actor"].startswith("system:")
                    else self._name(h["actor"]),
                }
                for h in pos["history"]
            ],
            "canEdit": self._editor(ctx, pos),
            "canConfirm": self._manager(ctx, pos),
            "canClose": self._editor(ctx, pos) and "recruiting_lead" in ctx.principal.roles,
            "canAssign": self._editor(ctx, pos) or self._manager(ctx, pos),
        }

    def get(self, ctx, pos_id):
        return self.dto(ctx, self._get(ctx, pos_id))

    def search(
        self, ctx, page, size, status=None, view="all", query="", dept="", owner="", city=""
    ):
        rows = [
            p
            for p in self.store.all()
            if self._visible(ctx, p)
            and (not status or p["status"] == status)
            and (view != "mine" or p["owner_id"] == ctx.principal.user_id)
            and (
                view != "participating"
                or ctx.principal.user_id in p.get("shared_ids", [])
                or p["manager_id"] == ctx.principal.user_id
            )
            and (not query or query.casefold() in p["fields"]["title"].casefold())
            and (not dept or p["dept"] == dept)
            and (not owner or p["owner_id"] == owner)
            and (not city or p["fields"]["city"] == city)
        ]
        return {
            "items": [self.dto(ctx, p) for p in rows[(page - 1) * size : page * size]],
            "total": len(rows),
            "page": page,
            "size": size,
        }

    def _signature(self, fields):
        return sha256(
            "\0".join(fields[k] for k in ("dept", "title", "level", "city")).encode()
        ).hexdigest()

    def _candidates(self, source):
        return [
            p
            for p in self.store.all()
            if p["signature"] == self._signature(source["fields"])
            and p["status"] in {"to_publish", "open"}
            and p["confidential"] == (source["fields"].get("confidential") == "1")
            and p["manager_id"] == source["managerId"]
            and set(p["access"]) == set(self._access(source))
        ]

    def _access(self, source):
        return sorted(
            {
                source["creatorId"],
                source["managerId"],
                source["ownerId"],
                *(n["approver_id"] for n in source["chain"]),
                *(u.strip() for u in source["fields"].get("visibleTo", "").split(",") if u.strip()),
            }
        )

    def on_requisition_approved(self, event):
        source = self.requisitions.approved_snapshot(
            event.payload["requisition_id"], event.payload["version"]
        )
        if self.store.generation(source["id"]):
            return
        if source["fields"].get("reqType") != "新增":
            raise DomainError("POSITION_SOURCE_UNSUPPORTED", "本批仅消费新增需求")
        task = {
            "id": source["id"],
            "version": 1,
            "source": source,
            "position_id": None,
            "at": self.clock.now().isoformat(),
        }
        task["due_at"] = self.calendar.deadline(task["at"]).isoformat()
        self.store.save_generation(task)
        if not self._candidates(source):
            ctx = Ctx(Principal("system:position", "岗位事件处理", (), ()), event.trace_id)
            self._generate(ctx, task, None)

    def generation(self, ctx, req_id):
        self.requisitions.get(ctx, req_id)
        task = self.store.generation(req_id)
        if not task:
            return {
                "status": "pending",
                "version": 0,
                "position": None,
                "candidates": [],
                "canResolve": False,
            }
        pos_id = task["position_id"]
        if pos_id:
            pos = self._get(ctx, pos_id)
            return {
                "status": "generated",
                "version": task["version"],
                "position": {"id": pos_id, "name": pos["fields"]["title"], "status": pos["status"]},
                "candidates": [],
                "canResolve": False,
            }
        source = task["source"]
        p = ctx.principal
        allowed = (
            source["dept"] in p.departments
            and bool(HR_ROLES.intersection(p.roles))
            and (p.user_id == source["ownerId"] or "recruiting_lead" in p.roles)
        )
        return {
            "status": "decision",
            "version": task["version"],
            "position": None,
            "canResolve": allowed,
            "dueAt": task.get("due_at", self.calendar.deadline(task["at"]).isoformat()),
            "candidates": [
                {"id": pos["id"], "name": pos["fields"]["title"]}
                for pos in self._candidates(source)
                if self._visible(ctx, pos)
            ],
        }

    def resolve_generation(self, ctx, req_id, command):
        self._lock_actor(ctx)
        result = self.generation(ctx, req_id)
        if result["version"] != command.expected_version:
            raise DomainError("VERSION_CONFLICT", "生成任务已更新，请刷新后核对", 409)
        if not result["canResolve"]:
            raise DomainError("FORBIDDEN", "仅负责 HR 或招聘负责人可以处理岗位生成", 403)
        task = self.store.generation(req_id)
        if task["version"] != command.expected_version:
            raise DomainError("VERSION_CONFLICT", "生成任务已更新", 409)
        if command.target_id and command.target_id not in {p["id"] for p in result["candidates"]}:
            raise DomainError("POSITION_MERGE_INVALID", "目标岗位不可合并，请刷新后核对")
        self._generate(ctx, task, command.target_id)
        return self.generation(ctx, req_id)

    def expire_generations(self):
        self.org.lock_configuration()
        count = 0
        for task in self.store.pending_generations():
            due = (
                datetime.fromisoformat(task["due_at"])
                if task.get("due_at")
                else self.calendar.deadline(task["at"])
            )
            if due > self.clock.now():
                continue
            ctx = Ctx(Principal("system:position-timeout", "岗位生成超时", (), ()), new_id("TRACE"))
            self._generate(ctx, task, None)
            count += 1
        return count

    def _generate(self, ctx, task, target_id):
        source = task["source"]
        if target_id:
            pos = self.store.get(target_id)
            old = pos["version"]
            pos["version"] += 1
        else:
            owner = self.org.identity(source["ownerId"])
            candidate = self.org.get_user(source["ownerId"]) if owner and owner["active"] else None
            owner_id = (
                candidate.id
                if candidate
                and HR_ROLES.intersection(candidate.roles)
                and source["dept"] in candidate.departments
                else None
            )
            fields = source["fields"]
            pos = {
                "id": new_id("POS"),
                "version": 1,
                "dept": source["dept"],
                "status": "to_publish",
                "signature": self._signature(fields),
                "confidential": fields.get("confidential") == "1",
                "fields": fields,
                "owner_id": owner_id,
                "manager_id": source["managerId"],
                "access": self._access(source),
                "sources": [],
                "history": [],
                "profile": {
                    "version": 1,
                    "must": fields["requirements"],
                    "plus": "",
                    "redflag": "",
                    "jd": fields["duties"],
                    "confirmedBy": None,
                    "source": "requisition",
                },
            }
            old = None
        pos["sources"].append(
            {
                "id": source["id"],
                "count": int(source["fields"]["headcount"]),
                "employmentType": source["fields"]["employmentType"],
            }
        )
        pos["history"].append(
            {
                "action": "merged" if target_id else "created",
                "actor": ctx.principal.user_id,
                "at": self.clock.now().isoformat(),
                "requisition_id": source["id"],
            }
        )
        self.store.save(pos, old)
        self._sync_source_readers(pos)
        previous = task["version"]
        task.update(position_id=pos["id"], version=previous + 1)
        self.store.save_generation(task, previous)
        self.journal.record(
            ctx,
            "position.merged" if target_id else "position.created",
            pos["id"],
            pos["version"],
            None,
            {"status": pos["status"], "version": pos["version"]},
        )

    def command(self, ctx, pos_id, command):
        self._lock_actor(ctx)
        pos = self._get(ctx, pos_id)
        if pos["version"] != command.expected_version:
            raise DomainError("VERSION_CONFLICT", "岗位已修改，请刷新后核对", 409)
        action = command.action
        editor, manager = self._editor(ctx, pos), self._manager(ctx, pos)
        allowed = (
            manager
            if action == "confirm_profile"
            else (editor or manager if action == "assign" else editor)
        )
        extended = action not in {
            "assign",
            "save_profile",
            "confirm_profile",
            "publish",
            "pause",
            "resume",
            "close",
        }
        if not extended and not allowed:
            raise DomainError("FORBIDDEN", "当前角色不能执行此岗位操作", 403)
        if pos["status"] == "closed":
            raise DomainError("INVALID_TRANSITION", "已关闭岗位只读", 409)
        before = {"version": pos["version"], "status": pos["status"]}
        if extended:
            self.content_action(ctx, pos, command)
        elif action == "assign":
            if (
                not self._lead(ctx, pos)
                and not manager
                and ctx.principal.user_id != pos["owner_id"]
            ):
                raise DomainError("FORBIDDEN", "仅负责人、用人经理或招聘负责人可转交岗位", 403)
            user = self.org.get_user(command.owner_id)
            if not HR_ROLES.intersection(user.roles) or pos["dept"] not in user.departments:
                raise DomainError("POSITION_OWNER_INVALID", "负责 HR 须在职且具备本部门招聘权限")
            pos["owner_id"] = user.id
            pos["shared_ids"] = [uid for uid in pos["shared_ids"] if uid != user.id]
        elif action == "save_profile":
            self._save_profile(ctx, pos, command)
        elif action == "confirm_profile":
            self._confirm_profile(ctx, pos)
        else:
            transitions = {
                "publish": ("to_publish", "open"),
                "pause": ("open", "paused"),
                "resume": ("paused", "open"),
            }
            if action == "close":
                if "recruiting_lead" not in ctx.principal.roles:
                    raise DomainError("FORBIDDEN", "普通 HR 请提交关闭申请，由用人经理确认", 403)
                self._close(ctx, pos, command.reason)
            else:
                previous, next_status = transitions[action]
                if pos["status"] != previous:
                    raise DomainError("INVALID_TRANSITION", "岗位状态不支持该操作", 409)
                if action == "publish":
                    self._jd_ready(pos)
                    if not pos["profile"]["confirmedBy"] or not pos["owner_id"]:
                        raise DomainError(
                            "POSITION_NOT_READY", "请先指定负责 HR 并由用人经理确认画像"
                        )
                    self.org.check_approver(pos["manager_id"], pos["dept"], "manager")
                    owner = self.org.get_user(pos["owner_id"])
                    if (
                        not HR_ROLES.intersection(owner.roles)
                        or pos["dept"] not in owner.departments
                    ):
                        raise DomainError(
                            "POSITION_OWNER_INVALID", "负责 HR 已失去部门范围或招聘角色"
                        )
                    text = " ".join(
                        pos["profile"].get(k, "") for k in ("must", "plus", "redflag", "jd")
                    )
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
                    pos["active_jd"] = deepcopy(pos["jd"])
                if action == "pause" and not command.reason.strip():
                    raise DomainError("POSITION_REASON_REQUIRED", "暂停原因不能为空")
                pos["status"] = next_status
        pos["version"] += 1
        pos["history"].append(
            {
                "action": action,
                "actor": ctx.principal.user_id,
                "at": self.clock.now().isoformat(),
                "reason": command.reason.strip(),
                "handling": command.handling if action == "pause" else None,
                "profile": dict(pos["profile"])
                if action in {"save_profile", "confirm_profile"}
                else None,
                "owner_id": pos["owner_id"] if action == "assign" else None,
                "shared_ids": pos["shared_ids"] if action == "share" else None,
                "jd_approval_required": pos["jd_approval_required"]
                if action == "configure_publish"
                else None,
                "close_reason": pos.get("closed_reason")
                if action in {"close", "confirm_close"}
                else None,
            }
        )
        self.store.save(pos, before["version"])
        if action in {"assign", "share"}:
            self._sync_source_readers(pos)
        event = {
            "publish": "published",
            "pause": "paused",
            "resume": "resumed",
            "close": "closed",
            "confirm_close": "closed",
            "confirm_profile": "profile_confirmed",
            "amend_confirm_profile": "profile_confirmed",
        }.get(action, action)
        self.journal.record(
            ctx,
            "position." + event,
            pos_id,
            pos["version"],
            before,
            {"status": pos["status"], "version": pos["version"]},
        )
        if action in {"save_kb", "retire_kb"}:
            self.journal.record(
                ctx, "kb.changed", pos_id, pos["version"], None, {"version": pos["version"]}
            )
        return self.dto(ctx, pos)

    def _sync_source_readers(self, pos):
        members = {*pos.get("shared_ids", [])}
        if pos["owner_id"]:
            members.add(pos["owner_id"])
        for source in pos["sources"]:
            self.requisitions.set_position_readers(source["id"], members)

    def authorize_write(self, ctx, pos_id):
        self._lock_actor(ctx)
        self._get(ctx, pos_id)

    def sync_source_access(self):
        self.org.lock_configuration()
        positions = self.store.all()
        for pos in positions:
            self._sync_source_readers(pos)
        return len(positions)

    def _lock_actor(self, ctx):
        self.org.lock_configuration()
        user = self.org.get_user(ctx.principal.user_id)
        if user.permission_version != ctx.principal.permission_version:
            raise DomainError("PERMISSION_CHANGED", "权限已更新，请刷新后重试", 409)
