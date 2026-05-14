from pacifor.agents.guards import guard
from pacifor.agents.hitl import hitl_gate


@guard
async def reviewer_node(state: dict, config=None) -> dict:
    """Human must approve the plan before execution proceeds."""
    return await hitl_gate(
        state,
        node_name="reviewer",
        payload={"plan": state.get("plan")},
    )
