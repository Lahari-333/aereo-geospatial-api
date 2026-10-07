"""Tests for multi-file batch upload endpoint (POST /api/files/batch/)."""

import io
from fastapi.testclient import TestClient

from tests.fixtures import (
    create_malformed_kml_bytes,
    create_valid_kml_bytes,
    create_valid_shapefile_zip_bytes,
)


def test_batch_upload_multiple_valid_files(isolated_storage, client: TestClient) -> None:
    """Verify batch upload of multiple valid geospatial files (KML + Shapefile ZIP)."""
    kml_bytes = create_valid_kml_bytes()
    zip_bytes = create_valid_shapefile_zip_bytes()

    files = [
        ("files", ("survey1.kml", io.BytesIO(kml_bytes), "application/vnd.google-earth.kml+xml")),
        ("files", ("parcels.zip", io.BytesIO(zip_bytes), "application/zip")),
    ]

    response = client.post("/api/files/batch/", files=files)
    assert response.status_code == 200

    data = response.json()
    assert data["total_files"] == 2
    assert data["successful"] == 2
    assert data["failed"] == 0
    assert data["total_processing_time_ms"] > 0
    assert len(data["results"]) == 2

    # Check first item (KML)
    r1 = data["results"][0]
    assert r1["filename"] == "survey1.kml"
    assert r1["status"] == "COMPLETED"
    assert r1["file_id"] is not None
    assert r1["feature_count"] == 1

    # Check second item (ZIP)
    r2 = data["results"][1]
    assert r2["filename"] == "parcels.zip"
    assert r2["status"] == "COMPLETED"
    assert r2["file_id"] is not None
    assert r2["spatial_summary"]["total_area_sqm"] > 0

    # Verify both records are queryable in database
    list_res = client.get("/api/files/")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 2


def test_batch_upload_fault_isolation(isolated_storage, client: TestClient) -> None:
    """Verify fault isolation: a corrupt file or bad format does not fail valid files."""
    valid_kml = create_valid_kml_bytes()
    bad_kml = create_malformed_kml_bytes()
    unsupported = b"dummy text content"

    files = [
        ("files", ("good.kml", io.BytesIO(valid_kml), "application/vnd.google-earth.kml+xml")),
        ("files", ("corrupt.kml", io.BytesIO(bad_kml), "application/vnd.google-earth.kml+xml")),
        ("files", ("invalid.txt", io.BytesIO(unsupported), "text/plain")),
    ]

    response = client.post("/api/files/batch/", files=files)
    assert response.status_code == 200

    data = response.json()
    assert data["total_files"] == 3
    assert data["successful"] == 1
    assert data["failed"] == 2

    results = data["results"]
    assert results[0]["filename"] == "good.kml"
    assert results[0]["status"] == "COMPLETED"

    assert results[1]["filename"] == "corrupt.kml"
    assert results[1]["status"] == "FAILED"
    assert "Malformed or unreadable KML" in results[1]["error"]

    assert results[2]["filename"] == "invalid.txt"
    assert results[2]["status"] == "FAILED"
    assert "Unsupported file extension" in results[2]["error"]

    # Verify only the single valid file was saved in the database
    list_res = client.get("/api/files/")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1
    assert list_res.json()["files"][0]["filename"] == "good.kml"


def test_batch_upload_exceeds_max_limit(isolated_storage, client: TestClient) -> None:
    """Verify batch exceeding the MAX_BATCH_FILES limit (10) returns 400."""
    valid_kml = create_valid_kml_bytes()
    files = [
        ("files", (f"file_{i}.kml", io.BytesIO(valid_kml), "application/vnd.google-earth.kml+xml"))
        for i in range(11)
    ]

    response = client.post("/api/files/batch/", files=files)
    assert response.status_code == 400
    assert "exceeds maximum limit of 10" in response.json()["detail"]


def test_batch_upload_empty_list_rejected(isolated_storage, client: TestClient) -> None:
    """Verify batch upload with no files returns 400."""
    response = client.post("/api/files/batch/", files=[])
    assert response.status_code in (400, 422)


def test_batch_upload_trailing_slash_support(isolated_storage, client: TestClient) -> None:
    """Verify /api/files/batch without trailing slash also works."""
    valid_kml = create_valid_kml_bytes()
    files = [
        ("files", ("survey.kml", io.BytesIO(valid_kml), "application/vnd.google-earth.kml+xml")),
    ]

    response = client.post("/api/files/batch", files=files)
    assert response.status_code == 200
    assert response.json()["successful"] == 1
