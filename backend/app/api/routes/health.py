from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    """Liveness + live DB-connectivity probe.

    Returns 200 ``{"status":"ok","db":"ok"}`` when the database is reachable, and
    503 ``{"status":"error","db":"error"}`` when it is not — so the Docker
    healthcheck (``curl -f``) actually fails when the DB is down rather than
    reporting a self-contradictory healthy-but-db-error 200.
    """
    db_ok = await request.app.state.context_manager.health_check()
    body = {
        "status": "ok" if db_ok else "error",
        "db": "ok" if db_ok else "error",
    }
    if not db_ok:
        return JSONResponse(status_code=503, content=body)
    return body
