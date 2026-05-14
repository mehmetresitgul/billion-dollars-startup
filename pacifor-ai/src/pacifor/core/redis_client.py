from typing import Optional

import redis.asyncio as aioredis

from pacifor.core.config import settings

_client: Optional[aioredis.Redis] = None


async def get_redis() -> Optional[aioredis.Redis]:
    global _client
    if _client is None and settings.redis_url:
        try:
            _client = aioredis.from_url(settings.redis_url, decode_responses=True)
            await _client.ping()
        except Exception:
            _client = None
    return _client


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None
