from hashlib import sha256
from typing import Protocol

from app.kernel.types import Ctx, DomainError, Principal, new_id

READ_ROLES = {"recruiter", "recruiting_lead", "hrbp", "hiring_manager", "hrd", "headcount_owner"}
HR_ROLES = {"recruiter", "recruiting_lead", "hrbp"}


class Requisitions(Protocol):
    def get(self, ctx, req_id): ...
    def approved_snapshot(self, req_id, version): ...


class PositionFacade:
    def __init__(self, store, requisitions: Requisitions, org, clock, journal):
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
            (p.user_id in pos["access"] or p.user_id == pos["owner_id"])
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
        return pos

    def _editor(self, ctx, pos):
        p = ctx.principal
        return (
            pos["dept"] in p.departments
            and bool(HR_ROLES.intersection(p.roles))
            and (p.user_id == pos["owner_id"] or "recruiting_lead" in p.roles)
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

    def search(self, ctx, page, size, status=None):
        rows = [
            p
            for p in self.store.all()
            if self._visible(ctx, p) and (not status or p["status"] == status)
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
        if not allowed:
            raise DomainError("FORBIDDEN", "当前角色不能执行此岗位操作", 403)
        if pos["status"] == "closed":
            raise DomainError("INVALID_TRANSITION", "已关闭岗位只读", 409)
        before = {"version": pos["version"], "status": pos["status"]}
        if action == "assign":
            user = self.org.get_user(command.owner_id)
            if not HR_ROLES.intersection(user.roles) or pos["dept"] not in user.departments:
                raise DomainError("POSITION_OWNER_INVALID", "负责 HR 须在职且具备本部门招聘权限")
            pos["owner_id"] = user.id
        elif action == "save_profile":
            if pos["status"] != "to_publish":
                raise DomainError("INVALID_TRANSITION", "本批仅支持发布前编辑画像", 409)
            if not command.must.strip() or not command.jd.strip():
                raise DomainError("PROFILE_REQUIRED", "必备条件与 JD 职责不能为空")
            pos["profile"] = {
                "version": pos["profile"]["version"] + 1,
                "must": command.must.strip(),
                "plus": command.plus.strip(),
                "redflag": command.redflag.strip(),
                "jd": command.jd.strip(),
                "confirmedBy": None,
                "source": "manual",
            }
        elif action == "confirm_profile":
            if pos["status"] != "to_publish" or pos["profile"]["confirmedBy"]:
                raise DomainError("INVALID_TRANSITION", "当前画像不能重复确认", 409)
            pos["profile"]["confirmedBy"] = ctx.principal.user_id
        else:
            transitions = {
                "publish": ("to_publish", "open"),
                "pause": ("open", "paused"),
                "resume": ("paused", "open"),
            }
            if action == "close":
                if "recruiting_lead" not in ctx.principal.roles:
                    raise DomainError(
                        "FORBIDDEN", "本批关闭由招聘负责人执行；HR 申请经理确认后续接入", 403
                    )
                if pos["status"] not in {"open", "paused"} or command.reason not in {
                    "招满",
                    "需求取消",
                    "组织调整",
                    "其他",
                }:
                    raise DomainError(
                        "POSITION_CLOSE_INVALID", "只能关闭招聘中或已暂停岗位，且须选择关闭原因"
                    )
                for source in sorted(pos["sources"], key=lambda s: s["id"]):
                    self.org.release_headcount(ctx, source["id"])
                pos["status"] = "closed"
            else:
                previous, next_status = transitions[action]
                if pos["status"] != previous:
                    raise DomainError("INVALID_TRANSITION", "岗位状态不支持该操作", 409)
                if action == "publish":
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
            }
        )
        self.store.save(pos, before["version"])
        event = {
            "publish": "published",
            "pause": "paused",
            "resume": "resumed",
            "close": "closed",
            "confirm_profile": "profile_confirmed",
        }.get(action, action)
        self.journal.record(
            ctx,
            "position." + event,
            pos_id,
            pos["version"],
            before,
            {"status": pos["status"], "version": pos["version"]},
        )
        return self.dto(ctx, pos)

    def _lock_actor(self, ctx):
        self.org.lock_configuration()
        user = self.org.get_user(ctx.principal.user_id)
        if user.permission_version != ctx.principal.permission_version:
            raise DomainError("PERMISSION_CHANGED", "权限已更新，请刷新后重试", 409)
