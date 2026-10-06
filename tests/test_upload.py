"""Automated tests for the geospatial file upload endpoint (POST /api/files/)."""

import io
from pathlib import Path
import uuid
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


@pytest.fixture
def isolated_storage(tmp_path: Path):
    """Fixture providing isolated upload directory and customized settings for testing."""
    test_upload_dir = tmp_path / "test_uploads"
    test_upload_dir.mkdir(parents=True, exist_ok=True)

    # Use a small 1 MB limit to easily test file size boundaries
    test_settings = Settings(
        UPLOAD_DIR=test_upload_dir,
        MAX_UPLOAD_SIZE_MB=1,
    )

    app.dependency_overrides[get_settings] = lambda: test_settings
    yield test_upload_dir, test_settings
    app.dependency_overrides.clear()


@pytest.fixture
def client(isolated_storage):
    """FastAPI TestClient with isolated settings active."""
    return TestClient(app)


def test_successful_kml_upload(isolated_storage, client: TestClient) -> None:
    """1. Verify successful upload of a .kml file."""
    upload_dir, _ = isolated_storage
    kml_content = b"<?xml version=\"1.0\" encoding=\"UTF-8\"?><kml><Placemark></Placemark></kml>"

    response = client.post(
        "/api/files/",
        files={"file": ("test_polygon.kml", io.BytesIO(kml_content), "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "test_polygon.kml"
    assert data["file_type"] == "kml"
    assert data["size_bytes"] == len(kml_content)
    assert data["status"] == "UPLOADED"
    assert "id" in data
    assert data["stored_filename"].endswith(".kml")


def test_successful_zip_upload(isolated_storage, client: TestClient) -> None:
    """2. Verify successful upload of a .zip file."""
    upload_dir, _ = isolated_storage
    # Create in-memory zip archive
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("test.shp", b"fake shapefile data")
    zip_bytes = zip_buffer.getvalue()

    response = client.post(
        "/api/files/",
        files={"file": ("shapefile_archive.zip", io.BytesIO(zip_bytes), "application/zip")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "shapefile_archive.zip"
    assert data["file_type"] == "zip"
    assert data["size_bytes"] == len(zip_bytes)
    assert data["status"] == "UPLOADED"
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
    # Ensure no empty files were left on disk
    assert len(list(upload_dir.iterdir())) == 0


def test_file_exceeding_size_limit(isolated_storage, client: TestClient) -> None:
    """5. Verify rejection of files exceeding the configured maximum size limit (1 MB in test settings)."""
    upload_dir, _ = isolated_storage
    # 1.2 MB file exceeds the 1 MB test limit
    oversized_data = b"X" * int(1.2 * 1024 * 1024)

    response = client.post(
        "/api/files/",
        files={"file": ("oversized.kml", io.BytesIO(oversized_data), "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 413
    assert "exceeds maximum allowed upload size" in response.json()["detail"]
    # Ensure the partially written file was cleaned up
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
    response = client.post(
        "/api/files/",
        files={"file": (variant_name, io.BytesIO(b"valid content dummy"), "application/octet-stream")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["file_type"] == expected_type
    assert data["stored_filename"].endswith(f".{expected_type}")


def test_path_traversal_filename_sanitization(isolated_storage, client: TestClient) -> None:
    """7. Verify protection against path traversal in filenames."""
    upload_dir, _ = isolated_storage
    traversal_name = "../../etc/malicious.kml"

    response = client.post(
        "/api/files/",
        files={"file": (traversal_name, io.BytesIO(b"<kml></kml>"), "application/vnd.google-earth.kml+xml")},
    )

    assert response.status_code == 201
    data = response.json()
    # The filename should be sanitized to base name only
    assert data["filename"] == "malicious.kml"
    # The stored file must be safely housed in upload_dir, not traversed
    stored_path = upload_dir / data["stored_filename"]
    assert stored_path.exists()
    assert stored_path.is_file()


def test_stored_file_actually_exists(isolated_storage, client: TestClient) -> None:
    """8. Verify that the file is actually written to disk with exact contents."""
    upload_dir, _ = isolated_storage
    content = b"<kml><Placemark><name>Point</name></Placemark></kml>"

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
        files={"file": ("my_sensitive_project_name.kml", io.BytesIO(b"<kml></kml>"), "application/octet-stream")},
    )

    assert response.status_code == 201
    data = response.json()
    stored_filename = data["stored_filename"]
    assert "my_sensitive_project_name" not in stored_filename
    # Stem must be a valid UUID
    uuid_part = stored_filename.replace(".kml", "")
    parsed_uuid = uuid.UUID(uuid_part)
    assert str(parsed_uuid) == data["id"]


def test_response_does_not_expose_absolute_path(isolated_storage, client: TestClient) -> None:
    """10. Verify response does not leak internal filesystem paths or drive details."""
    upload_dir, _ = isolated_storage

    response = client.post(
        "/api/files/",
        files={"file": ("check_leak.kml", io.BytesIO(b"<kml></kml>"), "application/octet-stream")},
    )

    assert response.status_code == 201
    response_body = response.text
    # Should not expose directory path
    assert str(upload_dir) not in response_body
    assert "C:" not in response_body
    assert "Users" not in response_body
