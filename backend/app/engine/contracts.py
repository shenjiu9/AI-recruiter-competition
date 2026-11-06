from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Component = Literal["A1", "A2", "A3", "A4", "A5", "A6", "A7"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StartJob(StrictModel):
    component: Component
    object_id: str = Field(min_length=1, max_length=64)
    prompt: str = Field(default="", max_length=8000)


class JobCommand(StrictModel):
    expected_version: int = Field(ge=1)
    action: Literal["approve", "reject", "cancel", "retry"]
    reason: str = Field(min_length=1, max_length=1000)
    verified: bool = False


class Evidence(StrictModel):
    source: Literal["resume", "message", "transcript", "knowledge", "profile"]
    ref: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=2000)


class EvaluationItem(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    verdict: Literal["meet", "not_meet", "unknown"]
    evidence: list[Evidence] = Field(default_factory=list, max_length=12)
    note: str = Field(default="", max_length=1000)


class Evaluation(StrictModel):
    items: list[EvaluationItem] = Field(min_length=1, max_length=100)
    questions: list[str] = Field(default_factory=list, max_length=30)
    self_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class Claim(StrictModel):
    kb_ref: str = Field(min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=2000)


class Reply(StrictModel):
    reply: str = Field(min_length=1, max_length=300)
    claims: list[Claim] = Field(default_factory=list, max_length=12)
    intents: list[
        Literal[
            "interested",
            "not_interested",
            "withdraw",
            "ask_human",
            "reschedule",
            "complaint",
            "unsubscribe",
        ]
    ] = Field(default_factory=list, max_length=7)
    needs_human: bool = False
    self_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)


class Draft(StrictModel):
    fields: dict[str, str] = Field(default_factory=dict, max_length=15)
    pending: list[str] = Field(default_factory=list, max_length=20)
    reply: str = Field(default="", max_length=4000)


class ExtractedField(StrictModel):
    value: str = Field(max_length=4000)
    evidence: Evidence


class Extraction(StrictModel):
    fields: dict[str, ExtractedField] = Field(max_length=20)


class SearchPlan(StrictModel):
    keywords: list[str] = Field(max_length=30)
    city: list[str] = Field(default_factory=list, max_length=20)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=30)
    explanation: str = Field(max_length=2000)


class FeedbackItem(StrictModel):
    id: str = Field(max_length=80)
    notes: str = Field(max_length=2000)
    evidence: list[Evidence] = Field(min_length=1, max_length=12)


class FeedbackDraft(StrictModel):
    items: list[FeedbackItem] = Field(min_length=1, max_length=30)


class Insight(StrictModel):
    answer: str = Field(max_length=6000)
    data_refs: list[str] = Field(min_length=1, max_length=50)
    suggestions: list[str] = Field(default_factory=list, max_length=20)


OUTPUTS = {
    "A1": Draft,
    "A2": SearchPlan,
    "A3": Extraction,
    "A4": Reply,
    "A5": Evaluation,
    "A6": FeedbackDraft,
    "A7": Insight,
}
NODES = {
    "A1": "draft",
    "A2": "attach",
    "A3": "attach",
    "A4": "conversation",
    "A5": "advance",
    "A6": "ai_interview",
    "A7": "hire",
}
