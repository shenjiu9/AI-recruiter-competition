import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=160)
    city: str = Field(default="", max_length=80)
    company: str = Field(default="", max_length=160)
    title: str = Field(default="", max_length=120)
    school: str = Field(default="", max_length=160)
    degree: str = Field(default="", max_length=40)
    graduation_year: int | None = Field(default=None, ge=1950, le=2100)
    years_exp: float | None = Field(default=None, ge=0, le=70)
    skills: str = Field(default="", max_length=2000)
    experience: str = Field(default="", max_length=10000)
    education: str = Field(default="", max_length=4000)
    certificates: str = Field(default="", max_length=2000)
    expected_city: str = Field(default="", max_length=80)
    expected_salary: str = Field(default="", max_length=100)

    @field_validator("phone")
    @classmethod
    def phone_number(cls, value):
        value = re.sub(r"[\s()\-]", "", value)
        if value.startswith("+86") and len(value) == 14:
            value = value[3:]
        if value and not re.fullmatch(r"\+?\d{7,15}", value):
            raise ValueError("invalid phone")
        return value

    @field_validator("email")
    @classmethod
    def email_address(cls, value):
        value = value.casefold()
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("invalid email")
        return value


class CreateCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Profile
    source: Literal["manual", "referral", "headhunter", "internal"] = "manual"


class CandidateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["edit", "consent", "do_not_contact", "tags", "key", "merge", "unmerge", "erase"]
    expected_version: int = Field(ge=1)
    profile: Profile | None = None
    resume_id: str = Field(default="", max_length=64)
    reason: str = Field(default="", max_length=1000)
    granted: bool = False
    policy_version: str = Field(default="recruitment-v1", min_length=1, max_length=80)
    evidence: str = Field(default="", max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=30)
    key_candidate: bool = False
    target_id: str = Field(default="", max_length=64)
    target_version: int | None = Field(default=None, ge=1)


class AttachCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    candidate_id: str = Field(min_length=1, max_length=64)
    position_id: str = Field(min_length=1, max_length=64)
    source: Literal["hr", "candidate"] = "hr"
    reason: str = Field(default="", max_length=1000)
    evidence: str = Field(default="", max_length=500)


class ApplicationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["advance", "reject", "withdraw", "rollback", "undo_reject", "transfer"]
    expected_version: int = Field(ge=1)
    reason: str = Field(default="", max_length=1000)
    reason_code: Literal[
        "", "requirements", "experience", "skills", "salary", "location", "other"
    ] = ""
    target_stage: Literal["reach", "talking", "ai_eval", "interview", "manager_eval"] | None = None
    target_position_id: str = Field(default="", max_length=64)
    notify: bool = False
