"""
Kill-switch guard applied to every LangGraph node.
Usage: decorate node functions with @guard.
"""
from functools import wraps
from typing import Any

from pacifor.core.kill_switch import kill_switch


def guard(fn):
    @wraps(fn)
    async def wrapper(state: dict, config: Any = None, **kwargs):
        await kill_switch.check()
        return await fn(state, config=config, **kwargs)

    return wrapper
