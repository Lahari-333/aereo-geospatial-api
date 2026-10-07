"""Data models for file records and persistent feature measurements."""

from datetime import datetime, timezone
import json
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.database import Base


class FileRecord(Base):
    """Represents an uploaded geospatial dataset and its processing summary."""

    __tablename__ = "file_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="UPLOADED")
    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    _geometry_types: Mapped[str] = mapped_column("geometry_types", Text, nullable=False, default="[]")
    crs: Mapped[str | None] = mapped_column(String(50), nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    _bbox: Mapped[str | None] = mapped_column("bbox", Text, nullable=True)
    _centroid: Mapped[str | None] = mapped_column("centroid", Text, nullable=True)
    _geojson_data: Mapped[str | None] = mapped_column("geojson_data", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    measurements: Mapped[list["MeasurementRecord"]] = relationship(
        "MeasurementRecord",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="MeasurementRecord.feature_id",
    )

    @property
    def geometry_types(self) -> list[str]:
        """Deserialize stored JSON geometry types to Python list."""
        try:
            return json.loads(self._geometry_types)
        except Exception:
            return []

    @geometry_types.setter
    def geometry_types(self, value: list[str]) -> None:
        """Serialize Python list of geometry types to JSON string."""
        self._geometry_types = json.dumps(value)

    @property
    def bbox(self) -> list[float] | None:
        """Deserialize bounding box [minx, miny, maxx, maxy]."""
        if not self._bbox:
            return None
        try:
            return json.loads(self._bbox)
        except Exception:
            return None

    @bbox.setter
    def bbox(self, value: list[float] | None) -> None:
        """Serialize bounding box to JSON string."""
        self._bbox = json.dumps(value) if value is not None else None

    @property
    def centroid(self) -> list[float] | None:
        """Deserialize centroid [longitude, latitude]."""
        if not self._centroid:
            return None
        try:
            return json.loads(self._centroid)
        except Exception:
            return None

    @centroid.setter
    def centroid(self, value: list[float] | None) -> None:
        """Serialize centroid to JSON string."""
        self._centroid = json.dumps(value) if value is not None else None

    @property
    def geojson_data(self) -> dict | None:
        """Deserialize GeoJSON FeatureCollection dictionary."""
        if not self._geojson_data:
            return None
        try:
            return json.loads(self._geojson_data)
        except Exception:
            return None

    @geojson_data.setter
    def geojson_data(self, value: dict | None) -> None:
        """Serialize GeoJSON dictionary to JSON string."""
        self._geojson_data = json.dumps(value) if value is not None else None


class MeasurementRecord(Base):
    """Represents a geometric metric calculation for an individual feature."""

    __tablename__ = "measurement_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("file_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feature_id: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(50), nullable=False)
    measurement_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_crs: Mapped[str | None] = mapped_column(String(50), nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    file: Mapped["FileRecord"] = relationship("FileRecord", back_populates="measurements")
