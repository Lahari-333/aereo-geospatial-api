"""Shared test fixtures for AEREO Geospatial File Measurement API tests."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings
from app.main import app
from app.storage.database import Base, get_db


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
