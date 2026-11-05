from dataclasses import dataclass


@dataclass(frozen=True)
class UserDTO:
    id: str
    name: str
    roles: tuple[str, ...]
    departments: tuple[str, ...]


@dataclass(frozen=True)
class DepartmentPolicy:
    id: str
    available_hc: int
    manager_id: str
    director_id: str
    hrbp_id: str
    hc_owner_id: str
    salary_max: float


@dataclass(frozen=True)
class ApprovalNode:
    id: str
    name: str
    approver_id: str
    approver: str
    note: str | None = None
