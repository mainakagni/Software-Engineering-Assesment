from functools import partial
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.dependencies import SettingsDep
from app.envelope import Envelope, ok
from app.health import checks

router = APIRouter(tags=["health"])


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"


class ComponentHealth(BaseModel):
    status: checks.Status
    details: dict[str, Any]


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, ComponentHealth]


@router.get("/health/live", response_model=Envelope[Liveness])
def liveness() -> Envelope[Liveness]:
    """The process is up. Used by the hosting platform; touches no dependencies."""
    return ok(Liveness())


@router.get(
    "/health",
    response_model=Envelope[HealthReport],
    responses={
        503: {"model": Envelope[HealthReport], "description": "At least one dependency is down"}
    },
)
def health(request: Request, response: Response, settings: SettingsDep) -> Envelope[HealthReport]:
    """Reports whether the database, the vector store, the job queue and the worker are working."""
    session_factory = request.app.state.session_factory
    worker_check = partial(
        checks.check_worker, stale_after_seconds=settings.worker_stale_after_seconds
    )
    results = {
        "database": checks.run_check("database", session_factory, checks.check_database),
        "vector_store": checks.run_check(
            "vector_store", session_factory, checks.check_vector_store
        ),
        "queue": checks.run_check("queue", session_factory, checks.check_queue),
        "worker": checks.run_check("worker", session_factory, worker_check),
    }
    healthy = all(result.status == "ok" for result in results.values())
    if not healthy:
        response.status_code = 503
    report = HealthReport(
        status="ok" if healthy else "degraded",
        checks={
            name: ComponentHealth(status=r.status, details=r.details) for name, r in results.items()
        },
    )
    return ok(report)


# HEAD too: uptime monitors often use it, and a 405 would read as "down". Kept out of the API docs.
for path, endpoint in (("/health/live", liveness), ("/health", health)):
    router.add_api_route(path, endpoint, methods=["HEAD"], include_in_schema=False)
