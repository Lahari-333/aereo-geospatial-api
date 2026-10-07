"""Application entry point and FastAPI configuration."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
        "description": "Geospatial vector file operations: multipart upload, batch processing, measurement retrieval, and RFC 7946 GeoJSON export.",
    },
    {
        "name": "viewer",
        "description": "Interactive Leaflet geospatial visualization dashboard.",
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
        "managing CRS transformations to UTM projections, calculating planar metric measurements "
        "(polygon area in m² and linestring length in m), batch processing, and RFC 7946 GeoJSON export."
    ),
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# Mount static viewer assets
if settings.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

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


@app.get(
    "/",
    tags=["viewer"],
    summary="Interactive Geospatial Viewer",
    description="Serves the AEREO interactive vector map dashboard.",
)
@app.get(
    "/viewer",
    tags=["viewer"],
    summary="Interactive Geospatial Viewer",
    description="Serves the AEREO interactive vector map dashboard.",
)
@app.get(
    "/viewer/",
    include_in_schema=False,
)
async def serve_viewer():
    """Serve the interactive Leaflet geospatial web viewer."""
    index_file = settings.STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "AEREO Geospatial API is running. Viewer index.html not found."}
