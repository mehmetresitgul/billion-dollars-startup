from pacifor.agents.guards import guard
from pacifor.core.audit import AuditEvent, audit_logger


def _extract_last_content(messages: list) -> str:
    """Pull text from the last message regardless of whether it is a dict or BaseMessage."""
    if not messages:
        return ""
    last = messages[-1]
    if isinstance(last, dict):
        return str(last.get("content", ""))
    return str(getattr(last, "content", ""))


@guard
async def planner_node(state: dict, config=None) -> dict:
    messages = state.get("messages", [])
    last_content = _extract_last_content(messages)

    # Production: replace with an actual LLM call, e.g. await llm.ainvoke(messages)
    plan = (
        f"1. Understand request: {last_content!r}. "
        "2. Gather required context. "
        "3. Produce deliverable. "
        "4. Verify against acceptance criteria."
    )

    await audit_logger.emit(
        AuditEvent.build(
            run_id=state["run_id"],
            node_name="planner",
            action="plan",
            outcome="success",
            agent_id=state.get("agent_id", "default"),
            user_id=state.get("user_id"),
            payload={"message_count": len(messages), "plan_length": len(plan)},
        )
    )

    return {"plan": plan}
