from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal[
        "configure",
        "offer",
        "book",
        "reschedule",
        "request_reschedule",
        "cancel",
        "complete",
        "no_show",
        "feedback",
        "remark",
        "retry_integration",
    ]
    expected_version: int = Field(ge=1)
    start: AwareDatetime | None = None
    slot_id: str = Field(default="", max_length=64)
    reason: str = Field(default="", max_length=2000)
    location: str = Field(default="", max_length=1000)
    meeting_url: str = Field(default="", max_length=1000)
    recording_consent: bool = False
    scores: dict[str, StrictInt] = Field(default_factory=dict, max_length=30)
    recommendation: Literal["", "strong_yes", "yes", "hold", "no"] = ""
    strengths: str = Field(default="", max_length=4000)
    concerns: str = Field(default="", max_length=4000)
    next_focus: str = Field(default="", max_length=2000)
    answers: dict[str, str] = Field(default_factory=dict, max_length=30)
    verified: bool = False
    recused: bool = False


class Availability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1, max_length=7)
    start_hour: int = Field(default=9, ge=7, le=20)
    end_hour: int = Field(default=18, ge=8, le=21)
    daily_limit: int = Field(default=5, ge=1, le=20)
    weekly_limit: int = Field(default=20, ge=1, le=100)
    buffer_minutes: int = Field(default=10, ge=0, le=60)
