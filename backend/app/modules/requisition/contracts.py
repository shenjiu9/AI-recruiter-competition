from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApprovalNodeDTO(BaseModel):
    id: str
    name: str
    approver_id: str
    approver: str
    note: str | None = None


class RequisitionDTO(BaseModel):
    id: str
    no: str
    version: int
    title: str
    dept: str
    type: Literal["new", "replace", "additional"]
    headcount: int
    initiator: str
    mode: Literal["self", "proxy", "ai_draft"]
    proxyBy: str | None = None
    status: Literal["draft", "in_approval", "approved", "rejected", "withdrawn"]
    waitingFor: str | None = None
    waitingDays: int = 0
    submittedAt: str | None = None


class RequisitionDetail(RequisitionDTO):
    fields: dict[str, str]
    chain: list[ApprovalNodeDTO]
    history: list[dict]
    currentNode: int
    creatorId: str
    managerId: str


class RequisitionPage(BaseModel):
    items: list[RequisitionDTO]
    total: int
    page: int
    size: int


class PrecheckItem(BaseModel):
    key: str
    label: str
    status: Literal["pass", "warn", "block"]
    detail: str


class VersionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class DraftPatch(VersionCommand):
    fields: dict[str, str]


class SubmitCommand(VersionCommand):
    fields: dict[str, str] | None = None


class ApprovalCommand(VersionCommand):
    node_id: str
    comment: str | None = Field(default=None, max_length=1000)


class RejectionCommand(VersionCommand):
    node_id: str
    reason: str = Field(min_length=1, max_length=1000)


class RequisitionApproved(BaseModel):
    schema_version: int = 1
    requisition_id: str
    version: int
