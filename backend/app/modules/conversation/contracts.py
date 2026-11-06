from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal[
        "send",
        "take_over",
        "hand_back",
        "issue_link",
        "revoke_links",
        "consent",
        "revoke",
        "do_not_contact",
        "ask_human",
        "correction_request",
        "deletion_request",
        "resolve_request",
    ]
    expected_version: int = Field(ge=0)
    content: str = Field(default="", max_length=4000)
    application_ids: list[str] = Field(default_factory=list, max_length=30)
    reply_to_id: str = Field(default="", max_length=64)
    request_id: str = Field(default="", max_length=64)
