"""HTTP endpoints for geospatial file upload, inspection, and measurement operations."""

from fastapi import APIRouter

router = APIRouter(prefix="/files", tags=["files"])

# Route handlers for geospatial file upload, inspection, and measurement operations
# will be registered here in subsequent stages.
