from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.position.contracts import InterviewRound


class HireCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["prepare", "decide", "approve", "reject", "withdraw", "handover", "result"]
    expected_version: int = Field(ge=1)
    decision: Literal["", "hire", "reject", "extra_round"] = ""
    reason: str = Field(default="", max_length=2000)
    verified: bool = False
    review_stamp: str = Field(default="", max_length=64)
    salary_k: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    salary_months: int = Field(default=12, ge=1, le=24)
    evidence: str = Field(default="", max_length=2000)
    offer_owner: str = Field(default="", max_length=64)
    expected_start: date | None = None
    extra_round: InterviewRound | None = None
    result: Literal["", "accepted", "declined", "joined", "no_show"] = ""


class CardCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    option: Literal["dismiss", "reject", "terminate", "keep"]
    reason: str = Field(min_length=1, max_length=2000)
