"""Application entry point and FastAPI configuration."""

from fastapi import FastAPI

from app.api.routes import files
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Backend API for geospatial file parsing and geometric measurements.",
)

# Register API routers
app.include_router(files.router)


@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint returning application status."""
    return {"status": "ok"}
