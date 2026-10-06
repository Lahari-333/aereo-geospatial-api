"""Service for validating, unpacking, and parsing geospatial datasets (KML and Shapefile ZIP)."""

from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
from typing import Any
import uuid
import xml.etree.ElementTree as ET
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
import shapely.geometry

from app.core.config import Settings

logger = logging.getLogger(__name__)


class GeospatialProcessingError(Exception):
    """Base exception for all geospatial processing errors."""


class CorruptFileError(GeospatialProcessingError):
    """Raised when an uploaded file cannot be parsed or read by geospatial drivers."""


class ZipSecurityError(GeospatialProcessingError):
    """Raised when a ZIP archive violates security boundaries (path traversal, size bombs)."""


class InvalidShapefileError(GeospatialProcessingError):
    """Raised when a Shapefile archive lacks required files or contains multiple Shapefiles."""


@dataclass
class NormalizedFeature:
    """Internal normalized representation of an individual geospatial feature."""

    feature_id: int
    geometry_type: str
    geometry: dict[str, Any] | None
    crs: str | None
    properties: dict[str, Any]
    is_valid: bool = True
    is_empty: bool = False


@dataclass
class FileProcessingResult:
    """Normalized output produced after reading and validating a geospatial dataset."""

    file_id: uuid.UUID
    file_type: str
    feature_count: int
    geometry_types: list[str]
    crs: str | None
    features: list[NormalizedFeature]
    has_missing_crs: bool = False


class GeospatialFileProcessor:
    """Parses and extracts metadata from KML and ESRI Shapefile ZIP archives."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def process_file(
        self,
        file_path: Path,
        file_type: str,
        file_id: uuid.UUID,
    ) -> FileProcessingResult:
        """Process an uploaded geospatial file based on its detected format."""
        normalized_type = file_type.lower().lstrip(".")
        if normalized_type == "kml":
            return self._process_kml(file_path, file_id)
        elif normalized_type == "zip":
            return self._process_shapefile_zip(file_path, file_id)
        else:
            raise GeospatialProcessingError(f"Unsupported file format '{file_type}'.")

    def _process_kml(self, file_path: Path, file_id: uuid.UUID) -> FileProcessingResult:
        """Parse a KML file with GeoPandas and extract features and CRS metadata."""
        try:
            gdf = gpd.read_file(file_path)
        except IndexError:
            # pyogrio raises IndexError when encountering an empty KML dataset (0 layers / 0 features)
            try:
                tree = ET.parse(file_path)
                root = tree.getroot()
                if root.tag.lower().endswith("kml"):
                    return FileProcessingResult(
                        file_id=file_id,
                        file_type="kml",
                        feature_count=0,
                        geometry_types=[],
                        crs="EPSG:4326",
                        features=[],
                        has_missing_crs=False,
                    )
            except Exception:
                pass
            raise CorruptFileError("Malformed or empty KML file could not be read.")
        except (pyogrio.errors.DataSourceError, Exception) as exc:
            logger.warning("Failed to parse KML file %s: %s", file_path.name, exc)
            raise CorruptFileError(f"Malformed or unreadable KML file: {exc}") from exc

        if not isinstance(gdf, gpd.GeoDataFrame):
            raise CorruptFileError("Failed to construct GeoDataFrame from KML source.")

        crs_str = self._extract_crs_string(gdf.crs)
        feature_count, geometry_types, features = self._extract_features(gdf, crs_str)

        return FileProcessingResult(
            file_id=file_id,
            file_type="kml",
            feature_count=feature_count,
            geometry_types=geometry_types,
            crs=crs_str,
            features=features,
            has_missing_crs=(crs_str is None),
        )

    def _process_shapefile_zip(self, file_path: Path, file_id: uuid.UUID) -> FileProcessingResult:
        """Safely unpack a ZIP archive, validate the Shapefile components, and parse with GeoPandas."""
        temp_dir = self.settings.PROCESSED_DIR / f"extract_{uuid.uuid4()}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            shp_path = self._safe_unpack_zip(file_path, temp_dir)
            try:
                gdf = gpd.read_file(shp_path)
            except Exception as exc:
                logger.warning("Failed to read Shapefile %s: %s", shp_path.name, exc)
                raise CorruptFileError(f"Failed to read ESRI Shapefile: {exc}") from exc

            if not isinstance(gdf, gpd.GeoDataFrame):
                raise CorruptFileError("Failed to construct GeoDataFrame from Shapefile source.")

            crs_str = self._extract_crs_string(gdf.crs)
            feature_count, geometry_types, features = self._extract_features(gdf, crs_str)

            return FileProcessingResult(
                file_id=file_id,
                file_type="zip",
                feature_count=feature_count,
                geometry_types=geometry_types,
                crs=crs_str,
                features=features,
                has_missing_crs=(crs_str is None),
            )

        finally:
            # Reliably clean up the temporary extraction directory
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _safe_unpack_zip(self, zip_path: Path, destination_dir: Path) -> Path:
        """Inspect and safely extract a ZIP archive protecting against Zip Slip and archive bombs."""
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                infolist = zf.infolist()

                # 1. Enforce member count limit
                if len(infolist) > self.settings.MAX_ZIP_MEMBERS:
                    raise ZipSecurityError(
                        f"ZIP archive contains {len(infolist)} entries, exceeding the limit of "
                        f"{self.settings.MAX_ZIP_MEMBERS} files."
                    )

                # 2. Enforce total uncompressed size limit
                total_uncompressed = sum(member.file_size for member in infolist)
                if total_uncompressed > self.settings.max_zip_uncompressed_size_bytes:
                    raise ZipSecurityError(
                        f"Total uncompressed ZIP size ({total_uncompressed} bytes) exceeds limit of "
                        f"{self.settings.MAX_ZIP_UNCOMPRESSED_SIZE_MB} MB."
                    )

                dest_resolved = destination_dir.resolve()

                # 3. Inspect every member against path traversal
                for member in infolist:
                    filename = member.filename
                    # Reject absolute paths, drive letters, and traversal components
                    if Path(filename).is_absolute() or filename.startswith(("/", "\\")):
                        raise ZipSecurityError(
                            f"Path traversal rejected: archive entry '{filename}' contains absolute path."
                        )

                    parts = Path(filename).parts
                    if ".." in parts:
                        raise ZipSecurityError(
                            f"Path traversal rejected: archive entry '{filename}' contains directory traversal sequence."
                        )

                    target_path = (destination_dir / filename).resolve()
                    if not target_path.is_relative_to(dest_resolved):
                        raise ZipSecurityError(
                            f"Path traversal rejected: target '{target_path}' escapes extraction directory."
                        )

                # Extract validated members
                zf.extractall(destination_dir)

        except zipfile.BadZipFile as exc:
            raise CorruptFileError("Invalid or corrupted ZIP archive.") from exc

        # 4. Search for .shp files in the extracted tree
        shp_candidates = [
            p for p in destination_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".shp"
        ]

        if not shp_candidates:
            raise InvalidShapefileError("ZIP archive does not contain an ESRI Shapefile (.shp).")

        if len(shp_candidates) > 1:
            names = [f.name for f in shp_candidates]
            raise InvalidShapefileError(
                f"Multiple Shapefiles found in archive: {names}. The archive must contain exactly one Shapefile."
            )

        selected_shp = shp_candidates[0]

        # 5. Verify required companion files (.shx, .dbf)
        parent_dir = selected_shp.parent
        stem_lower = selected_shp.stem.lower()

        companion_extensions = {
            item.suffix.lower()
            for item in parent_dir.iterdir()
            if item.is_file() and item.stem.lower() == stem_lower
        }

        required_extensions = {".shp", ".shx", ".dbf"}
        missing_required = required_extensions - companion_extensions

        if missing_required:
            missing_names = ", ".join(sorted(missing_required))
            raise InvalidShapefileError(
                f"Shapefile '{selected_shp.name}' is missing required companion file(s): {missing_names}."
            )

        return selected_shp

    def _extract_crs_string(self, crs: Any) -> str | None:
        """Extract a clean, standardized CRS string identifier or None if missing."""
        if crs is None:
            return None
        epsg = crs.to_epsg()
        if epsg is not None:
            return f"EPSG:{epsg}"
        return crs.to_string()

    def _extract_features(
        self,
        gdf: gpd.GeoDataFrame,
        crs_str: str | None,
    ) -> tuple[int, list[str], list[NormalizedFeature]]:
        """Extract features, geometries, and properties into a normalized JSON-compatible structure."""
        if gdf.empty or len(gdf) == 0:
            return 0, [], []

        active_geom_col = gdf.geometry.name if hasattr(gdf, "geometry") else "geometry"
        features: list[NormalizedFeature] = []
        observed_geom_types: set[str] = set()

        for idx, row in gdf.iterrows():
            geom = row.get(active_geom_col)

            if geom is None:
                geom_type = "None"
                geom_dict = None
                is_valid = False
                is_empty = True
            else:
                geom_type = getattr(geom, "geom_type", "Unknown")
                is_empty = getattr(geom, "is_empty", False)
                is_valid = getattr(geom, "is_valid", False) if not is_empty else False

                if is_empty:
                    geom_dict = {"type": geom_type, "coordinates": []}
                else:
                    geom_dict = shapely.geometry.mapping(geom)

                observed_geom_types.add(geom_type)

            # Extract non-geometry attributes and normalize to JSON-friendly types
            properties: dict[str, Any] = {}
            for col in gdf.columns:
                if col == active_geom_col:
                    continue
                val = row[col]
                if pd.isna(val):
                    properties[col] = None
                elif isinstance(val, (np.integer, int)):
                    properties[col] = int(val)
                elif isinstance(val, (np.floating, float)):
                    properties[col] = float(val)
                elif hasattr(val, "isoformat"):
                    properties[col] = val.isoformat()
                else:
                    properties[col] = val

            features.append(
                NormalizedFeature(
                    feature_id=int(idx),
                    geometry_type=geom_type,
                    geometry=geom_dict,
                    crs=crs_str,
                    properties=properties,
                    is_valid=is_valid,
                    is_empty=is_empty,
                )
            )

        geometry_types = sorted(list(observed_geom_types))
        return len(features), geometry_types, features
