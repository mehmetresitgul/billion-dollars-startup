"""
Unit tests for guards.py.

Uses make_guard() with isolated KillSwitch and AuditLogger instances so the
global singletons are never touched.
"""
import pytest
from unittest.mock import AsyncMock

from pacifor.agents.guards import make_guard
from pacifor.core.audit import AuditEvent, AuditLogger
from pacifor.core.exceptions import KillSwitchEngaged
from pacifor.core.kill_switch import KillSwitch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ks() -> KillSwitch:
    return KillSwitch()


@pytest.fixture
def logger() -> AuditLogger:
    return AuditLogger()


@pytest.fixture
def guarded(ks, logger):
    """Returns (guard_decorator, ks, logger) so tests can engage ks and inspect logger."""
    return make_guard(ks, logger), ks, logger


# ---------------------------------------------------------------------------
# Pass-through behaviour (kill switch OFF)
# ---------------------------------------------------------------------------

class TestGuardPassThrough:
    async def test_calls_wrapped_function(self, guarded):
        guard, ks, _ = guarded
        called = {}

        @guard
        async def my_node(state, config=None):
            called["yes"] = True
            return {"ok": True}

        result = await my_node({"run_id": "r1"})
        assert called.get("yes") is True
        assert result == {"ok": True}

    async def test_passes_state_unchanged(self, guarded):
        guard, ks, _ = guarded
        received = {}

        @guard
        async def my_node(state, config=None):
            received.update(state)
            return {}

        state = {"run_id": "r1", "agent_id": "test-agent", "user_id": "u1"}
        await my_node(state)
        assert received["run_id"] == "r1"
        assert received["agent_id"] == "test-agent"

    async def test_passes_config_to_node(self, guarded):
        guard, ks, _ = guarded
        received = {}

        @guard
        async def my_node(state, config=None):
            received["config"] = config
            return {}

        cfg = {"thread_id": "t1"}
        await my_node({"run_id": "r1"}, config=cfg)
        assert received["config"] == cfg

    async def test_returns_node_return_value(self, guarded):
        guard, ks, _ = guarded

        @guard
        async def my_node(state, config=None):
            return {"plan": "step 1"}

        result = await my_node({"run_id": "r1"})
        assert result == {"plan": "step 1"}

    async def test_no_audit_event_emitted_when_not_killed(self, guarded):
        guard, ks, logger = guarded

        @guard
        async def my_node(state, config=None):
            return {}

        await my_node({"run_id": "r1"})
        assert len(logger) == 0

    async def test_preserves_function_name(self, guarded):
        guard, _, _ = guarded

        @guard
        async def special_node(state, config=None):
            return {}

        assert special_node.__name__ == "special_node"

    async def test_preserves_function_docstring(self, guarded):
        guard, _, _ = guarded

        @guard
        async def documented_node(state, config=None):
            """This node does something."""
            return {}

        assert documented_node.__doc__ == "This node does something."


# ---------------------------------------------------------------------------
# Kill switch engaged — halt and audit
# ---------------------------------------------------------------------------

class TestGuardKillSwitch:
    async def test_raises_kill_switch_engaged(self, guarded):
        guard, ks, _ = guarded
        await ks.engage(reason="emergency")

        @guard
        async def my_node(state, config=None):
            return {}

        with pytest.raises(KillSwitchEngaged):
            await my_node({"run_id": "r1"})

    async def test_node_body_not_called_when_killed(self, guarded):
        guard, ks, _ = guarded
        await ks.engage()
        called = {}

        @guard
        async def my_node(state, config=None):
            called["yes"] = True
            return {}

        with pytest.raises(KillSwitchEngaged):
            await my_node({"run_id": "r1"})

        assert "yes" not in called

    async def test_emits_audit_event_on_kill(self, guarded):
        guard, ks, logger = guarded
        await ks.engage(reason="quota-exceeded")

        @guard
        async def billing_node(state, config=None):
            return {}

        with pytest.raises(KillSwitchEngaged):
            await billing_node({"run_id": "run-42", "agent_id": "billing"})

        events = logger.filter(action="kill_switch_halt")
        assert len(events) == 1
        assert events[0].run_id == "run-42"
        assert events[0].node_name == "billing_node"
        assert events[0].outcome == "killed"

    async def test_audit_event_contains_reason(self, guarded):
        guard, ks, logger = guarded
        await ks.engage(reason="rate-limit")

        @guard
        async def my_node(state, config=None):
            return {}

        with pytest.raises(KillSwitchEngaged):
            await my_node({"run_id": "r1"})

        event = logger.filter(action="kill_switch_halt")[0]
        # reason is hashed into payload_hash; check it's non-None
        assert event.payload_hash is not None

    async def test_kill_switch_engaged_carries_reason(self, guarded):
        guard, ks, _ = guarded
        await ks.engage(reason="manual-override")

        @guard
        async def my_node(state, config=None):
            return {}

        with pytest.raises(KillSwitchEngaged) as exc_info:
            await my_node({"run_id": "r1"})

        assert "manual-override" in exc_info.value.reason

    async def test_guard_uses_unknown_run_id_when_state_missing(self, guarded):
        guard, ks, logger = guarded
        await ks.engage()

        @guard
        async def my_node(state, config=None):
            return {}

        with pytest.raises(KillSwitchEngaged):
            await my_node({})  # no run_id in state

        event = logger.filter(action="kill_switch_halt")[0]
        assert event.run_id == "unknown"

    async def test_guard_recovers_after_release(self, guarded):
        guard, ks, _ = guarded
        await ks.engage()

        @guard
        async def my_node(state, config=None):
            return {"ok": True}

        with pytest.raises(KillSwitchEngaged):
            await my_node({"run_id": "r1"})

        await ks.release()
        result = await my_node({"run_id": "r1"})
        assert result == {"ok": True}


# ---------------------------------------------------------------------------
# make_guard isolation
# ---------------------------------------------------------------------------

class TestMakeGuardIsolation:
    async def test_two_guards_use_independent_kill_switches(self):
        ks1, ks2 = KillSwitch(), KillSwitch()
        logger = AuditLogger()
        guard1 = make_guard(ks1, logger)
        guard2 = make_guard(ks2, logger)

        @guard1
        async def node1(state, config=None):
            return {"from": "node1"}

        @guard2
        async def node2(state, config=None):
            return {"from": "node2"}

        await ks1.engage()

        with pytest.raises(KillSwitchEngaged):
            await node1({"run_id": "r1"})

        # ks2 not engaged — node2 must still pass
        result = await node2({"run_id": "r2"})
        assert result == {"from": "node2"}
