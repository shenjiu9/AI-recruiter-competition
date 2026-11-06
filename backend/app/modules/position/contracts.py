from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PositionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    action: Literal[
        "assign",
        "save_profile",
        "confirm_profile",
        "publish",
        "pause",
        "resume",
        "close",
        "save_jd",
        "approve_jd",
        "reject_jd",
        "apply_jd",
        "configure_publish",
        "save_kb",
        "retire_kb",
        "share",
        "comment",
        "request_close",
        "confirm_close",
        "reject_close",
        "save_interview_plan",
        "amend_confirm_profile",
    ]
    reason: str = Field(default="", max_length=500)
    handling: Literal["continue", "freeze"] = "continue"
    owner_id: str = Field(default="", max_length=64)
    must: str = Field(default="", max_length=2000)
    plus: str = Field(default="", max_length=2000)
    redflag: str = Field(default="", max_length=2000)
    jd: str = Field(default="", max_length=4000)
    must_ask: str = Field(default="", max_length=2000)
    plus_weights: list[Literal["high", "medium", "low"]] = Field(
        default_factory=list, max_length=40
    )
    jd_approval_required: bool = False
    entry_id: str | None = Field(default=None, max_length=64)
    content: str = Field(default="", max_length=4000)
    source: str = Field(default="", max_length=300)
    disclosure: Literal["proactive", "asked", "internal", "handoff"] = "internal"
    shared_ids: list[str] = Field(default_factory=list, max_length=5)
    mentions: list[str] = Field(default_factory=list, max_length=10)
    rounds: list["InterviewRound"] = Field(default_factory=list, max_length=6)


class InterviewRound(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    format: Literal["video", "onsite", "phone", "ai"]
    duration: Literal[15, 30, 45, 60, 90]
    interviewers: list[str] = Field(default_factory=list, max_length=10)
    rule: Literal["unanimous", "majority", "designated"] = "unanimous"
    decision_by: str | None = Field(default=None, max_length=64)
    criteria: str = Field(min_length=1, max_length=2000)


class GenerationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    target_id: str | None = Field(default=None, max_length=64)
