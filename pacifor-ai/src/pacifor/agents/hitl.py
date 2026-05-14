"""
HITL gate helper used inside LangGraph nodes.

Flow (single reviewer_node execution):
  Pass 1 — graph.ainvoke() first call:
    1. Emit audit(action="hitl_interrupt", outcome="pending")
    2. interrupt(payload) raises GraphInterrupt → graph pauses, thread saved to checkpointer
    3. Caller (run_service) sees NodeInterrupt, stores review_id for human action

  Pass 2 — graph.ainvoke(Command(resume=decision)):
    1. LangGraph restores thread and re-enters the node; interrupt() returns `decision`
    2. Validate decision dict
    3. Emit audit(action="hitl_decision", outcome="approved"|"rejected")
    4. Raise HITLRejected on rejection; return {"hitl_approved": True} on approval

Returns a *partial* state update dict — LangGraph merges it into the graph state.
"""
import uuid
from typing import Any

from langgraph.types import interrupt

from pacifor.core.audit import AuditEvent, AuditLogger, audit_logger as _global_audit_logger
from pacifor.core.exceptions import HITLRejected


async def hitl_gate(
    state: dict,
    *,
    node_name: str,
    payload: dict[str, Any],
    logger: AuditLogger = _global_audit_logger,
) -> dict:
    """
    Pause execution at a HITL checkpoint and wait for human approval.

    Returns a partial state update: {"hitl_approved": True}.
    Raises HITLRejected if the human rejects.

    `logger` can be injected in tests to avoid touching the global AuditLogger.
    """
    review_id = str(uuid.uuid4())

    await logger.emit(
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

    # Pauses on pass 1; returns decision on pass 2 after Command(resume=decision).
    raw_decision: Any = interrupt({"review_id": review_id, "payload": payload})

    # Treat non-dict or missing "approved" as rejection — safety default.
    decision: dict = raw_decision if isinstance(raw_decision, dict) else {}
    approved: bool = bool(decision.get("approved", False))
    outcome = "approved" if approved else "rejected"

    await logger.emit(
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

    return {"hitl_approved": True}
