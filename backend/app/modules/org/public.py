from typing import Protocol

from app.kernel.types import DomainError
from app.modules.org.contracts import ApprovalNode, DepartmentPolicy, UserDTO
from app.modules.org.headcount import HeadcountService


class Directory(Protocol):
    def get_user(self, user_id: str) -> UserDTO | None: ...
    def policy(self, dept_id: str) -> DepartmentPolicy | None: ...


class OrgFacade(HeadcountService):
    def __init__(self, directory: Directory, headcount, clock, journal):
        super().__init__(headcount, clock, journal)
        self.directory = directory

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

    def resolve_approval_chain(self, kind: str, dept_id: str, facts: dict) -> list[ApprovalNode]:
        policy = self.policy(dept_id)
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
        if facts.get("hc_request") or facts.get("salary_over"):
            nodes.append(("hc", "编制/薪酬加签", policy.hc_owner_id))
        chain = []
        for key, name, user_id in nodes:
            if user_id == facts["actor_id"]:
                if user_id == policy.hc_owner_id:
                    raise DomainError(
                        "REQ_APPROVER_UNAVAILABLE", "审批人与发起人相同，请配置上级审批人"
                    )
                user_id = policy.hc_owner_id
                note = "发起人本人，已上推"
            else:
                note = None
            user = self.get_user(user_id)
            chain.append(ApprovalNode(key, name, user.id, user.name, note))
        return chain
