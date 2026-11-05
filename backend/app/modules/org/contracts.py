from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HeadcountCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: int = Field(ge=2020, le=2100)
    expected_version: int = Field(ge=0)
    planned: int = Field(ge=0, le=1000000)
    used: int = Field(ge=0, le=1000000)
    frozen: bool = False
    effective_from: date

    @model_validator(mode="after")
    def validate_capacity(self):
        if self.used > self.planned or self.effective_from.year != self.year:
            raise ValueError("已用不得超过计划；生效日期须在所选年度内")
        return self


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
