from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SalaryBandCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    series: str = Field(min_length=1, max_length=80)
    grade: str = Field(min_length=1, max_length=40, pattern=r"^[^\s–~至,-]+$")
    city: str = Field(min_length=1, max_length=80)
    lower: float = Field(gt=0, le=1000, allow_inf_nan=False)
    upper: float = Field(gt=0, le=1000, allow_inf_nan=False)
    months: int = Field(ge=1, le=24)
    effective_from: date
    expected_version: int = Field(ge=0)

    @field_validator("grade", mode="before")
    @classmethod
    def normalize_grade(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_band(self):
        if self.lower > self.upper:
            raise ValueError("薪资上限不能小于下限")
        return self


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
    hrd_id: str | None = None


@dataclass(frozen=True)
class ApprovalNode:
    id: str
    name: str
    approver_id: str
    approver: str
    note: str | None = None
