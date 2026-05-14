from fastapi import APIRouter
from pacifor.api.routes import runs, hitl, kill_switch, audit

router = APIRouter(prefix="/v1")
router.include_router(runs.router)
router.include_router(hitl.router)
router.include_router(kill_switch.router)
router.include_router(audit.router)
