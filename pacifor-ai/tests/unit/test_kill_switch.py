"""
Unit tests for KillSwitch.

All tests use a fresh KillSwitch() instance (not the module singleton)
to guarantee isolation.  Redis is mocked via AsyncMock so no real server
is needed.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import RedisError

from pacifor.core.exceptions import KillSwitchEngaged
from pacifor.core.kill_switch import KillSwitch, _REDIS_FLAG_KEY, _REDIS_REASON_KEY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_redis(*, exists: bool = False, reason: str = "") -> AsyncMock:
    """Build a minimal aioredis mock."""
    client = AsyncMock()
    client.exists = AsyncMock(return_value=1 if exists else 0)
    client.get = AsyncMock(return_value=reason if reason else None)
    client.delete = AsyncMock(return_value=1)

    pipe = AsyncMock()
    pipe.set = MagicMock(return_value=pipe)   # pipeline().set() is sync in redis-py
    pipe.execute = AsyncMock(return_value=[True, True])
    client.pipeline = MagicMock(return_value=pipe)

    return client


# ---------------------------------------------------------------------------
# In-memory mode (no Redis)
# ---------------------------------------------------------------------------

class TestInMemoryMode:
    @pytest.fixture
    def ks(self) -> KillSwitch:
        return KillSwitch()  # no Redis attached

    async def test_initially_not_engaged(self, ks: KillSwitch) -> None:
        assert not await ks.is_engaged()

    async def test_engage_sets_flag(self, ks: KillSwitch) -> None:
        await ks.engage(reason="test")
        assert await ks.is_engaged()

    async def test_release_clears_flag(self, ks: KillSwitch) -> None:
        await ks.engage()
        await ks.release()
        assert not await ks.is_engaged()

    async def test_check_raises_when_engaged(self, ks: KillSwitch) -> None:
        await ks.engage(reason="emergency stop")
        with pytest.raises(KillSwitchEngaged) as exc_info:
            await ks.check()
        assert "emergency stop" in str(exc_info.value)

    async def test_check_passes_when_not_engaged(self, ks: KillSwitch) -> None:
        await ks.check()  # must not raise

    async def test_check_passes_after_release(self, ks: KillSwitch) -> None:
        await ks.engage()
        await ks.release()
        await ks.check()  # must not raise

    async def test_get_reason_empty_before_engage(self, ks: KillSwitch) -> None:
        assert await ks.get_reason() == ""

    async def test_get_reason_returns_stored_reason(self, ks: KillSwitch) -> None:
        await ks.engage(reason="quota exceeded")
        assert await ks.get_reason() == "quota exceeded"

    async def test_get_reason_clears_on_release(self, ks: KillSwitch) -> None:
        await ks.engage(reason="test")
        await ks.release()
        assert await ks.get_reason() == ""

    async def test_reengage_updates_reason(self, ks: KillSwitch) -> None:
        await ks.engage(reason="first")
        await ks.engage(reason="second")
        assert await ks.get_reason() == "second"

    async def test_release_without_prior_engage_is_safe(self, ks: KillSwitch) -> None:
        await ks.release()  # must not raise
        assert not await ks.is_engaged()

    async def test_default_reason_on_exception(self, ks: KillSwitch) -> None:
        await ks.engage()  # empty reason
        with pytest.raises(KillSwitchEngaged) as exc_info:
            await ks.check()
        assert exc_info.value.reason != ""  # falls back to default string


# ---------------------------------------------------------------------------
# Redis mode
# ---------------------------------------------------------------------------

class TestRedisMode:
    @pytest.fixture
    def ks(self) -> KillSwitch:
        instance = KillSwitch()
        instance.set_redis(make_redis())
        return instance

    async def test_engage_writes_to_redis(self) -> None:
        redis = make_redis()
        ks = KillSwitch()
        ks.set_redis(redis)

        await ks.engage(reason="redis-reason", ttl=120)

        pipe = redis.pipeline.return_value
        pipe.set.assert_any_call(_REDIS_FLAG_KEY, "1", ex=120)
        pipe.set.assert_any_call(_REDIS_REASON_KEY, "redis-reason", ex=120)
        pipe.execute.assert_awaited_once()

    async def test_is_engaged_reads_redis(self) -> None:
        redis = make_redis(exists=True)
        ks = KillSwitch()
        ks.set_redis(redis)

        assert await ks.is_engaged()
        redis.exists.assert_awaited_with(_REDIS_FLAG_KEY)

    async def test_is_not_engaged_when_redis_key_absent(self) -> None:
        redis = make_redis(exists=False)
        ks = KillSwitch()
        ks.set_redis(redis)

        assert not await ks.is_engaged()

    async def test_get_reason_reads_redis(self) -> None:
        redis = make_redis(reason="from-redis")
        ks = KillSwitch()
        ks.set_redis(redis)

        assert await ks.get_reason() == "from-redis"

    async def test_get_reason_returns_empty_when_key_missing(self) -> None:
        redis = make_redis(reason="")
        ks = KillSwitch()
        ks.set_redis(redis)

        assert await ks.get_reason() == ""

    async def test_release_deletes_redis_keys(self) -> None:
        redis = make_redis()
        ks = KillSwitch()
        ks.set_redis(redis)

        await ks.release()
        redis.delete.assert_awaited_with(_REDIS_FLAG_KEY, _REDIS_REASON_KEY)

    async def test_check_raises_when_redis_engaged(self) -> None:
        redis = make_redis(exists=True, reason="redis halt")
        ks = KillSwitch()
        ks.set_redis(redis)

        with pytest.raises(KillSwitchEngaged) as exc_info:
            await ks.check()
        assert "redis halt" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Redis failure fallback
# ---------------------------------------------------------------------------

class TestRedisFallback:
    async def test_engage_redis_error_still_sets_local(self) -> None:
        redis = make_redis()
        redis.pipeline.return_value.execute = AsyncMock(side_effect=RedisError("down"))
        ks = KillSwitch()
        ks.set_redis(redis)

        await ks.engage(reason="still works")

        # local state must be set despite Redis failure
        ks.set_redis(None)
        assert await ks.is_engaged()

    async def test_release_redis_error_still_clears_local(self) -> None:
        redis = make_redis()
        redis.delete = AsyncMock(side_effect=RedisError("down"))
        ks = KillSwitch()
        ks.set_redis(redis)

        await ks.engage()
        ks._redis = redis  # keep redis attached so delete is attempted
        await ks.release()

        ks.set_redis(None)
        assert not await ks.is_engaged()

    async def test_is_engaged_redis_error_falls_back_to_local(self) -> None:
        redis = make_redis()
        redis.exists = AsyncMock(side_effect=RedisError("down"))
        ks = KillSwitch()
        ks._local.set()  # manually set local flag
        ks.set_redis(redis)

        assert await ks.is_engaged()  # falls back to local=True

    async def test_is_engaged_redis_error_local_false(self) -> None:
        redis = make_redis()
        redis.exists = AsyncMock(side_effect=RedisError("down"))
        ks = KillSwitch()
        ks.set_redis(redis)

        assert not await ks.is_engaged()  # falls back to local=False

    async def test_get_reason_redis_error_falls_back_to_local(self) -> None:
        redis = make_redis()
        redis.get = AsyncMock(side_effect=RedisError("down"))
        ks = KillSwitch()
        ks._local_reason = "local-reason"
        ks.set_redis(redis)

        assert await ks.get_reason() == "local-reason"

    async def test_check_redis_error_halts_on_local_state(self) -> None:
        redis = make_redis()
        redis.exists = AsyncMock(side_effect=RedisError("down"))
        ks = KillSwitch()
        ks._local.set()
        ks.set_redis(redis)

        with pytest.raises(KillSwitchEngaged):
            await ks.check()


# ---------------------------------------------------------------------------
# Singleton smoke test
# ---------------------------------------------------------------------------

async def test_module_singleton_is_kill_switch_instance() -> None:
    from pacifor.core.kill_switch import kill_switch
    assert isinstance(kill_switch, KillSwitch)
