"""Spatial analysis service for calculating bounding boxes, planar centroids, aggregate metrics, and GeoJSON export."""

from datetime import date, datetime
from typing import Any
import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
from pyproj import CRS
from shapely.geometry import mapping

from app.services.measurement import FeatureMeasurement


class SpatialAnalyzer:
    """Computes spatial summaries and constructs RFC 7946 compliant GeoJSON."""

    @staticmethod
    def _sanitize_value(val: Any) -> Any:
        """Convert arbitrary pandas/numpy values to JSON-serializable primitives."""
        if val is None or pd.isna(val):
            return None
        if isinstance(val, (int, float, str, bool)):
            if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
                return None
            return val
        if isinstance(val, (datetime, date)):
            return val.isoformat()
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            f_val = float(val)
            return None if (np.isnan(f_val) or np.isinf(f_val)) else f_val
        if isinstance(val, (np.bool_,)):
            return bool(val)
        return str(val)

    @classmethod
    def compute_bbox(cls, gdf: gpd.GeoDataFrame) -> list[float] | None:
        """Calculate dataset bounding box in WGS 84 [minx, miny, maxx, maxy]."""
        if gdf is None or gdf.empty:
            return None

        valid_geoms = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        if valid_geoms.empty:
            return None

        try:
            if gdf.crs is not None and not gdf.crs.equals(CRS.from_epsg(4326)):
                gdf_4326 = valid_geoms.to_crs(epsg=4326)
            else:
                gdf_4326 = valid_geoms

            bounds = gdf_4326.total_bounds
            if len(bounds) != 4 or np.any(np.isnan(bounds)) or np.any(np.isinf(bounds)):
                return None

            return [round(float(b), 6) for b in bounds]
        except Exception:
            return None

    @classmethod
    def compute_centroid(cls, gdf: gpd.GeoDataFrame) -> list[float] | None:
        """Calculate planar center of mass in UTM and reproject to WGS 84 [lon, lat]."""
        if gdf is None or gdf.empty or gdf.crs is None:
            return None

        valid_geoms = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        if valid_geoms.empty:
            return None

        try:
            # 1. Project to UTM for scientifically accurate planar center of mass
            utm_crs = valid_geoms.estimate_utm_crs()
            projected = valid_geoms.to_crs(utm_crs)
            planar_center = projected.geometry.union_all().centroid

            # 2. Reproject planar point to WGS 84 (EPSG:4326)
            transformer = pyproj.Transformer.from_crs(utm_crs, "EPSG:4326", always_xy=True)
            lon, lat = transformer.transform(planar_center.x, planar_center.y)

            if np.isnan(lon) or np.isnan(lat) or np.isinf(lon) or np.isinf(lat):
                return None

            return [round(float(lon), 6), round(float(lat), 6)]
        except Exception:
            # Fallback for projected CRS or single geometry where estimate_utm_crs is unavailable
            try:
                if valid_geoms.crs.is_projected:
                    planar_center = valid_geoms.geometry.union_all().centroid
                    transformer = pyproj.Transformer.from_crs(valid_geoms.crs, "EPSG:4326", always_xy=True)
                    lon, lat = transformer.transform(planar_center.x, planar_center.y)
                    return [round(float(lon), 6), round(float(lat), 6)]
                else:
                    center = valid_geoms.geometry.union_all().centroid
                    return [round(float(center.x), 6), round(float(center.y), 6)]
            except Exception:
                return None

    @classmethod
    def compute_aggregates(cls, measurements: list[FeatureMeasurement]) -> tuple[float, float]:
        """Compute aggregate total polygon area (m²) and total linestring length (m)."""
        total_area = sum(
            m.value for m in measurements
            if m.measurement_type == "area" and m.value is not None
        )
        total_length = sum(
            m.value for m in measurements
            if m.measurement_type == "length" and m.value is not None
        )
        return round(float(total_area), 2), round(float(total_length), 2)

    @classmethod
    def build_geojson(
        cls,
        gdf: gpd.GeoDataFrame,
        measurements: list[FeatureMeasurement],
        bbox: list[float] | None = None,
    ) -> dict[str, Any]:
        """Construct RFC 7946 compliant GeoJSON FeatureCollection in WGS 84."""
        if gdf is None or gdf.empty or gdf.crs is None:
            return {
                "type": "FeatureCollection",
                "bbox": bbox,
                "features": [],
            }

        # Ensure geometries are in WGS 84 (EPSG:4326)
        if not gdf.crs.equals(CRS.from_epsg(4326)):
            export_gdf = gdf.to_crs(epsg=4326)
        else:
            export_gdf = gdf

        # Index measurements by feature_id
        meas_by_id = {m.feature_id: m for m in measurements}

        features: list[dict[str, Any]] = []
        for idx in range(len(export_gdf)):
            row = export_gdf.iloc[idx]
            geom = row.geometry

            # Map geometry to GeoJSON
            geom_json = mapping(geom) if geom is not None and not geom.is_empty else None

            # Collect properties
            props: dict[str, Any] = {}
            for col in export_gdf.columns:
                if col == "geometry":
                    continue
                props[str(col)] = cls._sanitize_value(row[col])

            # Inject measurement properties
            meas = meas_by_id.get(idx)
            props["feature_id"] = idx
            props["geometry_type"] = geom.geom_type if geom is not None else "None"
            props["measurement_type"] = meas.measurement_type if meas else None
            props["measurement_value"] = meas.value if meas else None
            props["measurement_unit"] = meas.unit if meas else None
            props["source_crs"] = meas.source_crs if meas else (gdf.crs.to_string() if gdf.crs else None)
            props["measurement_crs"] = meas.measurement_crs if meas else None

            features.append({
                "type": "Feature",
                "id": idx,
                "geometry": geom_json,
                "properties": props,
            })

        fc: dict[str, Any] = {
            "type": "FeatureCollection",
            "features": features,
        }
        if bbox is not None:
            fc["bbox"] = bbox
        return fc
