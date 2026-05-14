from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pacifor.core.exceptions import KillSwitchEngaged, RunNotFound


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(KillSwitchEngaged)
    async def kill_switch_handler(request: Request, exc: KillSwitchEngaged):
        return JSONResponse(
            status_code=503,
            content={"error": "kill_switch_engaged", "detail": exc.reason},
        )

    @app.exception_handler(RunNotFound)
    async def run_not_found_handler(request: Request, exc: RunNotFound):
        return JSONResponse(
            status_code=404,
            content={"error": "run_not_found", "detail": str(exc)},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={"error": "bad_request", "detail": str(exc)},
        )
