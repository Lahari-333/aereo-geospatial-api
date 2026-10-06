"""HTTP endpoints for geospatial file upload, inspection, and measurement operations."""

from typing import Annotated
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import Settings, get_settings
from app.schemas.file import FileUploadResponse
from app.services.file_processor import GeospatialFileProcessor, GeospatialProcessingError
from app.services.upload_service import UploadService

router = APIRouter(prefix="/files", tags=["files"])


def get_upload_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> UploadService:
    """Dependency provider for UploadService."""
    return UploadService(settings=settings)


def get_file_processor(
    settings: Annotated[Settings, Depends(get_settings)],
) -> GeospatialFileProcessor:
    """Dependency provider for GeospatialFileProcessor."""
    return GeospatialFileProcessor(settings=settings)


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
    summary="Upload and process a geospatial file",
    description=(
        "Upload a geospatial file (.kml or .zip containing Shapefile) for subsequent inspection "
        "and geometric measurements. Files are securely validated and stored, then parsed to extract "
        "features, geometries, and CRS metadata."
    ),
)
async def upload_file(
    file: Annotated[
        UploadFile,
        File(description="Geospatial file (.kml or .zip archive) to upload"),
    ],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    processor: Annotated[GeospatialFileProcessor, Depends(get_file_processor)],
) -> FileUploadResponse:
    """Validate, store, and parse an uploaded geospatial file."""
    upload_record = await upload_service.save_uploaded_file(file)

    stored_path = upload_service.upload_dir / upload_record.stored_filename

    try:
        processing_result = processor.process_file(
            file_path=stored_path,
            file_type=upload_record.file_type,
            file_id=upload_record.id,
        )
    except GeospatialProcessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return FileUploadResponse(
        id=upload_record.id,
        filename=upload_record.filename,
        stored_filename=upload_record.stored_filename,
        file_type=upload_record.file_type,
        size_bytes=upload_record.size_bytes,
        status="COMPLETED",
        feature_count=processing_result.feature_count,
        geometry_types=processing_result.geometry_types,
        crs=processing_result.crs,
    )
