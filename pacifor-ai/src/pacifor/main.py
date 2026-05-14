import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pacifor.api.errors import register_error_handlers
from pacifor.api.routes import router
from pacifor.core.config import settings
from pacifor.core.db import init_db
from pacifor.core.kill_switch import kill_switch
from pacifor.core.redis_client import close_redis, get_redis

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    redis = await get_redis()
    kill_switch.set_redis(redis)
    yield
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

register_error_handlers(app)
app.include_router(router)


@app.get("/health", tags=["system"])
async def health():
    engaged = await kill_switch.is_engaged()
    return {"status": "ok", "kill_switch": "engaged" if engaged else "off"}
