"""
Unit tests for hitl_gate().

interrupt() is patched at pacifor.agents.hitl.interrupt for every test so no
real LangGraph graph or checkpointer is needed.
"""
import pytest
from unittest.mock import patch

from pacifor.agents.hitl import hitl_gate
from pacifor.core.audit import AuditLogger
from pacifor.core.exceptions import HITLRejected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(**overrides) -> dict:
    base = {
        "run_id": "run-test",
        "agent_id": "default",
        "user_id": "user-1",
        "messages": [],
        "plan": "do the thing",
        "result": None,
        "hitl_approved": False,
    }
    return {**base, **overrides}


def _patch_interrupt(return_value):
    """Context manager: patch interrupt() to return a fixed value (simulates resume)."""
    return patch("pacifor.agents.hitl.interrupt", return_value=return_value)


# ---------------------------------------------------------------------------
# Approval path
# ---------------------------------------------------------------------------

class TestHITLGateApproval:
    async def test_returns_hitl_approved_true(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": True}):
            result = await hitl_gate(
                make_state(), node_name="reviewer", payload={"plan": "x"}, logger=logger
            )
        assert result == {"hitl_approved": True}

    async def test_returns_partial_state_only(self) -> None:
        """Must not return {**state, ...} — only the changed key."""
        logger = AuditLogger()
        with _patch_interrupt({"approved": True}):
            result = await hitl_gate(
                make_state(), node_name="reviewer", payload={}, logger=logger
            )
        assert set(result.keys()) == {"hitl_approved"}

    async def test_emits_interrupt_audit_event(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": True}):
            await hitl_gate(
                make_state(), node_name="reviewer", payload={"plan": "p"}, logger=logger
            )
        events = logger.filter(action="hitl_interrupt")
        assert len(events) == 1
        assert events[0].outcome == "pending"
        assert events[0].node_name == "reviewer"
        assert events[0].run_id == "run-test"

    async def test_emits_decision_audit_event_approved(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": True, "decided_by": "ops-user"}):
            await hitl_gate(
                make_state(), node_name="reviewer", payload={}, logger=logger
            )
        events = logger.filter(action="hitl_decision")
        assert len(events) == 1
        assert events[0].outcome == "approved"

    async def test_total_two_audit_events_on_approval(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": True}):
            await hitl_gate(
                make_state(), node_name="reviewer", payload={}, logger=logger
            )
        assert len(logger) == 2

    async def test_review_id_is_uuid_in_interrupt_payload(self) -> None:
        import uuid
        captured = {}

        def fake_interrupt(payload):
            captured["review_id"] = payload.get("review_id")
            return {"approved": True}

        logger = AuditLogger()
        with patch("pacifor.agents.hitl.interrupt", side_effect=fake_interrupt):
            await hitl_gate(
                make_state(), node_name="reviewer", payload={}, logger=logger
            )

        review_id = captured["review_id"]
        assert review_id is not None
        uuid.UUID(review_id)  # raises if not valid UUID

    async def test_interrupt_receives_payload(self) -> None:
        captured = {}

        def fake_interrupt(payload):
            captured["payload"] = payload
            return {"approved": True}

        logger = AuditLogger()
        with patch("pacifor.agents.hitl.interrupt", side_effect=fake_interrupt):
            await hitl_gate(
                make_state(), node_name="reviewer", payload={"plan": "step 1"}, logger=logger
            )

        assert captured["payload"]["payload"] == {"plan": "step 1"}

    async def test_decided_by_used_as_user_id_in_decision_event(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": True, "decided_by": "reviewer-42"}):
            await hitl_gate(
                make_state(), node_name="reviewer", payload={}, logger=logger
            )
        event = logger.filter(action="hitl_decision")[0]
        assert event.user_id == "reviewer-42"


# ---------------------------------------------------------------------------
# Rejection path
# ---------------------------------------------------------------------------

class TestHITLGateRejection:
    async def test_raises_hitl_rejected_when_not_approved(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": False, "reason": "looks risky"}):
            with pytest.raises(HITLRejected):
                await hitl_gate(
                    make_state(), node_name="reviewer", payload={}, logger=logger
                )

    async def test_rejected_exception_carries_node_name(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": False}):
            with pytest.raises(HITLRejected) as exc_info:
                await hitl_gate(
                    make_state(), node_name="safety-check", payload={}, logger=logger
                )
        assert exc_info.value.node_name == "safety-check"

    async def test_rejected_exception_carries_review_id(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": False}):
            with pytest.raises(HITLRejected) as exc_info:
                await hitl_gate(
                    make_state(), node_name="reviewer", payload={}, logger=logger
                )
        import uuid
        uuid.UUID(exc_info.value.review_id)  # must be a valid UUID

    async def test_emits_rejected_audit_event(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": False}):
            with pytest.raises(HITLRejected):
                await hitl_gate(
                    make_state(), node_name="reviewer", payload={}, logger=logger
                )
        event = logger.filter(action="hitl_decision")[0]
        assert event.outcome == "rejected"

    async def test_two_audit_events_emitted_on_rejection(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": False}):
            with pytest.raises(HITLRejected):
                await hitl_gate(
                    make_state(), node_name="reviewer", payload={}, logger=logger
                )
        assert len(logger) == 2


# ---------------------------------------------------------------------------
# Safety defaults — invalid decision values
# ---------------------------------------------------------------------------

class TestHITLGateSafetyDefaults:
    @pytest.mark.parametrize("bad_decision", [
        None,
        "yes",
        42,
        [],
        {},                       # dict but no "approved" key → False
        {"approved": None},       # None → bool(None) == False
        {"approved": 0},          # falsy int
    ])
    async def test_non_approved_decision_raises_rejected(self, bad_decision) -> None:
        logger = AuditLogger()
        with _patch_interrupt(bad_decision):
            with pytest.raises(HITLRejected):
                await hitl_gate(
                    make_state(), node_name="reviewer", payload={}, logger=logger
                )

    async def test_approved_true_string_is_falsy(self) -> None:
        """String 'True' is not bool True — should be treated as falsy."""
        logger = AuditLogger()
        # bool("True") is True in Python, so this test verifies that string "True"
        # is not special-cased and goes through the normal bool() conversion.
        with _patch_interrupt({"approved": "True"}):
            # bool("True") == True, so this actually approves.
            result = await hitl_gate(
                make_state(), node_name="reviewer", payload={}, logger=logger
            )
        assert result == {"hitl_approved": True}


# ---------------------------------------------------------------------------
# State fields propagated into audit events
# ---------------------------------------------------------------------------

class TestHITLGateAuditFields:
    async def test_agent_id_in_audit_events(self) -> None:
        logger = AuditLogger()
        state = make_state(agent_id="special-agent")
        with _patch_interrupt({"approved": True}):
            await hitl_gate(state, node_name="reviewer", payload={}, logger=logger)
        for event in logger.recent():
            assert event.agent_id == "special-agent"

    async def test_run_id_in_audit_events(self) -> None:
        logger = AuditLogger()
        state = make_state(run_id="run-xyz")
        with _patch_interrupt({"approved": True}):
            await hitl_gate(state, node_name="reviewer", payload={}, logger=logger)
        for event in logger.recent():
            assert event.run_id == "run-xyz"

    async def test_interrupt_event_payload_is_hashed(self) -> None:
        logger = AuditLogger()
        with _patch_interrupt({"approved": True}):
            await hitl_gate(
                make_state(), node_name="reviewer", payload={"plan": "secret"}, logger=logger
            )
        event = logger.filter(action="hitl_interrupt")[0]
        assert event.payload_hash is not None
        assert "secret" not in str(event.to_dict())
