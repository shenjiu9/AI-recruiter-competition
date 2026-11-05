from typing import Protocol

from app.kernel.types import DomainError
from app.modules.org.configuration import APPROVER_ROLES, ConfigurationService
from app.modules.org.contracts import ApprovalNode, DepartmentPolicy, UserDTO
from app.modules.org.headcount import HeadcountService
from app.modules.org.salary import SalaryService


class Directory(Protocol):
    def identity(self, user_id): ...
    def user_ids(self, query): ...
    def get_user(self, user_id: str) -> UserDTO | None: ...
    def policy(self, dept_id: str) -> DepartmentPolicy | None: ...
    def expand_scope(self, roots): ...


class OrgFacade(HeadcountService):
    def __init__(self, directory: Directory, headcount, salary, clock, journal, configuration):
        super().__init__(headcount, clock, journal)
        self.directory = directory
        self.salary = SalaryService(salary, clock, journal)
        self.configuration = ConfigurationService(configuration, self, clock, journal)

    def check_approver(self, user_id, dept, node_id):
        user = self.get_user(user_id)
        if dept not in user.departments or not APPROVER_ROLES[node_id].intersection(user.roles):
            raise DomainError(
                "ORG_APPROVER_INVALID", "审批人缺少该部门范围或所需角色，请管理员检查配置", 422
            )
        return user

    def identity(self, user_id):
        return self.directory.identity(user_id)

    def lock_configuration(self):
        self.configuration.store.lock()

    def transfer_candidates(self, dept, node_id, query):
        users = []
        for user_id in self.directory.user_ids(query):
            try:
                users.append(self.check_approver(user_id, dept, node_id))
            except DomainError:
                continue
        return users

    def salary_check(self, series, level, city, quote):
        return self.salary.check(series, level, city, quote)

    def salary_list(self, ctx, page, size):
        return self.salary.list(ctx, page, size)

    def salary_history(self, ctx, band_id):
        return self.salary.history(ctx, band_id)

    def save_salary(self, ctx, command):
        return self.salary.save(ctx, command)

    def get_user(self, user_id: str) -> UserDTO:
        user = self.directory.get_user(user_id)
        if not user:
            raise DomainError("NOT_FOUND", "在职用户不存在", 404)
        return user

    def policy(self, dept_id: str) -> DepartmentPolicy:
        policy = self.directory.policy(dept_id)
        if not policy:
            raise DomainError("REQ_DEPARTMENT_UNKNOWN", "部门尚未配置组织与编制数据")
        return policy

    def resolve_approval_chain(
        self, kind: str, dept_id: str, facts: dict, snapshot: dict | None = None
    ) -> list[ApprovalNode]:
        policy = DepartmentPolicy(**snapshot) if snapshot else self.policy(dept_id)
        nodes = []
        if facts["proxy"]:
            nodes.append(("manager", "用人经理确认", policy.manager_id))
        # Manager-created requests start at the next level, never self-approve.
        nodes.extend(
            [
                ("director", "部门负责人审批", policy.director_id),
                ("hrbp", "HRBP 审批", policy.hrbp_id),
            ]
        )
        if facts.get("hc_request"):
            nodes.append(("hc", "编制负责人加签", policy.hc_owner_id))
        if facts.get("salary_over"):
            hrd = self.directory.get_user(policy.hrd_id) if policy.hrd_id else None
            if (not hrd or "hrd" not in hrd.roles) and "salary" not in facts.get(
                "retained_nodes", {}
            ):
                raise DomainError(
                    "REQ_HRD_UNAVAILABLE", "薪资超带宽，但部门未配置有效 HRD，请联系管理员"
                )
            nodes.append(("salary", "HRD 薪资加签", policy.hrd_id))
        chain = []
        for key, name, user_id in nodes:
            if key in facts.get("retained_nodes", {}):
                chain.append(ApprovalNode(**facts["retained_nodes"][key]))
                continue
            if key == "salary" and user_id in {
                facts["actor_id"],
                policy.manager_id,
                facts.get("owner_id"),
            }:
                raise DomainError(
                    "REQ_APPROVER_UNAVAILABLE",
                    "HRD 不能审批本人发起或本人归属的招聘需求，请配置其他审批人",
                )
            if user_id == facts["actor_id"] or (
                key != "manager" and user_id == facts.get("owner_id")
            ):
                if key == "salary" or policy.hc_owner_id in {
                    facts["actor_id"],
                    facts.get("owner_id"),
                }:
                    raise DomainError(
                        "REQ_APPROVER_UNAVAILABLE", "审批人与发起人相同，请配置上级审批人"
                    )
                user_id = policy.hc_owner_id
                note = "发起人本人，已上推"
            else:
                note = None
            user = self.check_approver(user_id, dept_id, "hc" if note else key)
            chain.append(ApprovalNode(key, name, user.id, user.name, note))
        return chain
