import asyncio
import pytest
from httpx import AsyncClient


async def test_start_run_returns_201(client: AsyncClient):
    resp = await client.post(
        "/v1/runs",
        json={"initial_message": "Hello agent", "user_id": "user-1"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "running"
    assert "id" in data


async def test_get_run_not_found(client: AsyncClient):
    resp = await client.get("/v1/runs/nonexistent-id")
    assert resp.status_code == 404


async def test_list_runs(client: AsyncClient):
    await client.post("/v1/runs", json={"initial_message": "run 1"})
    await client.post("/v1/runs", json={"initial_message": "run 2"})
    resp = await client.get("/v1/runs")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2
