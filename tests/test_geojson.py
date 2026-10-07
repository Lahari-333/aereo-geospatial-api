"""Tests for RFC 7946 GeoJSON export endpoint (GET /api/files/{id}/geojson)."""

import io
from uuid import uuid4
from fastapi.testclient import TestClient

from tests.fixtures import (
    create_valid_kml_bytes,
    create_valid_shapefile_zip_bytes,
)


def test_get_file_geojson_kml(isolated_storage, client: TestClient) -> None:
    """Verify exporting an uploaded KML as RFC 7946 GeoJSON."""
    upload_res = client.post(
        "/api/files/",
        files={"file": ("survey_point.kml", io.BytesIO(create_valid_kml_bytes()), "application/vnd.google-earth.kml+xml")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["id"]

    # Request GeoJSON
    res = client.get(f"/api/files/{file_id}/geojson")
    assert res.status_code == 200

    data = res.json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert len(data["features"]) == 1

    feature = data["features"][0]
    assert feature["type"] == "Feature"
    assert feature["id"] == 0
    assert feature["geometry"]["type"] == "Point"
    assert len(feature["geometry"]["coordinates"]) in (2, 3)
    assert feature["geometry"]["coordinates"][:2] == [77.5946, 12.9716]
    assert "properties" in feature
    assert feature["properties"]["geometry_type"] == "Point"
    assert feature["properties"]["feature_id"] == 0


def test_get_file_geojson_shapefile_polygon(isolated_storage, client: TestClient) -> None:
    """Verify exporting an uploaded Polygon shapefile includes metric measurements in properties."""
    upload_res = client.post(
        "/api/files/",
        files={"file": ("field_polygon.zip", io.BytesIO(create_valid_shapefile_zip_bytes()), "application/zip")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["id"]

    res = client.get(f"/api/files/{file_id}/geojson")
    assert res.status_code == 200

    data = res.json()
    assert data["type"] == "FeatureCollection"
    assert "bbox" in data
    assert len(data["bbox"]) == 4

    features = data["features"]
    assert len(features) == 1
    poly_feat = features[0]
    assert poly_feat["geometry"]["type"] == "Polygon"
    props = poly_feat["properties"]
    assert props["geometry_type"] == "Polygon"
    assert props["measurement_type"] == "area"
    assert props["measurement_unit"] == "square_meters"
    assert props["measurement_value"] > 0
    assert props["measurement_crs"] is not None


def test_get_file_geojson_missing_crs_rejected(isolated_storage, client: TestClient) -> None:
    """Verify dataset with missing CRS returns 400 when attempting GeoJSON export."""
    no_prj_bytes = create_valid_shapefile_zip_bytes(include_prj=False)
    upload_res = client.post(
        "/api/files/",
        files={"file": ("no_prj.zip", io.BytesIO(no_prj_bytes), "application/zip")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["id"]

    res = client.get(f"/api/files/{file_id}/geojson")
    assert res.status_code == 400
    assert "source dataset CRS is missing" in res.json()["detail"]


def test_get_file_geojson_not_found(isolated_storage, client: TestClient) -> None:
    """Verify non-existent file ID returns 404."""
    random_id = str(uuid4())
    res = client.get(f"/api/files/{random_id}/geojson")
    assert res.status_code == 404
    assert f"File with ID '{random_id}' not found" in res.json()["detail"]


def test_get_file_geojson_trailing_slash_supported(isolated_storage, client: TestClient) -> None:
    """Verify trailing slash alias /{file_id}/geojson/ works identically."""
    upload_res = client.post(
        "/api/files/",
        files={"file": ("test.kml", io.BytesIO(create_valid_kml_bytes()), "application/vnd.google-earth.kml+xml")},
    )
    file_id = upload_res.json()["id"]

    res = client.get(f"/api/files/{file_id}/geojson/")
    assert res.status_code == 200
    assert res.json()["type"] == "FeatureCollection"
