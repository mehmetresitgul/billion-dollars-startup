from typing import Optional

from pacifor.core.audit import AuditEvent, audit_logger
from pacifor.core.kill_switch import kill_switch


class KillService:
    async def engage(self, reason: str = "", triggered_by: Optional[str] = None) -> None:
        await kill_switch.engage(reason=reason)
        await audit_logger.emit(
            AuditEvent.build(
                run_id="system",
                node_name="kill_switch",
                action="engage",
                outcome="success",
                user_id=triggered_by,
                payload={"reason": reason},
            )
        )

    async def release(self, triggered_by: Optional[str] = None) -> None:
        await kill_switch.release()
        await audit_logger.emit(
            AuditEvent.build(
                run_id="system",
                node_name="kill_switch",
                action="release",
                outcome="success",
                user_id=triggered_by,
            )
        )

    async def is_engaged(self) -> bool:
        return await kill_switch.is_engaged()


kill_service = KillService()
