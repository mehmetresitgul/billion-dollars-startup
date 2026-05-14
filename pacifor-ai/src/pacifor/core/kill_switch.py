"""
Kill switch with Redis primary backend and asyncio.Event fallback.

Engagement flow:
  1. engage(reason, ttl) — atomically writes to Redis (pipeline) and sets local Event
  2. Every LangGraph node calls check() via @guard — raises KillSwitchEngaged on hit
  3. release() clears both Redis keys and the local Event

Redis is authoritative when available.  If a Redis call fails mid-flight,
the local Event preserves the safety state so agents still halt.
"""
import asyncio
import logging
from typing import Optional

from redis.exceptions import RedisError

from pacifor.core.exceptions import KillSwitchEngaged

try:
    import redis.asyncio as aioredis
    _Redis = aioredis.Redis
except ImportError:  # pragma: no cover
    _Redis = None  # type: ignore[assignment]

_logger = logging.getLogger("pacifor.kill_switch")

_REDIS_FLAG_KEY = "pacifor:kill:global"
_REDIS_REASON_KEY = "pacifor:kill:reason"


class KillSwitch:
    """
    Thread-safe kill switch for async agent graphs.

    Attributes are kept private; callers interact only through
    engage / release / is_engaged / get_reason / check.
    """

    def __init__(self) -> None:
        self._local: asyncio.Event = asyncio.Event()
        self._local_reason: str = ""
        self._redis: Optional[_Redis] = None  # type: ignore[valid-type]

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def set_redis(self, client: Optional[object]) -> None:
        """Inject a connected aioredis.Redis client.  Pass None to force local mode."""
        self._redis = client  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    async def engage(self, reason: str = "", ttl: int = 3600) -> None:
        """
        Activate the kill switch.

        Sets the local Event first so that even a subsequent Redis error
        leaves agents in a halted state.
        """
        self._local.set()
        self._local_reason = reason

        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.set(_REDIS_FLAG_KEY, "1", ex=ttl)
                pipe.set(_REDIS_REASON_KEY, reason, ex=ttl)
                await pipe.execute()
            except RedisError:
                _logger.warning(
                    "Redis unavailable during engage — local state is set, agents will halt"
                )

    async def release(self) -> None:
        """
        Deactivate the kill switch.

        Clears local state first; Redis cleanup is best-effort.
        """
        self._local.clear()
        self._local_reason = ""

        if self._redis is not None:
            try:
                await self._redis.delete(_REDIS_FLAG_KEY, _REDIS_REASON_KEY)
            except RedisError:
                _logger.warning(
                    "Redis unavailable during release — local state is cleared"
                )

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    async def is_engaged(self) -> bool:
        """Return True if the kill switch is currently active."""
        if self._redis is not None:
            try:
                return bool(await self._redis.exists(_REDIS_FLAG_KEY))
            except RedisError:
                _logger.warning("Redis unavailable for is_engaged — using local state")
        return self._local.is_set()

    async def get_reason(self) -> str:
        """Return the reason string stored at engagement time, or empty string."""
        if self._redis is not None:
            try:
                reason = await self._redis.get(_REDIS_REASON_KEY)
                return reason if reason is not None else ""
            except RedisError:
                _logger.warning("Redis unavailable for get_reason — using local state")
        return self._local_reason

    async def check(self) -> None:
        """
        Raise KillSwitchEngaged if the switch is active.

        Call this as the first line of every LangGraph node (via @guard).
        """
        if await self.is_engaged():
            reason = await self.get_reason()
            raise KillSwitchEngaged(reason=reason or "Kill switch is engaged")


# Module-level singleton wired up in main.py lifespan.
kill_switch = KillSwitch()
