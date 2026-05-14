from fastapi import APIRouter
from pydantic import BaseModel
from pacifor.services.kill_service import kill_service

router = APIRouter(prefix="/kill", tags=["admin"])


class KillRequest(BaseModel):
    reason: str = ""
    triggered_by: str | None = None


@router.post("", summary="Engage kill switch — halts all running agents")
async def engage(body: KillRequest):
    await kill_service.engage(reason=body.reason, triggered_by=body.triggered_by)
    return {"status": "engaged", "reason": body.reason}


@router.post("/release", summary="Release kill switch — resumes normal operation")
async def release(body: KillRequest):
    await kill_service.release(triggered_by=body.triggered_by)
    return {"status": "released"}


@router.get("/status")
async def status():
    engaged = await kill_service.is_engaged()
    return {"engaged": engaged}
