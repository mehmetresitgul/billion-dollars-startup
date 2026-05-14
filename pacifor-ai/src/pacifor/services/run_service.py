"""
In-memory run store for MVP — replace dict with DB queries when ready.
Runs graph in a background asyncio task so the API responds immediately.
"""
import asyncio
from datetime import datetime, UTC
from typing import Optional

from pacifor.agents.graph import graph
from pacifor.api.schemas.runs import RunCreate
from pacifor.core.exceptions import KillSwitchEngaged, HITLRejected

_runs: dict[str, dict] = {}


class RunService:
    async def start(self, run_id: str, body: RunCreate) -> dict:
        now = datetime.now(UTC)
        record = {
            "id": run_id,
            "agent_id": body.agent_id,
            "user_id": body.user_id,
            "status": "running",
            "created_at": now,
            "result": None,
            "error": None,
        }
        _runs[run_id] = record

        initial_state = {
            "run_id": run_id,
            "agent_id": body.agent_id,
            "user_id": body.user_id or "anonymous",
            "messages": [{"role": "user", "content": body.initial_message}],
            "plan": None,
            "result": None,
            "hitl_approved": False,
        }
        asyncio.create_task(self._execute(run_id, initial_state))
        return record

    async def _execute(self, run_id: str, state: dict) -> None:
        config = {"configurable": {"thread_id": run_id}}
        try:
            result = await graph.ainvoke(state, config=config)
            _runs[run_id]["status"] = "completed"
            _runs[run_id]["result"] = result.get("result")
        except KillSwitchEngaged as exc:
            _runs[run_id]["status"] = "killed"
            _runs[run_id]["error"] = exc.reason
        except HITLRejected as exc:
            _runs[run_id]["status"] = "rejected"
            _runs[run_id]["error"] = str(exc)
        except Exception as exc:
            _runs[run_id]["status"] = "failed"
            _runs[run_id]["error"] = str(exc)

    async def resume(self, run_id: str, decision: dict) -> None:
        from langgraph.types import Command
        config = {"configurable": {"thread_id": run_id}}
        asyncio.create_task(
            graph.ainvoke(Command(resume=decision), config=config)
        )

    async def get(self, run_id: str) -> Optional[dict]:
        return _runs.get(run_id)

    async def list_all(self, limit: int = 50) -> list[dict]:
        runs = list(_runs.values())
        return runs[-limit:]


run_service = RunService()
