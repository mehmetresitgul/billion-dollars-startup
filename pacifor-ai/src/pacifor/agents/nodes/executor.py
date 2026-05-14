from pacifor.agents.guards import guard
from pacifor.core.audit import AuditEvent, audit_logger


@guard
async def executor_node(state: dict, config=None) -> dict:
    await audit_logger.emit(
        AuditEvent.build(
            run_id=state["run_id"],
            node_name="executor",
            action="execute",
            outcome="success",
            agent_id=state.get("agent_id", "default"),
            user_id=state.get("user_id"),
            payload={"plan": state.get("plan")},
        )
    )

    # Replace with actual execution logic
    result = f"Executed: {state.get('plan', 'no plan')}"
    return {**state, "result": result}
