import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from pacifor.main import app
from pacifor.core.kill_switch import kill_switch


@pytest.fixture(autouse=True)
async def reset_kill_switch():
    await kill_switch.release()
    yield
    await kill_switch.release()


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
