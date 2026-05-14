import pytest
from pacifor.core.audit import AuditEvent
from pacifor.core.hashing import payload_hash


def test_payload_hash_is_deterministic():
    data = {"foo": "bar", "num": 42}
    assert payload_hash(data) == payload_hash(data)


def test_payload_hash_order_independent():
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert payload_hash(a) == payload_hash(b)


def test_audit_event_build_hashes_payload():
    event = AuditEvent.build(
        run_id="run-1",
        node_name="planner",
        action="plan",
        outcome="success",
        payload={"plan": "do something"},
    )
    expected = payload_hash({"plan": "do something"})
    assert event.payload_hash == expected


def test_audit_event_build_no_payload():
    event = AuditEvent.build(
        run_id="run-1",
        node_name="planner",
        action="plan",
        outcome="success",
    )
    assert event.payload_hash is None


def test_audit_event_to_dict_contains_required_fields():
    event = AuditEvent.build(
        run_id="run-1",
        node_name="executor",
        action="execute",
        outcome="success",
    )
    d = event.to_dict()
    for field in ("run_id", "node_name", "action", "outcome", "timestamp"):
        assert field in d
