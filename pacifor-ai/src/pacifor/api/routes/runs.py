import uuid
from fastapi import APIRouter, HTTPException
from pacifor.api.schemas.runs import RunCreate, RunResponse
from pacifor.services.run_service import run_service

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunResponse, status_code=201)
async def start_run(body: RunCreate):
    run_id = str(uuid.uuid4())
    return await run_service.start(run_id=run_id, body=body)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    run = await run_service.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return run


@router.get("", response_model=list[RunResponse])
async def list_runs(limit: int = 50):
    return await run_service.list_all(limit=limit)
