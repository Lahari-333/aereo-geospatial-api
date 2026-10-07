"""Pydantic schemas for geospatial file requests, responses, and measurement outputs."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


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
