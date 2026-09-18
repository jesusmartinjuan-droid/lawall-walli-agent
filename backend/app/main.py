"""FastAPI application entry point."""

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    agent_images,
    auth,
    dashboard,
    documents,
    drafts,
    health,
    mailboxes,
    processing,
    prompts,
    users,
    web_sources,
)
from app.core.config import settings
from app.core.logging import configure_logging, get_logger

# Importing base_all registers every ORM model on the shared declarative
# registry before any request runs. Without this, SQLAlchemy can fail to
# resolve string-based relationship() targets (e.g. "EmailThread") whenever a
# request path only happens to import a subset of the model modules.
from app.db import base_all  # noqa: F401

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception path=%s error=%s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("app_starting name=%s environment=%s", settings.app_name, settings.environment)


app.include_router(health.router, prefix="/api")
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(mailboxes.router)
app.include_router(prompts.router)
app.include_router(documents.router)
app.include_router(agent_images.router)
app.include_router(drafts.router)
app.include_router(processing.router)
app.include_router(dashboard.router)
app.include_router(web_sources.router)
