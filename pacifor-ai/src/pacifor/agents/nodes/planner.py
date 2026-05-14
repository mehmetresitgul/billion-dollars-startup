from pacifor.agents.guards import guard
from pacifor.core.audit import AuditEvent, audit_logger


@guard
async def planner_node(state: dict, config=None) -> dict:
    await audit_logger.emit(
        AuditEvent.build(
            run_id=state["run_id"],
            node_name="planner",
            action="plan",
            outcome="success",
            agent_id=state.get("agent_id", "default"),
            user_id=state.get("user_id"),
            payload={"message_count": len(state.get("messages", []))},
        )
    )

    # Replace with actual LLM call (e.g. ChatOpenAI)
    plan = "Step 1: Analyze input. Step 2: Execute action. Step 3: Review output."
    return {**state, "plan": plan}
