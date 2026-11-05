from dataclasses import asdict
from typing import Protocol

from app.kernel.types import Ctx, DomainError, Principal, new_id

APPROVER_ROLES = {
    "manager": {"hiring_manager"},
    "director": {"hiring_manager", "recruiting_lead"},
    "hrbp": {"hrbp"},
    "hc": {"headcount_owner", "hrbp"},
    "hc_final": {"headcount_owner", "hrbp"},
    "salary": {"hrd"},
}


class ConfigurationStore(Protocol):
    def lock(self): ...
    def users(self): ...
    def user(self, user_id): ...
    def departments(self): ...
    def save(self, kind, object_id, expected, values): ...
    def revision(self, kind, object_id, version, data, actor, at): ...
    def history(self, kind, object_id): ...


class ConfigurationService:
    def __init__(self, store: ConfigurationStore, org, clock, journal):
        self.store, self.org, self.clock, self.journal = store, org, clock, journal

    def authorize(self, ctx, write=False):
        user = self.org.get_user(ctx.principal.user_id)
        allowed = {"admin"} if write else {"admin", "recruiting_lead"}
        if not allowed.intersection(user.roles):
            raise DomainError("FORBIDDEN", "仅系统管理员可维护；招聘负责人可查看授权部门配置", 403)
        return user

    def bootstrap_admin(self, user_id, expected_version):
        # Local deployment command only; deliberately has no HTTP route.
        self.store.lock()
        if any(u["active"] and "admin" in u["roles"] for u in self.store.users()):
            raise DomainError("ORG_ADMIN_EXISTS", "已有在职管理员，请由管理员在系统内授权", 409)
        row = self.store.user(user_id)
        if row is None or not row["active"]:
            raise DomainError("ORG_USER_INACTIVE", "首位管理员须是已导入的在职人员")
        roles = sorted(set(row["roles"]) | {"admin"})
        self.store.save("permissions", user_id, expected_version, {"roles": roles})
        after = {**row, "roles": roles, "version": expected_version + 1}
        ctx = Ctx(Principal(user_id, row["name"], ("admin",), ()), new_id("bootstrap"))
        self._record(ctx, "permissions", user_id, row, after)
        return after

    def departments(self, ctx):
        user = self.authorize(ctx)
        names = {row["id"]: row["name"] for row in self.store.users()}
        return [
            {
                **row,
                "approver_names": {
                    key: names.get(value, value) for key, value in row["policy"].items()
                },
            }
            for row in self.store.departments()
            if "admin" in user.roles or row["id"] in user.departments
        ]

    def department(self, ctx, dept):
        row = next((r for r in self.departments(ctx) if r["id"] == dept), None)
        if row is None:
            raise DomainError("NOT_FOUND", "部门不存在或不在授权范围", 404)
        return row

    def users(self, ctx, page, size, query):
        user = self.authorize(ctx)
        items = []
        for row in self.store.users():
            effective = self.org.directory.expand_scope(
                set(row["departments"]) | set(row["directory_departments"])
            )
            if "admin" not in user.roles and not set(effective).intersection(user.departments):
                continue
            if query and query.casefold() not in (row["id"] + " " + row["name"]).casefold():
                continue
            if "admin" not in user.roles:
                # Read-only leaders never receive unrelated department grants.
                row = {
                    **row,
                    "departments": [d for d in row["departments"] if d in user.departments],
                    "directory_departments": [
                        d for d in row["directory_departments"] if d in user.departments
                    ],
                }
            items.append(row)
        return {
            "items": items[(page - 1) * size : page * size],
            "total": len(items),
            "page": page,
            "size": size,
        }

    def _record(self, ctx, kind, object_id, before, after):
        if not self.store.history(kind, object_id):
            self.store.revision(kind, object_id, before["version"], before, None, self.clock.now())
        self.store.revision(
            kind, object_id, after["version"], after, ctx.principal.user_id, self.clock.now()
        )
        self.journal.record(
            ctx, f"org.{kind}_updated", object_id, after["version"], before, after, False
        )

    def save_permissions(self, ctx, user_id, command):
        self.store.lock()
        self.authorize(ctx, write=True)
        row = self.store.user(user_id)
        if row is None:
            raise DomainError("NOT_FOUND", "通讯录用户不存在", 404)
        if not row["active"]:
            raise DomainError("ORG_USER_INACTIVE", "离职用户不能新增或修改授权，请先处理目录状态")
        dept_ids = {d["id"] for d in self.store.departments()}
        if set(command.departments) - dept_ids:
            raise DomainError("ORG_SCOPE_INVALID", "授权包含未同步的部门")
        if "admin" in row["roles"] and "admin" not in command.roles:
            if not any(
                u["id"] != user_id and u["active"] and "admin" in u["roles"]
                for u in self.store.users()
            ):
                raise DomainError("ORG_LAST_ADMIN", "至少保留一名在职系统管理员", 409)
        values = {
            "roles": sorted(set(command.roles)),
            "departments": sorted(set(command.departments)),
        }
        self.store.save("permissions", user_id, command.expected_version, values)
        after = {**row, **values, "version": command.expected_version + 1}
        self._record(ctx, "permissions", user_id, row, after)
        return after

    def save_policy(self, ctx, dept, command):
        self.store.lock()
        self.authorize(ctx, write=True)
        row = self.department(ctx, dept)
        policy = {**row["policy"], **command.model_dump(exclude={"expected_version"})}
        for key, node in [
            ("manager_id", "manager"),
            ("director_id", "director"),
            ("hrbp_id", "hrbp"),
            ("hc_owner_id", "hc"),
            ("hrd_id", "salary"),
        ]:
            self.org.check_approver(policy[key], dept, node)
        if policy["manager_id"] in {
            policy[k] for k in ("director_id", "hrbp_id", "hc_owner_id", "hrd_id")
        }:
            raise DomainError("ORG_SELF_APPROVAL", "后续审批人必须与归属用人经理独立")
        self.store.save("approval", dept, command.expected_version, {"policy": policy})
        after = {**row, "policy": policy, "version": command.expected_version + 1}
        names = {user["id"]: user["name"] for user in self.store.users()}
        after["approver_names"] = {key: names.get(value, value) for key, value in policy.items()}
        self._record(ctx, "approval", dept, row, after)
        return after

    def history(self, ctx, kind, object_id, page, size):
        if kind == "permissions":
            self.authorize(ctx, write=True)
            if self.store.user(object_id) is None:
                raise DomainError("NOT_FOUND", "用户不存在", 404)
        else:
            self.department(ctx, object_id)
        rows = self.store.history(kind, object_id)
        return {
            "items": rows[(page - 1) * size : page * size],
            "total": len(rows),
            "page": page,
            "size": size,
        }

    def trial(self, ctx, dept, command):
        row = self.department(ctx, dept)
        actor = self.org.get_user(command.actor_id)
        if dept not in actor.departments or not {
            "recruiter",
            "recruiting_lead",
            "hrbp",
            "hiring_manager",
        }.intersection(actor.roles):
            raise DomainError("ORG_ACTOR_INVALID", "试算发起人须具有该部门发起权限")
        if (
            not {"recruiter", "recruiting_lead", "hrbp"}.intersection(actor.roles)
            and actor.id != row["policy"]["manager_id"]
        ):
            raise DomainError("ORG_ACTOR_INVALID", "用人经理只能发起本人负责部门的需求")
        return {
            "version": row["version"],
            "chain": [
                asdict(n)
                for n in self.org.resolve_approval_chain(
                    "requisition",
                    dept,
                    {**command.model_dump(), "proxy": actor.id != row["policy"]["manager_id"]},
                )
            ],
        }
