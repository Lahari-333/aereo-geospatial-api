from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Application settings and configuration."""

    APP_NAME: str = "Geospatial File Measurement API"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Storage paths
    BASE_DIR: Path = BASE_DIR
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    PROCESSED_DIR: Path = BASE_DIR / "processed"

    # Database connection URL
    DATABASE_URL: str = f"sqlite:///{BASE_DIR.as_posix()}/geospatial.db"

    # File upload configurations
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: set[str] = {".kml", ".zip"}

    # ZIP extraction & security limits
    MAX_ZIP_MEMBERS: int = 100
    MAX_ZIP_UNCOMPRESSED_SIZE_MB: int = 100

    @property
    def max_upload_size_bytes(self) -> int:
        """Return maximum upload size in bytes."""
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def max_zip_uncompressed_size_bytes(self) -> int:
        """Return maximum uncompressed ZIP size in bytes."""
        return self.MAX_ZIP_UNCOMPRESSED_SIZE_MB * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    settings = Settings()
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    return settings
