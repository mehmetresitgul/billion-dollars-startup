"""
Unit tests for AuditEvent and AuditLogger.

No DB or Redis required — AuditLogger's in-memory buffer is used throughout.
DB path is tested via an AsyncMock session.
"""
import json
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pacifor.core.audit import AuditEvent, AuditLogger, _BUFFER_MAX
from pacifor.core.hashing import payload_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(**overrides) -> AuditEvent:
    defaults = dict(
        run_id="run-abc",
        node_name="planner",
        action="plan",
        outcome="success",
    )
    return AuditEvent.build(**{**defaults, **overrides})


@pytest.fixture(autouse=True)
def fresh_logger() -> AuditLogger:
    """Each test gets a private AuditLogger so the module singleton is untouched."""
    return AuditLogger()


# ---------------------------------------------------------------------------
# AuditEvent — construction
# ---------------------------------------------------------------------------

class TestAuditEventBuild:
    def test_required_fields_set(self) -> None:
        e = make_event()
        assert e.run_id == "run-abc"
        assert e.node_name == "planner"
        assert e.action == "plan"
        assert e.outcome == "success"

    def test_default_agent_id(self) -> None:
        e = make_event()
        assert e.agent_id == "default"

    def test_custom_agent_id(self) -> None:
        e = make_event(agent_id="researcher")
        assert e.agent_id == "researcher"

    def test_user_id_defaults_to_none(self) -> None:
        e = make_event()
        assert e.user_id is None

    def test_payload_is_hashed(self) -> None:
        data = {"plan": "step 1"}
        e = make_event(payload=data)
        assert e.payload_hash == payload_hash(data)

    def test_no_payload_gives_none_hash(self) -> None:
        e = make_event()
        assert e.payload_hash is None

    def test_payload_not_stored_raw(self) -> None:
        e = make_event(payload={"secret": "pii-data"})
        d = e.to_dict()
        assert "secret" not in str(d)
        assert "pii-data" not in str(d)

    def test_timestamp_is_iso_utc(self) -> None:
        before = datetime.now(UTC).isoformat()
        e = make_event()
        after = datetime.now(UTC).isoformat()
        assert before <= e.timestamp <= after

    def test_to_dict_contains_all_fields(self) -> None:
        e = make_event()
        d = e.to_dict()
        for key in ("run_id", "node_name", "action", "outcome", "agent_id", "timestamp"):
            assert key in d

    def test_to_dict_is_json_serialisable(self) -> None:
        e = make_event(payload={"x": 1})
        json.dumps(e.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# AuditEvent — immutability
# ---------------------------------------------------------------------------

class TestAuditEventImmutability:
    def test_frozen_raises_on_mutation(self) -> None:
        e = make_event()
        with pytest.raises((AttributeError, TypeError)):
            e.outcome = "tampered"  # type: ignore[misc]

    def test_two_events_with_same_payload_have_same_hash(self) -> None:
        data = {"k": "v"}
        e1 = make_event(payload=data)
        e2 = make_event(payload=data)
        assert e1.payload_hash == e2.payload_hash

    def test_different_payloads_give_different_hashes(self) -> None:
        e1 = make_event(payload={"a": 1})
        e2 = make_event(payload={"a": 2})
        assert e1.payload_hash != e2.payload_hash

    def test_key_order_does_not_affect_hash(self) -> None:
        e1 = make_event(payload={"x": 1, "y": 2})
        e2 = make_event(payload={"y": 2, "x": 1})
        assert e1.payload_hash == e2.payload_hash


# ---------------------------------------------------------------------------
# AuditLogger — buffer
# ---------------------------------------------------------------------------

class TestAuditLoggerBuffer:
    async def test_emit_adds_to_buffer(self, fresh_logger: AuditLogger) -> None:
        e = make_event()
        await fresh_logger.emit(e)
        assert len(fresh_logger) == 1

    async def test_emit_multiple_events(self, fresh_logger: AuditLogger) -> None:
        for i in range(5):
            await fresh_logger.emit(make_event(run_id=f"run-{i}"))
        assert len(fresh_logger) == 5

    async def test_buffer_respects_max_size(self) -> None:
        small = AuditLogger(buffer_size=3)
        for i in range(10):
            await small.emit(make_event(run_id=f"run-{i}"))
        assert len(small) == 3

    async def test_recent_returns_last_n(self, fresh_logger: AuditLogger) -> None:
        for i in range(10):
            await fresh_logger.emit(make_event(run_id=f"run-{i}"))
        last3 = fresh_logger.recent(3)
        assert len(last3) == 3
        assert [e.run_id for e in last3] == ["run-7", "run-8", "run-9"]

    async def test_recent_default_limit(self, fresh_logger: AuditLogger) -> None:
        for i in range(5):
            await fresh_logger.emit(make_event())
        assert len(fresh_logger.recent()) == 5

    async def test_clear_drains_buffer(self, fresh_logger: AuditLogger) -> None:
        await fresh_logger.emit(make_event())
        fresh_logger.clear()
        assert len(fresh_logger) == 0

    async def test_recent_after_clear_is_empty(self, fresh_logger: AuditLogger) -> None:
        await fresh_logger.emit(make_event())
        fresh_logger.clear()
        assert fresh_logger.recent() == []


# ---------------------------------------------------------------------------
# AuditLogger — filter
# ---------------------------------------------------------------------------

class TestAuditLoggerFilter:
    @pytest.fixture
    async def populated(self, fresh_logger: AuditLogger) -> AuditLogger:
        events = [
            AuditEvent.build(run_id="r1", node_name="planner", action="plan", outcome="success"),
            AuditEvent.build(run_id="r1", node_name="reviewer", action="hitl_interrupt", outcome="pending"),
            AuditEvent.build(run_id="r2", node_name="executor", action="execute", outcome="success"),
            AuditEvent.build(run_id="r2", node_name="planner", action="plan", outcome="failed"),
        ]
        for e in events:
            await fresh_logger.emit(e)
        return fresh_logger

    async def test_filter_by_run_id(self, populated: AuditLogger) -> None:
        results = populated.filter(run_id="r1")
        assert len(results) == 2
        assert all(e.run_id == "r1" for e in results)

    async def test_filter_by_node_name(self, populated: AuditLogger) -> None:
        results = populated.filter(node_name="planner")
        assert len(results) == 2

    async def test_filter_by_action(self, populated: AuditLogger) -> None:
        results = populated.filter(action="plan")
        assert len(results) == 2

    async def test_filter_by_outcome(self, populated: AuditLogger) -> None:
        results = populated.filter(outcome="success")
        assert len(results) == 2

    async def test_filter_combined(self, populated: AuditLogger) -> None:
        results = populated.filter(run_id="r2", outcome="success")
        assert len(results) == 1
        assert results[0].node_name == "executor"

    async def test_filter_no_match_returns_empty(self, populated: AuditLogger) -> None:
        assert populated.filter(run_id="does-not-exist") == []

    async def test_filter_none_args_returns_all(self, populated: AuditLogger) -> None:
        assert len(populated.filter()) == 4


# ---------------------------------------------------------------------------
# AuditLogger — logging sink
# ---------------------------------------------------------------------------

class TestAuditLoggerLogging:
    async def test_emit_writes_to_logger(self, fresh_logger: AuditLogger) -> None:
        with patch("pacifor.core.audit._logger") as mock_log:
            e = make_event()
            await fresh_logger.emit(e)
            mock_log.info.assert_called_once()
            logged_json = mock_log.info.call_args[0][0]
            data = json.loads(logged_json)
            assert data["run_id"] == "run-abc"
            assert data["action"] == "plan"

    async def test_logged_json_is_valid(self, fresh_logger: AuditLogger, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="pacifor.audit"):
            await fresh_logger.emit(make_event(payload={"x": 42}))
        assert caplog.records
        json.loads(caplog.records[0].message)  # must not raise


# ---------------------------------------------------------------------------
# AuditLogger — DB write
# ---------------------------------------------------------------------------

class TestAuditLoggerDB:
    # AuditEntry is imported lazily inside emit() to break the circular dep,
    # so the correct patch target is the models module, not pacifor.core.audit.
    _PATCH = "pacifor.models.audit_entry.AuditEntry"

    async def test_emit_with_db_adds_entry(self, fresh_logger: AuditLogger) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        with patch(self._PATCH, MagicMock()):
            await fresh_logger.emit(make_event(), db=db)
            db.add.assert_called_once()
            db.flush.assert_awaited_once()

    async def test_emit_without_db_skips_db(self, fresh_logger: AuditLogger) -> None:
        with patch(self._PATCH) as MockEntry:
            await fresh_logger.emit(make_event())
            MockEntry.assert_not_called()

    async def test_db_failure_does_not_propagate(self, fresh_logger: AuditLogger) -> None:
        db = AsyncMock()
        db.add = MagicMock(side_effect=Exception("db is down"))

        with patch(self._PATCH, MagicMock()):
            await fresh_logger.emit(make_event(), db=db)  # must not raise

    async def test_event_still_in_buffer_after_db_failure(self, fresh_logger: AuditLogger) -> None:
        db = AsyncMock()
        db.add = MagicMock(side_effect=Exception("db is down"))

        with patch(self._PATCH, MagicMock()):
            await fresh_logger.emit(make_event(), db=db)

        assert len(fresh_logger) == 1  # buffer write happened before DB attempt


# ---------------------------------------------------------------------------
# hashing.py helpers (used by AuditEvent.build)
# ---------------------------------------------------------------------------

class TestPayloadHash:
    def test_deterministic(self) -> None:
        data = {"foo": "bar", "num": 42}
        assert payload_hash(data) == payload_hash(data)

    def test_key_order_independent(self) -> None:
        assert payload_hash({"a": 1, "b": 2}) == payload_hash({"b": 2, "a": 1})

    def test_different_values_differ(self) -> None:
        assert payload_hash({"v": 1}) != payload_hash({"v": 2})

    def test_nested_dict(self) -> None:
        data = {"outer": {"inner": [1, 2, 3]}}
        assert payload_hash(data) == payload_hash(data)

    def test_returns_hex_string(self) -> None:
        result = payload_hash({})
        assert len(result) == 64
        int(result, 16)  # valid hex — must not raise

    def test_list_input(self) -> None:
        assert payload_hash([1, 2, 3]) == payload_hash([1, 2, 3])


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

def test_module_singleton_is_audit_logger_instance() -> None:
    from pacifor.core.audit import audit_logger
    assert isinstance(audit_logger, AuditLogger)
