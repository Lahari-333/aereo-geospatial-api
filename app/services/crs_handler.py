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

    def determine_measurement_crs(self, gdf: gpd.GeoDataFrame) -> pyproj.CRS | None:
        """Select an appropriate projected CRS for planar metric calculations.

        Rules:
        - If CRS is missing: raises MissingCRSError.
        - If CRS is already projected: returns the existing projected CRS directly.
        - If CRS is geographic: estimates optimal local UTM CRS using dataset bounds.
        - If geometries have no extent (all empty/null): returns None.
        """
        if gdf.crs is None:
            raise MissingCRSError(
                "Cannot calculate metric measurements because the source dataset CRS is missing."
            )

        source_crs = gdf.crs if isinstance(gdf.crs, pyproj.CRS) else pyproj.CRS.from_user_input(gdf.crs)

        # CASE A: Source CRS is already projected
        if source_crs.is_projected:
            logger.info("Source CRS is already projected: %s", self.extract_crs_string(source_crs))
            return source_crs

        # CASE B: Source CRS is geographic (e.g. EPSG:4326)
        if source_crs.is_geographic:
            # Filter non-empty, non-null geometries to compute spatial extent
            active_geom_col = gdf.geometry.name if hasattr(gdf, "geometry") else "geometry"
            valid_mask = (~gdf[active_geom_col].is_empty) & gdf[active_geom_col].notna()
            valid_subset = gdf[valid_mask]

            if valid_subset.empty:
                logger.info("Geographic dataset contains only empty or null geometries; no UTM projection needed.")
                return None

            try:
                estimated_utm = valid_subset.estimate_utm_crs()
                if estimated_utm is None or not estimated_utm.is_projected:
                    raise MeasurementCRSError(
                        "Could not determine a valid projected UTM CRS for the dataset extent."
                    )
                logger.info(
                    "Estimated UTM projection for geographic dataset: %s",
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

        # CASE D: Unrecognized or invalid CRS type
        raise MeasurementCRSError(
            f"Unsupported CRS type '{self.extract_crs_string(source_crs)}'. Must be geographic or projected."
        )

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
        if gdf.crs == measurement_crs or not gdf.crs.is_geographic:
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
            logger.error("Reprojection to %s failed: %s", measurement_crs_str, exc)
            raise MeasurementCRSError(
                f"Failed to reproject dataset from {source_crs_str} to {measurement_crs_str}: {exc}"
            ) from exc
