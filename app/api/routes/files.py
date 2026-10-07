"""HTTP endpoints for geospatial file upload, inspection, and measurement operations."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.file_record import FileRecord, MeasurementRecord
from app.schemas.file import (
    FileDetailResponse,
    FileListResponse,
    FileMeasurementsResponse,
    FileUploadResponse,
)
from app.services.crs_handler import MissingCRSError
from app.services.file_processor import GeospatialFileProcessor, GeospatialProcessingError
from app.services.measurement import MeasurementService
from app.services.upload_service import UploadService
from app.storage.database import get_db

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


def get_measurement_service() -> MeasurementService:
    """Dependency provider for MeasurementService."""
    return MeasurementService()


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
    summary="Upload, parse, and measure a geospatial file",
    description=(
        "Upload a geospatial file (.kml or .zip containing Shapefile). The file is securely stored, "
        "parsed with GeoPandas, metric measurements (polygon area, linestring length) are calculated, "
        "and metadata is persisted for querying."
    ),
)
async def upload_file(
    file: Annotated[
        UploadFile,
        File(description="Geospatial file (.kml or .zip archive) to upload"),
    ],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    processor: Annotated[GeospatialFileProcessor, Depends(get_file_processor)],
    measurer: Annotated[MeasurementService, Depends(get_measurement_service)],
    db: Annotated[Session, Depends(get_db)],
) -> FileUploadResponse:
    """Validate, store, parse, measure, and persist an uploaded geospatial file."""
    upload_record = await upload_service.save_uploaded_file(file)

    stored_path = upload_service.upload_dir / upload_record.stored_filename

    try:
        try:
            processing_result = processor.process_file(
                file_path=stored_path,
                file_type=upload_record.file_type,
                file_id=upload_record.id,
            )
        except GeospatialProcessingError as exc:
            if stored_path.exists():
                stored_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        # Calculate metric measurements if dataset has a valid CRS and geometries
        measurement_crs_str: str | None = None
        calculated_measurements = []

        if processing_result.gdf is not None and not processing_result.has_missing_crs:
            try:
                calculated_measurements = measurer.calculate_measurements(processing_result.gdf)
                # Find the projected measurement CRS used for area/length
                for m in calculated_measurements:
                    if m.measurement_crs:
                        measurement_crs_str = m.measurement_crs
                        break
            except MissingCRSError:
                pass

        # Persist file record and feature measurements
        file_entity = FileRecord(
            id=str(upload_record.id),
            filename=upload_record.filename,
            stored_filename=upload_record.stored_filename,
            file_type=upload_record.file_type,
            size_bytes=upload_record.size_bytes,
            status="COMPLETED",
            feature_count=processing_result.feature_count,
            crs=processing_result.crs,
            measurement_crs=measurement_crs_str,
        )
        file_entity.geometry_types = processing_result.geometry_types

        # Add measurement records
        for m in calculated_measurements:
            meas_entity = MeasurementRecord(
                feature_id=m.feature_id,
                geometry_type=m.geometry_type,
                measurement_type=m.measurement_type,
                value=m.value,
                unit=m.unit,
                source_crs=m.source_crs,
                measurement_crs=m.measurement_crs,
                notes=m.notes,
            )
            file_entity.measurements.append(meas_entity)

        db.add(file_entity)
        db.commit()
        db.refresh(file_entity)

    except Exception:
        db.rollback()
        if stored_path.exists():
            stored_path.unlink()
        raise

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


@router.get(
    "",
    response_model=FileListResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.get(
    "/",
    response_model=FileListResponse,
    status_code=status.HTTP_200_OK,
    summary="List stored geospatial files",
    description="Retrieve a list of all stored geospatial files and their processing summary.",
)
def list_files(
    db: Annotated[Session, Depends(get_db)],
) -> FileListResponse:
    """Retrieve all stored geospatial file records."""
    records = db.scalars(select(FileRecord).order_by(FileRecord.created_at.desc())).all()
    return FileListResponse(
        total=len(records),
        files=[
            FileDetailResponse(
                id=UUID(r.id),
                filename=r.filename,
                stored_filename=r.stored_filename,
                file_type=r.file_type,
                size_bytes=r.size_bytes,
                status=r.status,
                feature_count=r.feature_count,
                geometry_types=r.geometry_types,
                crs=r.crs,
                measurement_crs=r.measurement_crs,
                created_at=r.created_at,
                error_message=r.error_message,
            )
            for r in records
        ],
    )


@router.get(
    "/{file_id}",
    response_model=FileDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get file details",
    description="Retrieve file metadata, processing status, and CRS summary for a given file ID.",
)
@router.get(
    "/{file_id}/",
    response_model=FileDetailResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def get_file(
    file_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> FileDetailResponse:
    """Retrieve details of a single geospatial file by ID."""
    record = db.scalar(select(FileRecord).where(FileRecord.id == str(file_id)))
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )

    return FileDetailResponse(
        id=UUID(record.id),
        filename=record.filename,
        stored_filename=record.stored_filename,
        file_type=record.file_type,
        size_bytes=record.size_bytes,
        status=record.status,
        feature_count=record.feature_count,
        geometry_types=record.geometry_types,
        crs=record.crs,
        measurement_crs=record.measurement_crs,
        created_at=record.created_at,
        error_message=record.error_message,
    )


@router.get(
    "/{file_id}/measurements",
    response_model=FileMeasurementsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get feature measurements",
    description="Retrieve geometric measurements (area, length) for each feature in a file.",
)
@router.get(
    "/{file_id}/measurements/",
    response_model=FileMeasurementsResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def get_file_measurements(
    file_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> FileMeasurementsResponse:
    """Retrieve detailed geometric measurements for all features in a file."""
    record = db.scalar(select(FileRecord).where(FileRecord.id == str(file_id)))
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )

    if record.crs is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot calculate metric measurements because the source dataset CRS is missing.",
        )

    return FileMeasurementsResponse(
        file_id=UUID(record.id),
        filename=record.filename,
        status=record.status,
        source_crs=record.crs,
        measurement_crs=record.measurement_crs,
        total_features=record.feature_count or 0,
        measurements=[
            m for m in record.measurements
        ],
    )


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a file",
    description="Remove a file record and its persistent measurements, and delete the file from disk.",
)
@router.delete(
    "/{file_id}/",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def delete_file(
    file_id: UUID,
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Delete a geospatial file from storage and database."""
    record = db.scalar(select(FileRecord).where(FileRecord.id == str(file_id)))
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )

    # Remove physical file if it exists
    file_path = upload_service.upload_dir / record.stored_filename
    if file_path.exists():
        file_path.unlink()

    db.delete(record)
    db.commit()

    return {"status": "deleted", "id": str(file_id)}
