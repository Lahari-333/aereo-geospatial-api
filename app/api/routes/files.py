"""HTTP endpoints for geospatial file upload, inspection, measurement, batch processing, and GeoJSON export."""

import time
from typing import Annotated, Any
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.file_record import FileRecord, MeasurementRecord
from app.schemas.file import (
    BatchFileItemResponse,
    BatchUploadResponse,
    FileDetailResponse,
    FileListResponse,
    FileMeasurementsResponse,
    FileUploadResponse,
    SpatialSummaryResponse,
)
from app.services.crs_handler import MissingCRSError
from app.services.file_processor import GeospatialFileProcessor, GeospatialProcessingError
from app.services.measurement import MeasurementService
from app.services.spatial_analyzer import SpatialAnalyzer
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


async def process_single_upload(
    file: UploadFile,
    upload_service: UploadService,
    processor: GeospatialFileProcessor,
    measurer: MeasurementService,
    db: Session,
) -> tuple[FileRecord, SpatialSummaryResponse, float]:
    """Validate, store, parse, measure, analyze, and persist a single geospatial file."""
    start_time = time.perf_counter()
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
                for m in calculated_measurements:
                    if m.measurement_crs:
                        measurement_crs_str = m.measurement_crs
                        break
            except MissingCRSError:
                pass

        # Compute spatial summary (bbox, planar centroid, aggregate metrics, GeoJSON)
        bbox: list[float] | None = None
        centroid: list[float] | None = None
        total_area: float = 0.0
        total_length: float = 0.0
        geojson_data: dict[str, Any] | None = None

        if processing_result.gdf is not None and not processing_result.has_missing_crs:
            bbox = SpatialAnalyzer.compute_bbox(processing_result.gdf)
            centroid = SpatialAnalyzer.compute_centroid(processing_result.gdf)
            total_area, total_length = SpatialAnalyzer.compute_aggregates(calculated_measurements)
            geojson_data = SpatialAnalyzer.build_geojson(
                processing_result.gdf,
                calculated_measurements,
                bbox=bbox,
            )

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
            total_area_sqm=total_area,
            total_length_m=total_length,
        )
        file_entity.geometry_types = processing_result.geometry_types
        file_entity.bbox = bbox
        file_entity.centroid = centroid
        file_entity.geojson_data = geojson_data

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

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        file_entity.processing_time_ms = elapsed_ms

        db.add(file_entity)
        db.commit()
        db.refresh(file_entity)

        spatial_summary = SpatialSummaryResponse(
            bbox=bbox,
            centroid=centroid,
            total_area_sqm=total_area,
            total_length_m=total_length,
        )
        return file_entity, spatial_summary, elapsed_ms

    except Exception:
        db.rollback()
        if stored_path.exists():
            stored_path.unlink()
        raise


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
        "spatial summary (bbox, centroid) is analyzed, and metadata is persisted for querying."
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
    file_entity, spatial_summary, elapsed_ms = await process_single_upload(
        file=file,
        upload_service=upload_service,
        processor=processor,
        measurer=measurer,
        db=db,
    )

    return FileUploadResponse(
        id=UUID(file_entity.id),
        filename=file_entity.filename,
        stored_filename=file_entity.stored_filename,
        file_type=file_entity.file_type,
        size_bytes=file_entity.size_bytes,
        status="COMPLETED",
        feature_count=file_entity.feature_count,
        geometry_types=file_entity.geometry_types,
        crs=file_entity.crs,
        processing_time_ms=elapsed_ms,
        spatial_summary=spatial_summary,
    )


@router.post(
    "/batch",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
@router.post(
    "/batch/",
    response_model=BatchUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch upload and process geospatial files",
    description="Upload up to 10 geospatial files (.kml and .zip) simultaneously with independent fault isolation.",
)
async def upload_files_batch(
    files: Annotated[
        list[UploadFile],
        File(description="List of geospatial vector files (.kml or .zip) to upload"),
    ],
    upload_service: Annotated[UploadService, Depends(get_upload_service)],
    processor: Annotated[GeospatialFileProcessor, Depends(get_file_processor)],
    measurer: Annotated[MeasurementService, Depends(get_measurement_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[Session, Depends(get_db)],
) -> BatchUploadResponse:
    """Process multiple geospatial file uploads in a single batch request with fault isolation."""
    batch_start = time.perf_counter()

    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file must be provided for batch upload.",
        )

    if len(files) > settings.MAX_BATCH_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Batch size of {len(files)} exceeds maximum limit of {settings.MAX_BATCH_FILES} files.",
        )

    results: list[BatchFileItemResponse] = []

    for upload_file_item in files:
        file_start = time.perf_counter()
        orig_name = upload_file_item.filename or "unknown"
        try:
            file_entity, spatial_summary, _ = await process_single_upload(
                file=upload_file_item,
                upload_service=upload_service,
                processor=processor,
                measurer=measurer,
                db=db,
            )
            file_ms = round((time.perf_counter() - file_start) * 1000, 2)
            results.append(
                BatchFileItemResponse(
                    filename=file_entity.filename,
                    status="COMPLETED",
                    file_id=UUID(file_entity.id),
                    file_type=file_entity.file_type,
                    size_bytes=file_entity.size_bytes,
                    feature_count=file_entity.feature_count,
                    geometry_types=file_entity.geometry_types,
                    crs=file_entity.crs,
                    processing_time_ms=file_ms,
                    spatial_summary=spatial_summary,
                )
            )
        except HTTPException as exc:
            file_ms = round((time.perf_counter() - file_start) * 1000, 2)
            results.append(
                BatchFileItemResponse(
                    filename=orig_name,
                    status="FAILED",
                    error=str(exc.detail),
                    processing_time_ms=file_ms,
                )
            )
        except Exception as exc:
            file_ms = round((time.perf_counter() - file_start) * 1000, 2)
            results.append(
                BatchFileItemResponse(
                    filename=orig_name,
                    status="FAILED",
                    error=str(exc),
                    processing_time_ms=file_ms,
                )
            )

    successful = sum(1 for r in results if r.status == "COMPLETED")
    failed = sum(1 for r in results if r.status == "FAILED")
    total_ms = round((time.perf_counter() - batch_start) * 1000, 2)

    return BatchUploadResponse(
        total_files=len(files),
        successful=successful,
        failed=failed,
        total_processing_time_ms=total_ms,
        results=results,
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
    files = []
    for r in records:
        sp = None
        if r.bbox or r.centroid or r.total_area_sqm is not None or r.total_length_m is not None:
            sp = SpatialSummaryResponse(
                bbox=r.bbox,
                centroid=r.centroid,
                total_area_sqm=r.total_area_sqm or 0.0,
                total_length_m=r.total_length_m or 0.0,
            )
        files.append(
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
                processing_time_ms=r.processing_time_ms,
                spatial_summary=sp,
            )
        )

    return FileListResponse(
        total=len(files),
        files=files,
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

    spatial_summary = None
    if record.bbox or record.centroid or record.total_area_sqm is not None or record.total_length_m is not None:
        spatial_summary = SpatialSummaryResponse(
            bbox=record.bbox,
            centroid=record.centroid,
            total_area_sqm=record.total_area_sqm or 0.0,
            total_length_m=record.total_length_m or 0.0,
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
        processing_time_ms=record.processing_time_ms,
        spatial_summary=spatial_summary,
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
        measurements=[m for m in record.measurements],
    )


@router.get(
    "/{file_id}/geojson",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Export file as GeoJSON",
    description="Retrieve RFC 7946 compliant GeoJSON FeatureCollection in WGS 84 (EPSG:4326) with feature measurements.",
)
@router.get(
    "/{file_id}/geojson/",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def get_file_geojson(
    file_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Retrieve RFC 7946 GeoJSON FeatureCollection for a file."""
    record = db.scalar(select(FileRecord).where(FileRecord.id == str(file_id)))
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File with ID '{file_id}' not found.",
        )

    if record.crs is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate GeoJSON because the source dataset CRS is missing.",
        )

    geojson_data = record.geojson_data
    if geojson_data is None:
        geojson_data = {
            "type": "FeatureCollection",
            "bbox": record.bbox,
            "features": [],
        }

    return geojson_data


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
