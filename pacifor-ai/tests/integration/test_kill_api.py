import pytest
from httpx import AsyncClient


async def test_kill_switch_status_default_off(client: AsyncClient):
    resp = await client.get("/v1/kill/status")
    assert resp.status_code == 200
    assert resp.json()["engaged"] is False


async def test_engage_and_release(client: AsyncClient):
    resp = await client.post("/v1/kill", json={"reason": "test engage"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "engaged"

    resp = await client.get("/v1/kill/status")
    assert resp.json()["engaged"] is True

    resp = await client.post("/v1/kill/release", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "released"

    resp = await client.get("/v1/kill/status")
    assert resp.json()["engaged"] is False


async def test_health_reflects_kill_switch(client: AsyncClient):
    await client.post("/v1/kill", json={"reason": "health test"})
    resp = await client.get("/health")
    assert resp.json()["kill_switch"] == "engaged"
