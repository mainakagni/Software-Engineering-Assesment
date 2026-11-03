from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import redis
from app.database import get_db
from app.config import settings
from app.api.health.schemas import HealthResponse

router = APIRouter(tags=["Health & Diagnostics"])


@router.get("/health", response_model=HealthResponse)
def check_health(db: Session = Depends(get_db)):
    services = {
        "database": "down",
        "vector_store": "down",
        "redis_queue": "down"
    }

    try:
        db.execute(text("SELECT 1;"))
        services["database"] = "up"
    except Exception:
        pass

    try:
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            result = db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector';")).scalar()
            services["vector_store"] = "up" if result == 1 else "not_installed"
        else:
            services["vector_store"] = "up (sqlite_test_mode)"
    except Exception:
        pass

    try:
        r = redis.from_url(settings.REDIS_URL, socket_timeout=1)
        if r.ping():
            services["redis_queue"] = "up"
    except Exception:
        pass

    overall_status = "healthy" if all("up" in v for v in services.values()) else "degraded"

    return {
        "status": overall_status,
        "services": services
    }
