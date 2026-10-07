"""Tests for spatial summary metrics (bbox, planar centroid, aggregate metrics, processing time)."""

import io
from fastapi.testclient import TestClient
import geopandas as gpd
from shapely.geometry import Polygon

from app.services.spatial_analyzer import SpatialAnalyzer
from tests.fixtures import (
    create_valid_kml_bytes,
    create_valid_shapefile_zip_bytes,
)


def test_upload_returns_spatial_summary_and_timing(isolated_storage, client: TestClient) -> None:
    """Verify that file upload response includes spatial summary and real processing time."""
    upload_res = client.post(
        "/api/files/",
        files={"file": ("polygon.zip", io.BytesIO(create_valid_shapefile_zip_bytes()), "application/zip")},
    )
    assert upload_res.status_code == 201
    data = upload_res.json()

    # Processing time ms must be positive
    assert "processing_time_ms" in data
    assert data["processing_time_ms"] is not None
    assert data["processing_time_ms"] > 0

    # Spatial summary
    assert "spatial_summary" in data
    summary = data["spatial_summary"]
    assert summary is not None
    assert summary["bbox"] is not None
    assert len(summary["bbox"]) == 4
    # minx < maxx and miny < maxy
    assert summary["bbox"][0] < summary["bbox"][2]
    assert summary["bbox"][1] < summary["bbox"][3]

    # Centroid
    assert summary["centroid"] is not None
    assert len(summary["centroid"]) == 2
    lon, lat = summary["centroid"]
    # Coordinates inside the bbox
    assert summary["bbox"][0] <= lon <= summary["bbox"][2]
    assert summary["bbox"][1] <= lat <= summary["bbox"][3]

    # Aggregates
    assert summary["total_area_sqm"] > 0
    assert summary["total_length_m"] == 0.0


def test_get_file_and_list_files_include_spatial_summary(isolated_storage, client: TestClient) -> None:
    """Verify GET /api/files/{id} and GET /api/files/ return the spatial summary."""
    upload_res = client.post(
        "/api/files/",
        files={"file": ("polygon.zip", io.BytesIO(create_valid_shapefile_zip_bytes()), "application/zip")},
    )
    file_id = upload_res.json()["id"]

    # 1. Detail endpoint
    detail_res = client.get(f"/api/files/{file_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["spatial_summary"] is not None
    assert detail["spatial_summary"]["total_area_sqm"] > 0
    assert detail["processing_time_ms"] > 0

    # 2. List endpoint
    list_res = client.get("/api/files/")
    assert list_res.status_code == 200
    files = list_res.json()["files"]
    assert len(files) == 1
    assert files[0]["spatial_summary"] is not None
    assert files[0]["spatial_summary"]["total_area_sqm"] > 0


def test_centroid_calculation_scientific_accuracy() -> None:
    """Verify that planar centroid projects to metric UTM before reprojecting to WGS 84."""
    # Create a polygon in Bengaluru, India
    poly = Polygon([(77.5, 12.9), (77.6, 12.9), (77.6, 13.0), (77.5, 13.0)])
    gdf = gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")

    centroid = SpatialAnalyzer.compute_centroid(gdf)
    assert centroid is not None
    lon, lat = centroid
    # Must be approximately (77.55, 12.95)
    assert abs(lon - 77.55) < 0.01
    assert abs(lat - 12.95) < 0.01


def test_empty_or_null_geometry_spatial_summary() -> None:
    """Verify handling of GeoDataFrames with empty or null geometries."""
    gdf = gpd.GeoDataFrame(geometry=[None], crs="EPSG:4326")
    bbox = SpatialAnalyzer.compute_bbox(gdf)
    centroid = SpatialAnalyzer.compute_centroid(gdf)
    assert bbox is None
    assert centroid is None
