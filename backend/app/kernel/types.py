from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str
    roles: tuple[str, ...]
    departments: tuple[str, ...]
    permission_version: int = 1


@dataclass(frozen=True)
class Ctx:
    principal: Principal
    trace_id: str


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 422, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.details = details or {}


class Journal(Protocol):
    def record(
        self,
        ctx: Ctx,
        action: str,
        object_id: str,
        version: int,
        before: dict | None,
        after: dict,
        event: bool = True,
    ) -> None: ...
