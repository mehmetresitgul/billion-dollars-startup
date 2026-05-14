from langgraph.graph import StateGraph, END

from pacifor.agents.nodes import executor_node, planner_node, reviewer_node
from pacifor.agents.state import AgentState


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("planner", planner_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("executor", executor_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "reviewer")
    builder.add_edge("reviewer", "executor")
    builder.add_edge("executor", END)

    return builder.compile()


graph = build_graph()
