from app.kernel.types import DomainError

TRANSITIONS = {
    ("draft", "submit"): "in_approval",
    ("rejected", "submit"): "in_approval",
    ("withdrawn", "submit"): "in_approval",
    ("in_approval", "approve"): "approved",
    ("in_approval", "reject"): "rejected",
    ("in_approval", "withdraw"): "withdrawn",
}


def transition(state: str, action: str) -> str:
    try:
        return TRANSITIONS[state, action]
    except KeyError:
        raise DomainError("INVALID_TRANSITION", f"当前状态 {state} 不允许 {action}", 409) from None
