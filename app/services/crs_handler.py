"""Service module for Coordinate Reference System (CRS) validation, inspection, and reprojection."""

import logging
from typing import Any
import geopandas as gpd
import pyproj

logger = logging.getLogger(__name__)


class CRSError(Exception):
    """Base exception for coordinate reference system errors."""


class MissingCRSError(CRSError):
    """Raised when dataset does not define a Coordinate Reference System."""


class MeasurementCRSError(CRSError):
    """Raised when a suitable projected measurement CRS cannot be determined or reprojection fails."""


class CRSHandler:
    """Handles CRS inspection, validation, and transformation for metric measurements."""

    WEB_MERCATOR_EPSG_CODES = {3857, 900913, 3785, 3587, 102100, 102113}
    WEB_MERCATOR_KEYWORDS = {
        "pseudo-mercator",
        "popular visualisation pseudo mercator",
        "web mercator",
        "pseudo mercator",
    }

    @staticmethod
    def extract_crs_string(crs: Any) -> str | None:
        """Standardize CRS representation to an EPSG identifier string or WKT/PROJ string."""
        if crs is None:
            return None
        if not isinstance(crs, pyproj.CRS):
            try:
                crs = pyproj.CRS.from_user_input(crs)
            except Exception:
                return str(crs)

        epsg = crs.to_epsg()
        if epsg is not None:
            return f"EPSG:{epsg}"
        return crs.to_string()

    @staticmethod
    def is_geographic(crs: Any) -> bool:
        """Check whether the provided CRS is a geographic (angular) coordinate system."""
        if crs is None:
            return False
        if not isinstance(crs, pyproj.CRS):
            crs = pyproj.CRS.from_user_input(crs)
        return bool(crs.is_geographic)

    @staticmethod
    def is_projected(crs: Any) -> bool:
        """Check whether the provided CRS is a planar projected coordinate system."""
        if crs is None:
            return False
        if not isinstance(crs, pyproj.CRS):
            crs = pyproj.CRS.from_user_input(crs)
        return bool(crs.is_projected)

    @classmethod
    def is_suitable_metric_crs(cls, crs: Any) -> bool:
        """Check if a CRS is a planar projected coordinate system suitable for accurate metric calculations.

        Returns False if:
        - CRS is None or not projected (e.g. geographic EPSG:4326 in angular degrees).
        - CRS is Web Mercator / Pseudo-Mercator (e.g. EPSG:3857), which has severe latitude-dependent
          scale and area distortion making it unsuitable for planar measurements.
        - CRS coordinate units are not metric (e.g. US survey feet, feet).
        """
        if crs is None:
            return False
        if not isinstance(crs, pyproj.CRS):
            try:
                crs = pyproj.CRS.from_user_input(crs)
            except Exception:
                return False

        if not crs.is_projected:
            return False

        # 1. Reject Web Mercator variants due to severe scale distortion away from the equator
        epsg = crs.to_epsg()
        if epsg in cls.WEB_MERCATOR_EPSG_CODES:
            return False

        crs_name = (crs.name or "").lower()
        if any(kw in crs_name for kw in cls.WEB_MERCATOR_KEYWORDS):
            return False

        if crs.coordinate_operation and crs.coordinate_operation.method_name:
            method_name = crs.coordinate_operation.method_name.lower()
            if any(kw in method_name for kw in cls.WEB_MERCATOR_KEYWORDS):
                return False

        # 2. Verify metric units on planar coordinate axes
        if not crs.axis_info:
            return False

        for axis in crs.axis_info:
            unit_name = (axis.unit_name or "").lower()
            if unit_name in ("metre", "meter", "m"):
                continue
            conversion = getattr(axis, "unit_conversion_factor", None)
            if conversion is not None and abs(conversion - 1.0) < 1e-6:
                continue
            return False

        return True

    def determine_measurement_crs(self, gdf: gpd.GeoDataFrame) -> pyproj.CRS | None:
        """Select an appropriate projected CRS for planar metric calculations.

        Rules:
        - If CRS is missing: raises MissingCRSError (never assume EPSG:4326).
        - If CRS is already a suitable metric projection (e.g. UTM, Lambert in metres):
          returns the existing projected CRS directly.
        - If CRS is geographic (e.g. EPSG:4326) OR unsuitable for metric measurement
          (e.g. EPSG:3857 Web Mercator with scale distortion, or projected with foot units):
          estimates optimal local UTM CRS using dataset extent.
        - If geometries have no extent (all empty/null): returns None.
        """
        if gdf.crs is None:
            raise MissingCRSError(
                "Cannot calculate metric measurements because the source dataset CRS is missing."
            )

        source_crs = gdf.crs if isinstance(gdf.crs, pyproj.CRS) else pyproj.CRS.from_user_input(gdf.crs)

        # CASE A: Source CRS is already a suitable metric projection (e.g. UTM)
        if self.is_suitable_metric_crs(source_crs):
            logger.info("Source CRS is already a suitable metric projection: %s", self.extract_crs_string(source_crs))
            return source_crs

        # CASE B: Source CRS is geographic OR unsuitable projected (Web Mercator, non-metric feet)
        # Filter non-empty, non-null geometries to compute spatial extent
        active_geom_col = gdf.geometry.name if hasattr(gdf, "geometry") else "geometry"
        geom_series = gdf[active_geom_col]
        valid_indices = [
            i for i, geom in geom_series.items()
            if geom is not None and not getattr(geom, "is_empty", False)
        ]
        valid_subset = gdf.loc[valid_indices]

        if valid_subset.empty:
            logger.info("Dataset contains only empty or null geometries; no UTM projection needed.")
            return None

        try:
            estimated_utm = valid_subset.estimate_utm_crs()
            if estimated_utm is None or not estimated_utm.is_projected:
                raise MeasurementCRSError(
                    "Could not determine a valid projected UTM CRS for the dataset extent."
                )
            logger.info(
                "Determined UTM projection for dataset (source: %s): %s",
                self.extract_crs_string(source_crs),
                self.extract_crs_string(estimated_utm),
            )
            return estimated_utm
        except Exception as exc:
            if isinstance(exc, (MissingCRSError, MeasurementCRSError)):
                raise
            logger.warning("Failed to estimate UTM CRS: %s", exc)
            raise MeasurementCRSError(
                f"Could not determine a suitable projected measurement CRS for the dataset: {exc}"
            ) from exc

    def transform_for_measurement(
        self,
        gdf: gpd.GeoDataFrame,
    ) -> tuple[gpd.GeoDataFrame, str | None, str | None, bool]:
        """Transform a GeoDataFrame to a planar metric projection if needed.

        Returns:
            Tuple of (transformed_gdf, source_crs_str, measurement_crs_str, is_transformed)
        """
        if gdf.crs is None:
            raise MissingCRSError(
                "Cannot calculate metric measurements because the source dataset CRS is missing."
            )

        source_crs_str = self.extract_crs_string(gdf.crs)
        measurement_crs = self.determine_measurement_crs(gdf)

        if measurement_crs is None:
            # No valid geometries to project (all null or empty)
            return gdf, source_crs_str, None, False

        measurement_crs_str = self.extract_crs_string(measurement_crs)

        # If source is already the measurement CRS, no reprojection needed
        if gdf.crs == measurement_crs or source_crs_str == measurement_crs_str:
            return gdf, source_crs_str, measurement_crs_str, False

        # Transform using to_crs() (never set_crs())
        try:
            transformed_gdf = gdf.to_crs(measurement_crs)
            logger.info(
                "Successfully reprojected GeoDataFrame from %s to %s for measurement.",
                source_crs_str,
                measurement_crs_str,
            )
            return transformed_gdf, source_crs_str, measurement_crs_str, True
        except Exception as exc:
            logger.error("Reprojection from %s to %s failed: %s", source_crs_str, measurement_crs_str, exc)
            raise MeasurementCRSError(
                f"Failed to reproject dataset from {source_crs_str} to {measurement_crs_str}: {exc}"
            ) from exc
