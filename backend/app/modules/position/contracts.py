from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PositionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    action: Literal[
        "assign", "save_profile", "confirm_profile", "publish", "pause", "resume", "close"
    ]
    reason: str = Field(default="", max_length=500)
    handling: Literal["continue", "freeze"] = "continue"
    owner_id: str = Field(default="", max_length=64)
    must: str = Field(default="", max_length=2000)
    plus: str = Field(default="", max_length=2000)
    redflag: str = Field(default="", max_length=2000)
    jd: str = Field(default="", max_length=4000)


class GenerationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    target_id: str | None = Field(default=None, max_length=64)
