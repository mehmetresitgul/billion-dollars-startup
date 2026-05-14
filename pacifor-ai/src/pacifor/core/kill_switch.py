"""
Kill switch with Redis primary backend and in-memory fallback.
Every LangGraph node calls `await kill_switch.check()` as its first line.
Raising KillSwitchEngaged bubbles to the graph runner which marks the run as "killed".
"""
import asyncio
from typing import Optional

import redis.asyncio as aioredis

from pacifor.core.exceptions import KillSwitchEngaged

REDIS_KEY = "pacifor:kill:global"


class KillSwitch:
    def __init__(self) -> None:
        self._local = asyncio.Event()
        self._redis: Optional[aioredis.Redis] = None

    def set_redis(self, client: Optional[aioredis.Redis]) -> None:
        self._redis = client

    async def engage(self, reason: str = "", ttl: int = 3600) -> None:
        self._local.set()
        if self._redis:
            await self._redis.set(REDIS_KEY, reason or "engaged", ex=ttl)

    async def release(self) -> None:
        self._local.clear()
        if self._redis:
            await self._redis.delete(REDIS_KEY)

    async def is_engaged(self) -> bool:
        if self._redis:
            val = await self._redis.get(REDIS_KEY)
            return val is not None
        return self._local.is_set()

    async def check(self) -> None:
        if await self.is_engaged():
            raise KillSwitchEngaged()


kill_switch = KillSwitch()
