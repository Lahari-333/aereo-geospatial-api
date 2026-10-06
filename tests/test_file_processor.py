"""Unit tests for GeospatialFileProcessor verifying parsing, security, and extraction."""

import io
from pathlib import Path
import uuid
import zipfile
import pytest

from app.core.config import Settings
from app.services.file_processor import (
    CorruptFileError,
    GeospatialFileProcessor,
    InvalidShapefileError,
    ZipSecurityError,
)
from tests.fixtures import (
    create_empty_kml_bytes,
    create_invalid_zip_bytes,
    create_malformed_kml_bytes,
    create_valid_kml_bytes,
    create_valid_shapefile_zip_bytes,
    create_zip_with_multiple_shapefiles_bytes,
    create_zip_with_path_traversal_bytes,
    create_zip_without_shapefile_bytes,
)


@pytest.fixture
def processor(tmp_path: Path):
    """Instantiate a GeospatialFileProcessor with isolated paths."""
    test_settings = Settings(
        UPLOAD_DIR=tmp_path / "uploads",
        PROCESSED_DIR=tmp_path / "processed",
        MAX_ZIP_MEMBERS=10,
        MAX_ZIP_UNCOMPRESSED_SIZE_MB=5,
    )
    test_settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    test_settings.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    return GeospatialFileProcessor(settings=test_settings), test_settings


def test_valid_kml_processing(processor, tmp_path: Path) -> None:
    """Verify that a valid KML file is parsed and features/metadata extracted."""
    proc, _ = processor
    kml_path = tmp_path / "sample.kml"
    kml_path.write_bytes(create_valid_kml_bytes())

    file_id = uuid.uuid4()
    result = proc.process_file(file_path=kml_path, file_type="kml", file_id=file_id)

    assert result.file_id == file_id
    assert result.file_type == "kml"
    assert result.feature_count == 1
    assert "Point" in result.geometry_types
    assert result.crs == "EPSG:4326"
    assert not result.has_missing_crs

    feature = result.features[0]
    assert feature.feature_id == 0
    assert feature.geometry_type == "Point"
    assert feature.geometry["type"] == "Point"
    assert len(feature.geometry["coordinates"]) >= 2
    assert feature.properties["Name"] == "Test Point"
    assert feature.is_valid
    assert not feature.is_empty


def test_valid_shapefile_zip_processing(processor, tmp_path: Path) -> None:
    """Verify that a valid Shapefile ZIP is safely extracted, parsed, and cleaned up."""
    proc, settings = processor
    zip_path = tmp_path / "shapefile.zip"
    zip_path.write_bytes(create_valid_shapefile_zip_bytes(include_prj=True))

    file_id = uuid.uuid4()
    result = proc.process_file(file_path=zip_path, file_type="zip", file_id=file_id)

    assert result.file_id == file_id
    assert result.file_type == "zip"
    assert result.feature_count == 1
    assert "Polygon" in result.geometry_types
    assert result.crs == "EPSG:4326"
    assert not result.has_missing_crs

    feature = result.features[0]
    assert feature.feature_id == 0
    assert feature.geometry_type == "Polygon"
    assert feature.geometry["type"] == "Polygon"
    assert feature.properties["name"] == "Zone A"
    assert feature.properties["id"] == 101

    # Verify temporary extraction directory was cleaned up
    assert len(list(settings.PROCESSED_DIR.iterdir())) == 0


def test_malformed_kml_fails_cleanly(processor, tmp_path: Path) -> None:
    """Verify malformed KML raises CorruptFileError with informative detail."""
    proc, _ = processor
    bad_kml = tmp_path / "broken.kml"
    bad_kml.write_bytes(create_malformed_kml_bytes())

    with pytest.raises(CorruptFileError) as exc_info:
        proc.process_file(file_path=bad_kml, file_type="kml", file_id=uuid.uuid4())

    assert "Malformed or unreadable KML" in str(exc_info.value)


def test_invalid_zip_fails_cleanly(processor, tmp_path: Path) -> None:
    """Verify corrupted ZIP archive raises CorruptFileError."""
    proc, _ = processor
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(create_invalid_zip_bytes())

    with pytest.raises(CorruptFileError) as exc_info:
        proc.process_file(file_path=corrupt_zip, file_type="zip", file_id=uuid.uuid4())

    assert "Invalid or corrupted ZIP" in str(exc_info.value)


def test_zip_without_shapefile_fails_cleanly(processor, tmp_path: Path) -> None:
    """Verify ZIP containing no .shp file raises InvalidShapefileError."""
    proc, settings = processor
    no_shp_zip = tmp_path / "no_shp.zip"
    no_shp_zip.write_bytes(create_zip_without_shapefile_bytes())

    with pytest.raises(InvalidShapefileError) as exc_info:
        proc.process_file(file_path=no_shp_zip, file_type="zip", file_id=uuid.uuid4())

    assert "does not contain an ESRI Shapefile" in str(exc_info.value)
    # Ensure extraction directory was cleaned
    assert len(list(settings.PROCESSED_DIR.iterdir())) == 0


def test_zip_with_multiple_shapefiles_handled_deliberately(processor, tmp_path: Path) -> None:
    """Verify ZIP with multiple Shapefiles is rejected with an explicit error."""
    proc, settings = processor
    multi_zip = tmp_path / "multi.zip"
    multi_zip.write_bytes(create_zip_with_multiple_shapefiles_bytes())

    with pytest.raises(InvalidShapefileError) as exc_info:
        proc.process_file(file_path=multi_zip, file_type="zip", file_id=uuid.uuid4())

    assert "Multiple Shapefiles found" in str(exc_info.value)
    assert len(list(settings.PROCESSED_DIR.iterdir())) == 0


def test_zip_slip_path_traversal_blocked(processor, tmp_path: Path) -> None:
    """Verify path traversal entries in ZIP archives trigger ZipSecurityError."""
    proc, settings = processor
    evil_zip = tmp_path / "evil.zip"
    evil_zip.write_bytes(create_zip_with_path_traversal_bytes())

    with pytest.raises(ZipSecurityError) as exc_info:
        proc.process_file(file_path=evil_zip, file_type="zip", file_id=uuid.uuid4())

    assert "Path traversal rejected" in str(exc_info.value)
    assert len(list(settings.PROCESSED_DIR.iterdir())) == 0


def test_zip_bomb_member_limit_enforced(processor, tmp_path: Path) -> None:
    """Verify archive member count limits are enforced."""
    proc, settings = processor
    bomb_zip = tmp_path / "many_files.zip"

    # Settings limit is 10 members in fixture
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(15):
            zf.writestr(f"file_{i}.txt", "data")
    bomb_zip.write_bytes(buf.getvalue())

    with pytest.raises(ZipSecurityError) as exc_info:
        proc.process_file(file_path=bomb_zip, file_type="zip", file_id=uuid.uuid4())

    assert "exceeding the limit" in str(exc_info.value)


def test_missing_crs_detected_explicitly(processor, tmp_path: Path) -> None:
    """Verify Shapefile without .prj metadata is processed with None CRS and flag set."""
    proc, _ = processor
    no_prj_zip = tmp_path / "no_prj.zip"
    no_prj_zip.write_bytes(create_valid_shapefile_zip_bytes(include_prj=False))

    result = proc.process_file(file_path=no_prj_zip, file_type="zip", file_id=uuid.uuid4())

    assert result.crs is None
    assert result.has_missing_crs is True
    assert result.feature_count == 1


def test_empty_kml_dataset_handled_safely(processor, tmp_path: Path) -> None:
    """Verify KML with 0 Placemarks produces zero features without error."""
    proc, _ = processor
    empty_kml = tmp_path / "empty.kml"
    empty_kml.write_bytes(create_empty_kml_bytes())

    result = proc.process_file(file_path=empty_kml, file_type="kml", file_id=uuid.uuid4())

    assert result.feature_count == 0
    assert result.geometry_types == []
    assert len(result.features) == 0
