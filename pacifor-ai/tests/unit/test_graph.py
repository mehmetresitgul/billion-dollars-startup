"""
Unit tests for graph.py and individual node functions.

Strategy:
  - Node tests: engage/release the global kill_switch singleton (autouse fixture
    in conftest.py resets it after each test).
  - HITL tests: patch pacifor.agents.hitl.interrupt to skip the real pause.
  - Graph integration tests: combine both, run graph.ainvoke() end-to-end.
"""
import pytest
from unittest.mock import patch

from langgraph.checkpoint.memory import MemorySaver

from pacifor.agents.graph import build_graph
from pacifor.agents.nodes.executor import executor_node
from pacifor.agents.nodes.planner import planner_node
from pacifor.agents.nodes.reviewer import reviewer_node
from pacifor.core.audit import AuditLogger, audit_logger
from pacifor.core.exceptions import HITLRejected, KillSwitchEngaged
from pacifor.core.kill_switch import kill_switch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(**overrides) -> dict:
    base = {
        "run_id": "run-1",
        "agent_id": "default",
        "user_id": "user-1",
        "messages": [{"role": "user", "content": "Build a dashboard"}],
        "plan": None,
        "result": None,
        "hitl_approved": False,
    }
    return {**base, **overrides}


def _approve():
    return patch("pacifor.agents.hitl.interrupt", return_value={"approved": True})


def _reject():
    return patch("pacifor.agents.hitl.interrupt", return_value={"approved": False})


# ---------------------------------------------------------------------------
# planner_node
# ---------------------------------------------------------------------------

class TestPlannerNode:
    async def test_returns_plan_key(self) -> None:
        result = await planner_node(make_state())
        assert "plan" in result

    async def test_plan_is_non_empty_string(self) -> None:
        result = await planner_node(make_state())
        assert isinstance(result["plan"], str)
        assert len(result["plan"]) > 0

    async def test_plan_contains_last_message_content(self) -> None:
        state = make_state(messages=[{"role": "user", "content": "Write a report"}])
        result = await planner_node(state)
        assert "Write a report" in result["plan"]

    async def test_plan_with_no_messages(self) -> None:
        result = await planner_node(make_state(messages=[]))
        assert "plan" in result  # must not raise

    async def test_returns_partial_state_only(self) -> None:
        result = await planner_node(make_state())
        assert set(result.keys()) == {"plan"}

    async def test_emits_audit_event(self) -> None:
        logger = AuditLogger()
        with patch("pacifor.agents.nodes.planner.audit_logger", logger):
            await planner_node(make_state())
        events = logger.filter(action="plan", node_name="planner")
        assert len(events) == 1
        assert events[0].outcome == "success"

    async def test_halts_when_kill_switch_engaged(self) -> None:
        await kill_switch.engage(reason="test")
        with pytest.raises(KillSwitchEngaged):
            await planner_node(make_state())

    async def test_works_after_kill_switch_released(self) -> None:
        await kill_switch.engage()
        await kill_switch.release()
        result = await planner_node(make_state())
        assert "plan" in result


# ---------------------------------------------------------------------------
# reviewer_node
# ---------------------------------------------------------------------------

class TestReviewerNode:
    async def test_returns_hitl_approved_true_on_approval(self) -> None:
        with _approve():
            result = await reviewer_node(make_state(plan="a plan"))
        assert result == {"hitl_approved": True}

    async def test_raises_hitl_rejected_on_rejection(self) -> None:
        with _reject():
            with pytest.raises(HITLRejected):
                await reviewer_node(make_state(plan="a plan"))

    async def test_halts_when_kill_switch_engaged(self) -> None:
        await kill_switch.engage()
        with _approve():  # even if HITL would approve, kill switch fires first
            with pytest.raises(KillSwitchEngaged):
                await reviewer_node(make_state())

    async def test_passes_plan_to_hitl_gate(self) -> None:
        captured = {}

        def fake_interrupt(payload):
            captured["payload"] = payload
            return {"approved": True}

        with patch("pacifor.agents.hitl.interrupt", side_effect=fake_interrupt):
            await reviewer_node(make_state(plan="my special plan"))

        assert captured["payload"]["payload"]["plan"] == "my special plan"


# ---------------------------------------------------------------------------
# executor_node
# ---------------------------------------------------------------------------

class TestExecutorNode:
    async def test_returns_result_key(self) -> None:
        result = await executor_node(make_state(plan="step 1"))
        assert "result" in result

    async def test_result_contains_plan(self) -> None:
        result = await executor_node(make_state(plan="deploy to prod"))
        assert "deploy to prod" in result["result"]

    async def test_result_with_no_plan(self) -> None:
        result = await executor_node(make_state(plan=None))
        assert "result" in result  # must not raise

    async def test_returns_partial_state_only(self) -> None:
        result = await executor_node(make_state(plan="x"))
        assert set(result.keys()) == {"result"}

    async def test_emits_audit_event(self) -> None:
        logger = AuditLogger()
        with patch("pacifor.agents.nodes.executor.audit_logger", logger):
            await executor_node(make_state(plan="x"))
        events = logger.filter(action="execute", node_name="executor")
        assert len(events) == 1
        assert events[0].outcome == "success"

    async def test_halts_when_kill_switch_engaged(self) -> None:
        await kill_switch.engage()
        with pytest.raises(KillSwitchEngaged):
            await executor_node(make_state(plan="x"))


# ---------------------------------------------------------------------------
# build_graph()
# ---------------------------------------------------------------------------

class TestBuildGraph:
    def test_returns_compiled_graph(self) -> None:
        g = build_graph()
        assert g is not None

    def test_uses_memory_saver_by_default(self) -> None:
        # build_graph() must not raise — MemorySaver is wired automatically
        g = build_graph()
        assert g is not None

    def test_accepts_custom_checkpointer(self) -> None:
        custom = MemorySaver()
        g = build_graph(checkpointer=custom)
        assert g is not None

    def test_graph_has_planner_node(self) -> None:
        g = build_graph()
        assert "planner" in g.get_graph().nodes

    def test_graph_has_reviewer_node(self) -> None:
        g = build_graph()
        assert "reviewer" in g.get_graph().nodes

    def test_graph_has_executor_node(self) -> None:
        g = build_graph()
        assert "executor" in g.get_graph().nodes


# ---------------------------------------------------------------------------
# Graph integration — full run
# ---------------------------------------------------------------------------

class TestGraphIntegration:
    @pytest.fixture
    def g(self):
        return build_graph(checkpointer=MemorySaver())

    def _config(self, thread_id: str = "t1") -> dict:
        return {"configurable": {"thread_id": thread_id}}

    async def test_full_run_approved(self, g) -> None:
        """planner → reviewer (HITL approve) → executor → END in one ainvoke."""
        with _approve():
            result = await g.ainvoke(make_state(), config=self._config("t-approve"))

        assert result["plan"] is not None
        assert result["result"] is not None
        assert result["hitl_approved"] is True

    async def test_full_run_rejected_raises(self, g) -> None:
        with _reject():
            with pytest.raises(HITLRejected):
                await g.ainvoke(make_state(), config=self._config("t-reject"))

    async def test_full_run_kill_switch_at_planner(self, g) -> None:
        await kill_switch.engage(reason="graph-test")
        with _approve():
            with pytest.raises(KillSwitchEngaged):
                await g.ainvoke(make_state(), config=self._config("t-kill-plan"))

    async def test_kill_switch_blocks_second_run_when_engaged(self, g) -> None:
        """
        Kill switch engaged after a successful run must block the next run.
        This verifies persistence across invocations on the same graph instance.
        """
        # First run completes normally
        with _approve():
            result = await g.ainvoke(make_state(), config=self._config("t-run-1"))
        assert result["result"] is not None

        # Operator engages kill switch between runs
        await kill_switch.engage(reason="post-run-block")

        # Second run must halt immediately
        with _approve():
            with pytest.raises(KillSwitchEngaged):
                await g.ainvoke(make_state(), config=self._config("t-run-2"))

    async def test_result_contains_plan_content(self, g) -> None:
        state = make_state(messages=[{"role": "user", "content": "Launch rocket"}])
        with _approve():
            result = await g.ainvoke(state, config=self._config("t-content"))
        assert "Launch rocket" in result["plan"]
        assert result["result"] is not None

    async def test_each_thread_is_independent(self, g) -> None:
        """Two concurrent runs in the same graph must not share state."""
        with _approve():
            r1 = await g.ainvoke(
                make_state(run_id="run-A", messages=[{"role": "user", "content": "Task A"}]),
                config=self._config("thread-A"),
            )
            r2 = await g.ainvoke(
                make_state(run_id="run-B", messages=[{"role": "user", "content": "Task B"}]),
                config=self._config("thread-B"),
            )

        assert "Task A" in r1["plan"]
        assert "Task B" in r2["plan"]
        assert r1["plan"] != r2["plan"]
