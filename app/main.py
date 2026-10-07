"""Application entry point and FastAPI configuration."""

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes import files
from app.core.config import get_settings
from app.storage.database import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context initializing storage tables on startup."""
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Backend API for geospatial file parsing and geometric measurements.",
    lifespan=lifespan,
)

# Register API routers
app.include_router(files.router, prefix="/api")


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint returning application status."""
    return {"status": "ok"}
