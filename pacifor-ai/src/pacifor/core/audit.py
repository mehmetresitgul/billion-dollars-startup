"""
Audit logger: structured JSON to stdout + optional async DB write.

Design decisions:
  - AuditEvent is a frozen dataclass — immutable after construction.
  - Raw payloads are never stored; only SHA-256 hashes (PII-light audit trail).
  - AuditLogger.emit() is the single entry point; all nodes, HITL events,
    and kill-switch transitions route through it.
  - An in-memory deque (default 500 events) enables test assertions and
    lightweight querying without a database round-trip.
  - DB writes are best-effort: failures are logged but do not propagate,
    so an unhealthy DB never halts the agent graph.
"""
import json
import logging
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

from pacifor.core.hashing import payload_hash

_logger = logging.getLogger("pacifor.audit")

_BUFFER_MAX = 500


@dataclass(frozen=True)
class AuditEvent:
    """
    Immutable record of one agent action or system event.

    Build via AuditEvent.build() — never construct directly with a raw
    payload; use the `payload` kwarg so hashing happens in one place.
    """

    run_id: str
    node_name: str
    action: str
    outcome: str
    agent_id: str = "default"
    user_id: Optional[str] = None
    payload_hash: Optional[str] = field(default=None, repr=False)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @classmethod
    def build(
        cls,
        *,
        run_id: str,
        node_name: str,
        action: str,
        outcome: str,
        agent_id: str = "default",
        user_id: Optional[str] = None,
        payload: Optional[Any] = None,
    ) -> "AuditEvent":
        """
        Construct an AuditEvent, hashing `payload` if provided.

        The raw payload is intentionally discarded here; only the hash
        travels further in the audit trail.
        """
        phash = payload_hash(payload) if payload is not None else None
        return cls(
            run_id=run_id,
            node_name=node_name,
            action=action,
            outcome=outcome,
            agent_id=agent_id,
            user_id=user_id,
            payload_hash=phash,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """
    Single-instance audit sink.

    emit() writes to:
      1. The in-memory ring buffer (always)
      2. stdlib logging at INFO level as JSON (always)
      3. The async DB session (when provided)

    The buffer supports test assertions via filter() and clear().
    """

    def __init__(self, buffer_size: int = _BUFFER_MAX) -> None:
        self._buffer: deque[AuditEvent] = deque(maxlen=buffer_size)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def emit(self, event: AuditEvent, db: Any = None) -> None:
        """
        Record one audit event.

        `db` is an optional SQLAlchemy AsyncSession.  If the DB write fails,
        the error is logged and swallowed — the event is still in the buffer.
        """
        self._buffer.append(event)
        _logger.info(json.dumps(event.to_dict()))

        if db is not None:
            try:
                from pacifor.models.audit_entry import AuditEntry  # lazy import avoids circular dep
                db.add(AuditEntry(**event.to_dict()))
                await db.flush()
            except Exception:
                _logger.exception(
                    "DB persist failed for audit event run_id=%s action=%s",
                    event.run_id,
                    event.action,
                )

    # ------------------------------------------------------------------
    # Read (buffer)
    # ------------------------------------------------------------------

    def recent(self, limit: int = 100) -> list[AuditEvent]:
        """Return the last `limit` events from the buffer (oldest-first)."""
        events = list(self._buffer)
        return events[-limit:]

    def filter(
        self,
        *,
        run_id: Optional[str] = None,
        node_name: Optional[str] = None,
        action: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> list[AuditEvent]:
        """
        Filter the in-memory buffer.

        Useful for test assertions: `audit_logger.filter(run_id="x", action="plan")`.
        Returns events in insertion order.
        """
        results: list[AuditEvent] = list(self._buffer)
        if run_id is not None:
            results = [e for e in results if e.run_id == run_id]
        if node_name is not None:
            results = [e for e in results if e.node_name == node_name]
        if action is not None:
            results = [e for e in results if e.action == action]
        if outcome is not None:
            results = [e for e in results if e.outcome == outcome]
        return results

    def clear(self) -> None:
        """Drain the buffer.  Call in test teardown to prevent cross-test pollution."""
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)


# Module-level singleton.
audit_logger = AuditLogger()
