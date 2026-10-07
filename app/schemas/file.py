"""Pydantic schemas for geospatial file requests, responses, and measurement outputs."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class SpatialSummaryResponse(BaseModel):
    """Spatial bounding box, centroid, and aggregate geometric metrics."""

    bbox: list[float] | None = Field(
        default=None,
        description="Bounding box in EPSG:4326 [minx, miny, maxx, maxy]",
    )
    centroid: list[float] | None = Field(
        default=None,
        description="Centroid coordinate in EPSG:4326 [longitude, latitude]",
    )
    total_area_sqm: float = Field(
        default=0.0,
        description="Total aggregate area across all polygons in square meters",
    )
    total_length_m: float = Field(
        default=0.0,
        description="Total aggregate length across all linestrings in meters",
    )

    model_config = ConfigDict(from_attributes=True)


class FileUploadResponse(BaseModel):
    """Response model for uploaded and processed geospatial files."""

    id: UUID = Field(..., description="Unique identifier for the file record")
    filename: str = Field(..., description="Original name of the uploaded file")
    stored_filename: str = Field(..., description="Internal safely generated storage filename")
    file_type: str = Field(..., description="Detected supported file extension (e.g. kml, zip)")
    size_bytes: int = Field(..., description="Total size of the uploaded file in bytes")
    status: str = Field(default="COMPLETED", description="Current lifecycle processing status")
    feature_count: int | None = Field(default=None, description="Number of geospatial features extracted")
    geometry_types: list[str] = Field(default_factory=list, description="Unique geometry types detected in dataset")
    crs: str | None = Field(default=None, description="Coordinate Reference System of the source dataset, if defined")
    processing_time_ms: float | None = Field(
        default=None,
        description="Analysis and persistence duration in milliseconds",
    )
    spatial_summary: SpatialSummaryResponse | None = Field(
        default=None,
        description="Spatial bounding box, centroid, and metric totals",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "filename": "roads.kml",
                "stored_filename": "123e4567-e89b-12d3-a456-426614174000.kml",
                "file_type": "kml",
                "size_bytes": 12345,
                "status": "COMPLETED",
                "feature_count": 5,
                "geometry_types": ["Polygon", "LineString"],
                "crs": "EPSG:4326",
                "processing_time_ms": 42.5,
                "spatial_summary": {
                    "bbox": [77.5, 12.9, 77.6, 13.0],
                    "centroid": [77.55, 12.95],
                    "total_area_sqm": 123456.78,
                    "total_length_m": 450.0,
                },
            }
        },
    )


class FileDetailResponse(BaseModel):
    """Detailed file information including timestamp, measurements CRS, and status."""

    id: UUID = Field(..., description="Unique identifier for the file record")
    filename: str = Field(..., description="Original name of the uploaded file")
    stored_filename: str = Field(..., description="Internal safely generated storage filename")
    file_type: str = Field(..., description="Detected supported file extension (e.g. kml, zip)")
    size_bytes: int = Field(..., description="Total size of the uploaded file in bytes")
    status: str = Field(..., description="Current lifecycle processing status (e.g. COMPLETED, FAILED)")
    feature_count: int | None = Field(default=None, description="Number of geospatial features extracted")
    geometry_types: list[str] = Field(default_factory=list, description="Unique geometry types detected in dataset")
    crs: str | None = Field(default=None, description="Coordinate Reference System of the source dataset")
    measurement_crs: str | None = Field(default=None, description="Projected planar CRS used for measurements")
    created_at: datetime = Field(..., description="Creation and upload timestamp (UTC)")
    error_message: str | None = Field(default=None, description="Diagnostic error message if processing failed")
    processing_time_ms: float | None = Field(
        default=None,
        description="Analysis and persistence duration in milliseconds",
    )
    spatial_summary: SpatialSummaryResponse | None = Field(
        default=None,
        description="Spatial bounding box, centroid, and metric totals",
    )

    model_config = ConfigDict(from_attributes=True)


class FileListResponse(BaseModel):
    """List response containing stored geospatial file records."""

    total: int = Field(..., description="Total number of stored files")
    files: list[FileDetailResponse] = Field(..., description="List of file records")


class FeatureMeasurementResponse(BaseModel):
    """Geometric measurement details for an individual feature."""

    feature_id: int = Field(..., description="Deterministic zero-based feature index")
    geometry_type: str = Field(..., description="Type of geometry (Polygon, LineString, Point, etc.)")
    measurement_type: str | None = Field(default=None, description="Metric type ('area', 'length', or null)")
    value: float | None = Field(default=None, description="Calculated measurement value (null for Points or invalid geometries)")
    unit: str | None = Field(default=None, description="Measurement unit ('square_meters', 'meters', or null)")
    source_crs: str | None = Field(default=None, description="Original source Coordinate Reference System")
    measurement_crs: str | None = Field(default=None, description="Projected CRS used to compute the measurement")
    notes: str | None = Field(default=None, description="Additional context or notes regarding measurement status")

    model_config = ConfigDict(from_attributes=True)


class FileMeasurementsResponse(BaseModel):
    """Response containing all feature measurements for a geospatial file."""

    file_id: UUID = Field(..., description="Unique identifier of the measured file")
    filename: str = Field(..., description="Original filename")
    status: str = Field(..., description="File processing status")
    source_crs: str | None = Field(default=None, description="Source CRS of the dataset")
    measurement_crs: str | None = Field(default=None, description="Projected measurement CRS applied")
    total_features: int = Field(..., description="Total number of features in dataset")
    measurements: list[FeatureMeasurementResponse] = Field(..., description="Individual feature measurements")

    model_config = ConfigDict(from_attributes=True)


class BatchFileItemResponse(BaseModel):
    """Result and diagnostics for an individual file within a batch upload."""

    filename: str = Field(..., description="Original name of the uploaded file")
    status: str = Field(..., description="Processing status ('COMPLETED' or 'FAILED')")
    file_id: UUID | None = Field(default=None, description="Unique identifier if file was successfully processed")
    file_type: str | None = Field(default=None, description="Detected supported file extension")
    size_bytes: int | None = Field(default=None, description="Uploaded file size in bytes")
    feature_count: int | None = Field(default=None, description="Number of extracted geospatial features")
    geometry_types: list[str] = Field(default_factory=list, description="Unique geometry types detected")
    crs: str | None = Field(default=None, description="Detected source CRS")
    error: str | None = Field(default=None, description="Detailed diagnostic error message if processing failed")
    processing_time_ms: float | None = Field(default=None, description="Wall-clock processing time for this file in ms")
    spatial_summary: SpatialSummaryResponse | None = Field(default=None, description="Spatial bounding box, centroid, and metric totals")

    model_config = ConfigDict(from_attributes=True)


class BatchUploadResponse(BaseModel):
    """Aggregate response for multi-file batch upload operations."""

    total_files: int = Field(..., description="Total count of files processed in this batch")
    successful: int = Field(..., description="Count of successfully processed files")
    failed: int = Field(..., description="Count of files that failed processing")
    total_processing_time_ms: float = Field(..., description="Total wall-clock duration for the entire batch in ms")
    results: list[BatchFileItemResponse] = Field(..., description="Per-file processing outcomes and diagnostics")

    model_config = ConfigDict(from_attributes=True)
