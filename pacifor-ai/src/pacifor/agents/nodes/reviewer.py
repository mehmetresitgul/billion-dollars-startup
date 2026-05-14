from pacifor.agents.guards import guard
from pacifor.agents.hitl import hitl_gate


@guard
async def reviewer_node(state: dict, config=None) -> dict:
    """
    HITL gate: the human must approve the plan before execution begins.

    Returns a partial state update {"hitl_approved": True} on approval.
    Raises HITLRejected on rejection; raises KillSwitchEngaged if the
    kill switch fires before this node runs (handled by @guard).
    """
    return await hitl_gate(
        state,
        node_name="reviewer",
        payload={"plan": state.get("plan")},
    )
