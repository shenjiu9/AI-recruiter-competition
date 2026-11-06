"""Provider port and durable provision/compensation steps.

No production provider is enabled implicitly. Implementations must use bounded timeouts,
honour the idempotency key, and return the same reference after a lost response.
"""

from typing import Protocol


class InterviewGateway(Protocol):
    def meeting_create(self, interview: dict, key: str) -> str: ...
    def calendar_create(self, interview: dict, key: str) -> str: ...
    def meeting_cancel(self, reference: str, key: str) -> None: ...
    def calendar_cancel(self, reference: str, key: str) -> None: ...


class IntegrationRejected(Exception):
    """Provider definitively rejected the request without creating a resource."""


def step(iv, gateway):
    """One external effect per committed step; failures compensate persisted references."""
    task = iv["integration"]
    state = task["state"]
    if not gateway or state not in {"pending", "calendar_pending", "cleanup"}:
        return False
    key = f"{iv['id']}:{task['generation']}"
    try:
        if state == "cleanup":
            if task.get("calendar"):
                gateway.calendar_cancel(task["calendar"], key + ":calendar:cancel")
                task["calendar"] = None
            elif task.get("meeting"):
                gateway.meeting_cancel(task["meeting"], key + ":meeting:cancel")
                task["meeting"] = None
            else:
                task["state"] = "cancelled" if iv["status"] == "cancelled" else "failed"
        elif iv["status"] != "scheduled":
            task["state"] = "cleanup"
        elif state == "pending":
            if iv["spec"]["format"] == "video":
                # Recording stays off; collecting consent does not enable recording.
                task["meeting"] = gateway.meeting_create(
                    {**iv, "recording_enabled": False}, key + ":meeting"
                )
            task["state"] = "calendar_pending"
        else:
            task["calendar"] = gateway.calendar_create(iv, key + ":calendar")
            task["state"] = "synced"
        task["attempts"] = 0
    except IntegrationRejected:
        task["state"] = "cleanup"
    except Exception:
        # Never persist provider exception text: it can contain credentials or personal data.
        task["attempts"] = task.get("attempts", 0) + 1
        if state != "cleanup" and task["attempts"] >= 3:
            task["state"] = "uncertain_meeting" if state == "pending" else "uncertain_calendar"
    return True
