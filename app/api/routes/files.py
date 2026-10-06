"""HTTP endpoints for geospatial file upload, inspection, and measurement operations."""

from typing import Annotated
from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core.config import Settings, get_settings
from app.schemas.file import FileUploadResponse
from app.services.upload_service import UploadService

router = APIRouter(prefix="/files", tags=["files"])


def get_upload_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> UploadService:
    """Dependency provider for UploadService."""
    return UploadService(settings=settings)


@router.post(
    "",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post(
    "/",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a geospatial file",
    description=(
        "Upload a geospatial file (.kml or .zip containing Shapefile) for subsequent inspection "
        "and geometric measurements. Files are validated by extension and size, then stored securely."
    ),
)
async def upload_file(
    file: Annotated[
        UploadFile,
        File(description="Geospatial file (.kml or .zip archive) to upload"),
    ],
    service: Annotated[UploadService, Depends(get_upload_service)],
) -> FileUploadResponse:
    """Validate and store an uploaded geospatial file."""
    return await service.save_uploaded_file(file)
