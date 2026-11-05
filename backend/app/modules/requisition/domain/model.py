from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Requisition:
    id: str
    version: int
    creator_id: str
    manager_id: str
    dept: str
    status: str
    fields: dict[str, str]
    created_at: datetime
    mode: str = "proxy"
    chain: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    current_node: int = 0
    submitted_at: datetime | None = None
    hc_approver: dict | None = None
    approval_policy: dict | None = None
    salary_review: dict | None = None
    submitted_fields: dict | None = None
