"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.routes import router as auth_router
from app.config import Settings, get_settings
from app.db.session import make_session_factory
from app.documents.routes import router as documents_router
from app.errors import register_error_handlers
from app.health.routes import router as health_router
from app.logging_config import configure_logging
from app.middleware import (
    REQUEST_ID_HEADER,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    UploadSizeLimitMiddleware,
)
from app.providers.factory import build_embedder, build_llm
from app.qa.routes import router as questions_router

API_DESCRIPTION = """
Upload documents, then ask questions about them. Answers are grounded in your documents and cite
the passages they come from.

Click **Authorize** and log in with your email and password to try the protected endpoints.
"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Builds the app. uvicorn runs it with `app.main:create_app --factory`."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="DocuMind API", version="0.1.0", description=API_DESCRIPTION)
    app.state.settings = settings
    app.state.session_factory = make_session_factory(settings)
    app.state.embedder = build_embedder(settings)
    app.state.llm = build_llm(settings)

    # Middleware added last runs first: the request ID is set before anything else happens.
    app.add_middleware(
        UploadSizeLimitMiddleware, path="/api/documents", max_file_bytes=settings.max_upload_bytes
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.app_env == "production")
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
            expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
        )
    app.add_middleware(RequestContextMiddleware)

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(questions_router)
    return app
