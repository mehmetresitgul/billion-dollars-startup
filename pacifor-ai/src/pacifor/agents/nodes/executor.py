from pacifor.agents.guards import guard
from pacifor.core.audit import AuditEvent, audit_logger


@guard
async def executor_node(state: dict, config=None) -> dict:
    plan = state.get("plan") or ""

    # Production: replace with the real execution logic (tool calls, API, etc.)
    result = f"Executed: {plan}"

    await audit_logger.emit(
        AuditEvent.build(
            run_id=state["run_id"],
            node_name="executor",
            action="execute",
            outcome="success",
            agent_id=state.get("agent_id", "default"),
            user_id=state.get("user_id"),
            payload={"plan_length": len(plan)},
        )
    )

    return {"result": result}
