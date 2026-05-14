"""
Kill-switch guard for LangGraph nodes.

`guard` is the default decorator (uses the module-level KillSwitch singleton).
`make_guard(ks)` returns a decorator bound to a specific KillSwitch instance —
use this in tests so you don't touch the global singleton.

On kill, the guard:
  1. Emits an audit event (action="kill_switch_halt") so the halt is always recorded.
  2. Re-raises KillSwitchEngaged so LangGraph propagates it to the run_service.
"""
from functools import wraps
from typing import Any, Callable

from pacifor.core.audit import AuditEvent, AuditLogger, audit_logger as _global_audit_logger
from pacifor.core.exceptions import KillSwitchEngaged
from pacifor.core.kill_switch import KillSwitch, kill_switch as _global_kill_switch


def make_guard(ks: KillSwitch, logger: AuditLogger = _global_audit_logger) -> Callable:
    """
    Return a @guard decorator bound to the given KillSwitch (and optional AuditLogger).

    Example (production):
        guard = make_guard(kill_switch)

    Example (tests):
        guard = make_guard(KillSwitch(), AuditLogger())
    """
    def guard(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(state: dict, config: Any = None, **kwargs) -> dict:
            try:
                await ks.check()
            except KillSwitchEngaged as exc:
                await logger.emit(
                    AuditEvent.build(
                        run_id=state.get("run_id", "unknown"),
                        node_name=fn.__name__,
                        action="kill_switch_halt",
                        outcome="killed",
                        agent_id=state.get("agent_id", "default"),
                        user_id=state.get("user_id"),
                        payload={"reason": exc.reason},
                    )
                )
                raise
            return await fn(state, config=config, **kwargs)
        return wrapper
    return guard


# Default decorator — all production node files use this.
guard = make_guard(_global_kill_switch)
