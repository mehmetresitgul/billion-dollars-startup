"""
Pacifor agent graph.

build_graph() accepts an optional checkpointer.  A checkpointer is *required*
for LangGraph's interrupt() to work — without one, HITL gates raise at runtime.
MemorySaver is used by default (single-process / tests).
Pass a SQLAlchemy-backed checkpointer for multi-process production use.
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from pacifor.agents.nodes import executor_node, planner_node, reviewer_node
from pacifor.agents.state import AgentState


def build_graph(checkpointer=None):
    """
    Build and compile the Pacifor StateGraph.

    Node flow:  planner → reviewer (HITL gate) → executor → END
    """
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("executor", executor_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "reviewer")
    builder.add_edge("reviewer", "executor")
    builder.add_edge("executor", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())


# Module-level singleton used by run_service.
graph = build_graph()
