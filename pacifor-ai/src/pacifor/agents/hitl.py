"""
HITL gate helper.

Calling hitl_gate() inside a node:
  1. Emits an audit event (action="hitl_interrupt", outcome="pending")
  2. Calls LangGraph's interrupt() — pauses the graph and hands the review
     payload to the caller
  3. When the human approves/rejects via API, the graph is resumed with
     Command(resume={"approved": bool, "reason": str})
  4. Emits a second audit event with the decision outcome
  5. Raises HITLRejected if the human rejected; otherwise returns updated state
"""
import uuid
from typing import Any

from langgraph.types import interrupt

from pacifor.core.audit import AuditEvent, audit_logger
from pacifor.core.exceptions import HITLRejected


async def hitl_gate(state: dict, *, node_name: str, payload: dict[str, Any]) -> dict:
    review_id = str(uuid.uuid4())

    await audit_logger.emit(
        AuditEvent.build(
            run_id=state["run_id"],
            node_name=node_name,
            action="hitl_interrupt",
            outcome="pending",
            agent_id=state.get("agent_id", "default"),
            user_id=state.get("user_id"),
            payload={"review_id": review_id, **payload},
        )
    )

    decision: dict = interrupt({"review_id": review_id, "payload": payload})
    approved: bool = bool(decision.get("approved", False))
    outcome = "approved" if approved else "rejected"

    await audit_logger.emit(
        AuditEvent.build(
            run_id=state["run_id"],
            node_name=node_name,
            action="hitl_decision",
            outcome=outcome,
            agent_id=state.get("agent_id", "default"),
            user_id=decision.get("decided_by") or state.get("user_id"),
            payload={"review_id": review_id, "approved": approved},
        )
    )

    if not approved:
        raise HITLRejected(review_id=review_id, node_name=node_name)

    return {**state, "hitl_approved": True}
