import uuid
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.utils.logger import setup_logging
from app.api.auth.router import router as auth_router
from app.api.documents.router import router as documents_router
from app.api.questions.router import router as questions_router
from app.api.health.router import router as health_router

setup_logging()
logger = logging.getLogger("documind.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing DocuMind database and extensions...")
    try:
        init_db()
        logger.info("DocuMind initialized successfully.")
    except Exception as e:
        logger.warning(f"Could not connect to database on startup: {e}. Will retry on request.")
    yield
    logger.info("DocuMind API shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="DocuMind - Grounded AI Knowledge Assistant with citations and multi-tenant document RAG.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_and_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start_time = time.time()

    response = await call_next(request)

    process_time_ms = round((time.time() - start_time) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = str(process_time_ms)

    logger.info(
        f"HTTP {request.method} {request.url.path} status={response.status_code} latency={process_time_ms}ms",
        extra={"request_id": request_id}
    )
    return response



app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(documents_router, prefix=settings.API_V1_PREFIX)
app.include_router(questions_router, prefix=settings.API_V1_PREFIX)
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(health_router)


@app.get("/", tags=["Root"])
def root():
    return {
        "service": "DocuMind Knowledge Assistant API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }
