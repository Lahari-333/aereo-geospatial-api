"""Service module for calculating geospatial metric measurements (area, length)."""

from dataclasses import dataclass
import logging
from typing import Any
import geopandas as gpd

from app.services.crs_handler import CRSHandler, MissingCRSError

logger = logging.getLogger(__name__)


class MeasurementError(Exception):
    """Base exception for geometric measurement errors."""


class UnsupportedGeometryError(MeasurementError):
    """Raised when an operation is requested on an unsupported geometry type."""


class InvalidGeometryError(MeasurementError):
    """Raised when an invalid geometry is encountered and strict validation is enabled."""


@dataclass
class FeatureMeasurement:
    """Calculated metric measurement for an individual feature."""

    feature_id: int
    geometry_type: str
    measurement_type: str | None  # "area", "length", or None
    value: float | None  # Floating-point measurement value, full precision
    unit: str | None  # "square_meters", "meters", or None
    source_crs: str | None
    measurement_crs: str | None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize measurement result to standard dictionary."""
        return {
            "feature_id": self.feature_id,
            "geometry_type": self.geometry_type,
            "measurement_type": self.measurement_type,
            "value": self.value,
            "unit": self.unit,
            "source_crs": self.source_crs,
            "measurement_crs": self.measurement_crs,
        }


class MeasurementService:
    """Performs metric calculations on geospatial datasets with automatic CRS reprojection."""

    def __init__(self, crs_handler: CRSHandler | None = None) -> None:
        self.crs_handler = crs_handler or CRSHandler()

    def calculate_measurements(
        self,
        gdf: gpd.GeoDataFrame,
        strict_validity: bool = False,
    ) -> list[FeatureMeasurement]:
        """Calculate geometric measurements for each feature in a GeoDataFrame.

        Features are evaluated independently:
        - Polygon / MultiPolygon -> area in square_meters
        - LineString / MultiLineString -> length in meters
        - Point -> no measurement (value=None, measurement_crs=None)
        - Invalid / Empty / Null -> measurement marked unavailable (value=None)

        Args:
            gdf: Source GeoDataFrame.
            strict_validity: If True, raises InvalidGeometryError on invalid geometries.

        Returns:
            List of FeatureMeasurement instances.

        Raises:
            MissingCRSError: When the source dataset has no CRS defined.
            MeasurementCRSError: When reprojection to planar coordinates fails.
        """
        if gdf.empty:
            logger.info("Empty GeoDataFrame provided; returning 0 measurements.")
            return []

        # 1. Transform dataset to appropriate metric projected CRS
        transformed_gdf, source_crs_str, measurement_crs_str, is_transformed = (
            self.crs_handler.transform_for_measurement(gdf)
        )

        active_geom_col = (
            transformed_gdf.geometry.name
            if hasattr(transformed_gdf, "geometry")
            else "geometry"
        )

        results: list[FeatureMeasurement] = []

        # 2. Iterate each feature independently
        for idx, row in transformed_gdf.iterrows():
            feature_id = int(idx)
            geom = row.get(active_geom_col)

            # Null geometry handling
            if geom is None:
                results.append(
                    FeatureMeasurement(
                        feature_id=feature_id,
                        geometry_type="None",
                        measurement_type=None,
                        value=None,
                        unit=None,
                        source_crs=source_crs_str,
                        measurement_crs=None,
                        notes="Geometry is null.",
                    )
                )
                continue

            geom_type = getattr(geom, "geom_type", "Unknown")

            # Empty geometry handling
            if getattr(geom, "is_empty", False):
                measurement_type = self._determine_measurement_type(geom_type)
                results.append(
                    FeatureMeasurement(
                        feature_id=feature_id,
                        geometry_type=geom_type,
                        measurement_type=measurement_type,
                        value=None,
                        unit=None,
                        source_crs=source_crs_str,
                        measurement_crs=None,
                        notes="Geometry is empty.",
                    )
                )
                continue

            # Invalid geometry handling (no silent buffer(0) repair)
            if not getattr(geom, "is_valid", True):
                if strict_validity:
                    raise InvalidGeometryError(
                        f"Feature {feature_id} contains an invalid {geom_type} geometry."
                    )
                measurement_type = self._determine_measurement_type(geom_type)
                results.append(
                    FeatureMeasurement(
                        feature_id=feature_id,
                        geometry_type=geom_type,
                        measurement_type=measurement_type,
                        value=None,
                        unit=None,
                        source_crs=source_crs_str,
                        measurement_crs=None,
                        notes="Geometry is topologically invalid. Measurement unavailable.",
                    )
                )
                continue

            # Valid geometries: dispatch by type
            if geom_type == "Point":
                # Points do not require measurement
                results.append(
                    FeatureMeasurement(
                        feature_id=feature_id,
                        geometry_type="Point",
                        measurement_type=None,
                        value=None,
                        unit=None,
                        source_crs=source_crs_str,
                        measurement_crs=None,
                    )
                )

            elif geom_type in ("LineString", "MultiLineString"):
                # Planar length in meters
                length_val = float(geom.length)
                results.append(
                    FeatureMeasurement(
                        feature_id=feature_id,
                        geometry_type=geom_type,
                        measurement_type="length",
                        value=length_val,
                        unit="meters",
                        source_crs=source_crs_str,
                        measurement_crs=measurement_crs_str,
                    )
                )

            elif geom_type in ("Polygon", "MultiPolygon"):
                # Planar area in square meters
                area_val = float(geom.area)
                results.append(
                    FeatureMeasurement(
                        feature_id=feature_id,
                        geometry_type=geom_type,
                        measurement_type="area",
                        value=area_val,
                        unit="square_meters",
                        source_crs=source_crs_str,
                        measurement_crs=measurement_crs_str,
                    )
                )

            else:
                # Unsupported geometry types (e.g. MultiPoint, GeometryCollection)
                results.append(
                    FeatureMeasurement(
                        feature_id=feature_id,
                        geometry_type=geom_type,
                        measurement_type=None,
                        value=None,
                        unit=None,
                        source_crs=source_crs_str,
                        measurement_crs=None,
                        notes=f"Measurement not supported for geometry type: {geom_type}.",
                    )
                )

        logger.info("Computed measurements for %d features.", len(results))
        return results

    @staticmethod
    def _determine_measurement_type(geom_type: str) -> str | None:
        """Infer target measurement type from geometry type."""
        if "Polygon" in geom_type:
            return "area"
        if "Line" in geom_type:
            return "length"
        return None

    def measure_file_result(
        self,
        file_result: Any,
        strict_validity: bool = False,
    ) -> list[FeatureMeasurement]:
        """Calculate measurements directly from a FileProcessingResult containing a GeoDataFrame."""
        gdf = getattr(file_result, "gdf", None)
        if gdf is None:
            if getattr(file_result, "feature_count", 0) == 0:
                return []
            raise MeasurementError("FileProcessingResult does not contain an active GeoDataFrame.")
        return self.calculate_measurements(gdf, strict_validity=strict_validity)
