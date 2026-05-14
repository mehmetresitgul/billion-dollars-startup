"""
Audit logger: emits structured JSON events to stdout and (optionally) DB.
Every node, HITL transition, and kill event routes through AuditLogger.emit().
Payloads are hashed — raw data stays out of the audit table to keep it PII-light.
"""
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Any, Optional

from pacifor.core.hashing import payload_hash

_logger = logging.getLogger("pacifor.audit")


@dataclass
class AuditEvent:
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

    def to_dict(self) -> dict:
        return asdict(self)


class AuditLogger:
    async def emit(self, event: AuditEvent, db=None) -> None:
        record = event.to_dict()
        _logger.info(json.dumps(record))

        if db is not None:
            from pacifor.models.audit_entry import AuditEntry
            db.add(AuditEntry(**record))
            await db.flush()


audit_logger = AuditLogger()
