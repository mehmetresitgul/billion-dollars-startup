"""
HITL service: tracks pending reviews and resumes the graph on decision.
In-memory store for MVP — replace with DB (HITLReview model) when ready.
"""
import json
from datetime import datetime, UTC
from typing import Optional

from pacifor.api.schemas.hitl import HITLDecision

_reviews: dict[str, dict] = {}


class HITLService:
    async def add_pending(
        self, review_id: str, run_id: str, node_name: str, payload: dict
    ) -> None:
        _reviews[review_id] = {
            "id": review_id,
            "run_id": run_id,
            "node_name": node_name,
            "payload": payload,
            "status": "pending",
            "created_at": datetime.now(UTC),
        }

    async def list_pending(self) -> list[dict]:
        return [r for r in _reviews.values() if r["status"] == "pending"]

    async def decide(
        self, review_id: str, approved: bool, body: HITLDecision
    ) -> None:
        if review_id not in _reviews:
            raise KeyError(review_id)

        review = _reviews[review_id]
        review["status"] = "approved" if approved else "rejected"
        review["approved"] = approved
        review["decided_by"] = body.decided_by
        review["decided_at"] = datetime.now(UTC).isoformat()

        # Resume the paused graph with the human decision
        from pacifor.services.run_service import run_service
        await run_service.resume(
            run_id=review["run_id"],
            decision={
                "approved": approved,
                "reason": body.reason,
                "decided_by": body.decided_by,
            },
        )


hitl_service = HITLService()
