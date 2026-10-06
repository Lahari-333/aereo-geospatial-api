"""Pydantic schemas for geospatial file requests and response payloads."""

from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class FileUploadResponse(BaseModel):
    """Response model for uploaded geospatial files."""

    id: UUID = Field(..., description="Unique identifier for the file record")
    filename: str = Field(..., description="Original name of the uploaded file")
    stored_filename: str = Field(..., description="Internal safely generated storage filename")
    file_type: str = Field(..., description="Detected supported file extension (e.g. kml, zip)")
    size_bytes: int = Field(..., description="Total size of the uploaded file in bytes")
    status: str = Field(default="UPLOADED", description="Current lifecycle processing status")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "filename": "roads.kml",
                "stored_filename": "123e4567-e89b-12d3-a456-426614174000.kml",
                "file_type": "kml",
                "size_bytes": 12345,
                "status": "UPLOADED",
            }
        }
    )
