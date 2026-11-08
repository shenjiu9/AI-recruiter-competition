from app.kernel.types import DomainError


class QueryFacade:
    def __init__(self, positions, applications, hiring, decisions, candidates, requisitions):
        self.requisitions = requisitions
        self.positions, self.applications, self.hiring, self.decisions, self.candidates = (
            positions,
            applications,
            hiring,
            decisions,
            candidates,
        )

    def workbench(self, ctx):
        self.candidates.lock(ctx)
        positions = []
        for raw in self.positions.hiring_positions():
            try:
                p = self.positions.get(ctx, raw["id"])
                positions.append(
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "status": p["status"],
                        "planned": p["planned"],
                        "hired": p["hired"],
                        "remaining": max(0, p["planned"] - p["hired"]),
                        "stages": p["candidateCounts"]["stages"],
                    }
                )
            except DomainError:
                continue
        hires = self.hiring.listing(ctx)
        cards = self.decisions.listing(ctx)
        approvals = self.requisitions.pending_approvals(ctx)
        return {
            "counts": {
                "open_positions": sum(p["status"] == "open" for p in positions),
                "remaining": sum(p["remaining"] for p in positions if p["status"] == "open"),
                "cards": len(cards),
                "pending_handoffs": sum(h["can_handover"] for h in hires),
                "pending_results": sum(h["can_result"] for h in hires),
                "my_approvals": len(approvals) + sum(h["can_approve"] for h in hires),
            },
            "positions": positions,
            "cards": cards,
            "hires": hires,
            "requisition_approvals": approvals,
            "ai_enabled": False,
            "ai_activity": [],
            "projection": "transactional_read",
        }
