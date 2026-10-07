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


tags_metadata = [
    {
        "name": "files",
        "description": "Geospatial vector file operations: multipart upload, parsing, measurement retrieval, and record deletion.",
    },
    {
        "name": "health",
        "description": "Health check and service liveness probe.",
    },
]

app = FastAPI(
    title="AEREO Geospatial File Measurement API",
    version=settings.VERSION,
    description=(
        "Production backend API for parsing geospatial vector files (.kml and .zip containing Shapefiles), "
        "managing CRS transformations to UTM projections, and calculating planar metric measurements "
        "(polygon area in m² and linestring length in m)."
    ),
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# Register API routers
app.include_router(files.router, prefix="/api")


@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Verify API service availability.",
)
async def health_check() -> dict[str, str]:
    """Health check endpoint returning application status."""
    return {"status": "ok"}
