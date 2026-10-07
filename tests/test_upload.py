"""Automated tests for geospatial file upload, queries, and measurement endpoints."""

import io
from pathlib import Path
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.main import app
from app.storage.database import Base, get_db
from tests.fixtures import (
    create_malformed_kml_bytes,
    create_valid_kml_bytes,
    create_valid_shapefile_zip_bytes,
    create_zip_without_shapefile_bytes,
)


@pytest.fixture
def isolated_storage(tmp_path: Path):
    """Fixture providing isolated upload directory, test database, and customized settings."""
    test_upload_dir = tmp_path / "test_uploads"
    test_processed_dir = tmp_path / "test_processed"
    test_upload_dir.mkdir(parents=True, exist_ok=True)
    test_processed_dir.mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "test.db"
    test_db_url = f"sqlite:///{db_path}"

    test_settings = Settings(
        UPLOAD_DIR=test_upload_dir,
        PROCESSED_DIR=test_processed_dir,
        MAX_UPLOAD_SIZE_MB=1,
        DATABASE_URL=test_db_url,
    )

    test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_db] = override_get_db

    yield test_upload_dir, test_settings

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(isolated_storage):
    """FastAPI TestClient with isolated settings active."""
    return TestClient(app)


def test_successful_kml_upload(isolated_storage, client: TestClient) -> None:
    """1. Verify successful upload, processing, and persistence of a valid .kml file."""
    kml_content = create_valid_kml_bytes()

    response = client.post(
        "/api/files/",
        files={"file": ("test_polygon.kml", io.BytesIO(kml_content), "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "test_polygon.kml"
    assert data["file_type"] == "kml"
    assert data["size_bytes"] == len(kml_content)
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 1
    assert "Point" in data["geometry_types"]
    assert data["crs"] == "EPSG:4326"
    assert "id" in data
    assert data["stored_filename"].endswith(".kml")


def test_successful_zip_upload(isolated_storage, client: TestClient) -> None:
    """2. Verify successful upload, processing, and persistence of a valid Shapefile .zip file."""
    zip_bytes = create_valid_shapefile_zip_bytes()

    response = client.post(
        "/api/files/",
        files={"file": ("shapefile_archive.zip", io.BytesIO(zip_bytes), "application/zip")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "shapefile_archive.zip"
    assert data["file_type"] == "zip"
    assert data["size_bytes"] == len(zip_bytes)
    assert data["status"] == "COMPLETED"
    assert data["feature_count"] == 1
    assert "Polygon" in data["geometry_types"]
    assert data["crs"] == "EPSG:4326"
    assert data["stored_filename"].endswith(".zip")


@pytest.mark.parametrize("invalid_name", ["data.txt", "data.csv", "program.exe", "doc.pdf", "image.png"])
def test_unsupported_extension_rejected(isolated_storage, client: TestClient, invalid_name: str) -> None:
    """3. Verify rejection of unsupported file extensions with 400 Bad Request."""
    response = client.post(
        "/api/files/",
        files={"file": (invalid_name, io.BytesIO(b"sample data content"), "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


def test_empty_file_rejected(isolated_storage, client: TestClient) -> None:
    """4. Verify rejection of empty (0-byte) files."""
    upload_dir, _ = isolated_storage

    response = client.post(
        "/api/files/",
        files={"file": ("empty.kml", io.BytesIO(b""), "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()
    assert len(list(upload_dir.iterdir())) == 0


def test_file_exceeding_size_limit(isolated_storage, client: TestClient) -> None:
    """5. Verify rejection of files exceeding the configured maximum size limit (1 MB in test settings)."""
    upload_dir, _ = isolated_storage
    oversized_data = b"X" * int(1.2 * 1024 * 1024)

    response = client.post(
        "/api/files/",
        files={"file": ("oversized.kml", io.BytesIO(oversized_data), "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 413
    assert "exceeds maximum allowed upload size" in response.json()["detail"]
    assert len(list(upload_dir.iterdir())) == 0


@pytest.mark.parametrize(
    "variant_name, expected_type",
    [
        ("UPPERCASE.KML", "kml"),
        ("MixedCase.KmL", "kml"),
        ("UPPERCASE.ZIP", "zip"),
        ("MixedCase.ZiP", "zip"),
    ],
)
def test_case_insensitive_extension(
    isolated_storage, client: TestClient, variant_name: str, expected_type: str
) -> None:
    """6. Verify case-insensitive extension matching."""
    payload = create_valid_kml_bytes() if expected_type == "kml" else create_valid_shapefile_zip_bytes()

    response = client.post(
        "/api/files/",
        files={"file": (variant_name, io.BytesIO(payload), "application/octet-stream")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["file_type"] == expected_type
    assert data["status"] == "COMPLETED"
    assert data["stored_filename"].endswith(f".{expected_type}")


def test_path_traversal_filename_sanitization(isolated_storage, client: TestClient) -> None:
    """7. Verify protection against path traversal in filenames."""
    upload_dir, _ = isolated_storage
    traversal_name = "../../etc/malicious.kml"

    response = client.post(
        "/api/files/",
        files={"file": (traversal_name, io.BytesIO(create_valid_kml_bytes()), "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "malicious.kml"
    stored_path = upload_dir / data["stored_filename"]
    assert stored_path.exists()
    assert stored_path.is_file()


def test_stored_file_actually_exists(isolated_storage, client: TestClient) -> None:
    """8. Verify that the file is actually written to disk with exact contents."""
    upload_dir, _ = isolated_storage
    content = create_valid_kml_bytes()

    response = client.post(
        "/api/files/",
        files={"file": ("real_file.kml", io.BytesIO(content), "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 201
    stored_filename = response.json()["stored_filename"]
    stored_file = upload_dir / stored_filename
    assert stored_file.exists()
    assert stored_file.read_bytes() == content


def test_stored_filename_generated_safely(isolated_storage, client: TestClient) -> None:
    """9. Verify stored filename uses a generated UUID, not the client-provided name."""
    response = client.post(
        "/api/files/",
        files={"file": ("my_sensitive_project_name.kml", io.BytesIO(create_valid_kml_bytes()), "application/octet-stream")},
    )

    assert response.status_code == 201
    data = response.json()
    stored_filename = data["stored_filename"]
    assert "my_sensitive_project_name" not in stored_filename
    uuid_part = stored_filename.replace(".kml", "")
    parsed_uuid = uuid.UUID(uuid_part)
    assert str(parsed_uuid) == data["id"]


def test_response_does_not_expose_absolute_path(isolated_storage, client: TestClient) -> None:
    """10. Verify response does not leak internal filesystem paths or drive details."""
    upload_dir, _ = isolated_storage

    response = client.post(
        "/api/files/",
        files={"file": ("check_leak.kml", io.BytesIO(create_valid_kml_bytes()), "application/octet-stream")},
    )

    assert response.status_code == 201
    response_body = response.text
    assert str(upload_dir) not in response_body
    assert "C:" not in response_body
    assert "Users" not in response_body


def test_malformed_kml_upload_rejected(isolated_storage, client: TestClient) -> None:
    """11. Verify upload of syntactically broken KML returns 400 with clean error."""
    response = client.post(
        "/api/files/",
        files={"file": ("corrupt.kml", io.BytesIO(create_malformed_kml_bytes()), "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 400
    assert "Malformed or unreadable KML" in response.json()["detail"]


def test_zip_without_shapefile_upload_rejected(isolated_storage, client: TestClient) -> None:
    """12. Verify upload of ZIP missing a Shapefile returns 400 with clean error."""
    response = client.post(
        "/api/files/",
        files={"file": ("no_shp.zip", io.BytesIO(create_zip_without_shapefile_bytes()), "application/zip")},
    )
    assert response.status_code == 400
    assert "does not contain an ESRI Shapefile" in response.json()["detail"]


def test_get_file_and_list_files(isolated_storage, client: TestClient) -> None:
    """13. Verify querying file metadata via GET /api/files/ and GET /api/files/{id}."""
    # 1. Initially empty
    list_res = client.get("/api/files/")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 0

    # 2. Upload file
    upload_res = client.post(
        "/api/files/",
        files={"file": ("survey.kml", io.BytesIO(create_valid_kml_bytes()), "application/vnd.google-earth.kml+xml")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["id"]

    # 3. List contains 1 file
    list_res2 = client.get("/api/files/")
    assert list_res2.status_code == 200
    assert list_res2.json()["total"] == 1
    assert list_res2.json()["files"][0]["id"] == file_id

    # 4. Detail endpoint
    detail_res = client.get(f"/api/files/{file_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == file_id
    assert detail["filename"] == "survey.kml"
    assert detail["status"] == "COMPLETED"
    assert detail["feature_count"] == 1
    assert "created_at" in detail


def test_get_file_measurements(isolated_storage, client: TestClient) -> None:
    """14. Verify retrieving feature measurements via GET /api/files/{id}/measurements."""
    # Upload Shapefile ZIP with Polygon in EPSG:4326
    upload_res = client.post(
        "/api/files/",
        files={"file": ("parcels.zip", io.BytesIO(create_valid_shapefile_zip_bytes()), "application/zip")},
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["id"]

    # Query measurements
    meas_res = client.get(f"/api/files/{file_id}/measurements")
    assert meas_res.status_code == 200
    data = meas_res.json()
    assert data["file_id"] == file_id
    assert data["status"] == "COMPLETED"
    assert data["total_features"] == 1
    assert len(data["measurements"]) == 1

    m = data["measurements"][0]
    assert m["feature_id"] == 0
    assert m["geometry_type"] == "Polygon"
    assert m["measurement_type"] == "area"
    assert m["unit"] == "square_meters"
    assert m["value"] > 0
    assert m["source_crs"] == "EPSG:4326"
    assert m["measurement_crs"] is not None


def test_get_file_not_found(isolated_storage, client: TestClient) -> None:
    """15. Verify 404 Not Found for non-existent file IDs."""
    fake_id = str(uuid.uuid4())
    res = client.get(f"/api/files/{fake_id}")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    meas_res = client.get(f"/api/files/{fake_id}/measurements")
    assert meas_res.status_code == 404


def test_delete_file(isolated_storage, client: TestClient) -> None:
    """16. Verify deleting a file removes it from storage and database."""
    upload_dir, _ = isolated_storage
    upload_res = client.post(
        "/api/files/",
        files={"file": ("to_delete.kml", io.BytesIO(create_valid_kml_bytes()), "application/vnd.google-earth.kml+xml")},
    )
    file_id = upload_res.json()["id"]
    stored_name = upload_res.json()["stored_filename"]
    assert (upload_dir / stored_name).exists()

    # Delete
    del_res = client.delete(f"/api/files/{file_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"

    # Confirm removed from disk
    assert not (upload_dir / stored_name).exists()

    # Confirm 404 on subsequent get
    assert client.get(f"/api/files/{file_id}").status_code == 404
