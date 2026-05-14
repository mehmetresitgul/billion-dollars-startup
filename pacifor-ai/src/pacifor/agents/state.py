from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    run_id: str
    agent_id: str
    user_id: str
    messages: Annotated[list, add_messages]
    plan: str | None
    result: str | None
    hitl_approved: bool
