"""Service responsible for validating, streaming, and securely persisting uploaded files."""

from pathlib import Path
import uuid
from fastapi import HTTPException, UploadFile, status

from app.core.config import Settings
from app.schemas.file import FileUploadResponse

# 1 MB chunk size for streaming file writes to prevent memory exhaustion
STREAM_CHUNK_SIZE = 1024 * 1024


class UploadService:
    """Handles upload validation, filename sanitization, and secure chunked storage."""

    def __init__(self, settings: Settings) -> None:
        self.upload_dir = settings.UPLOAD_DIR
        self.max_size_bytes = settings.max_upload_size_bytes
        self.max_size_mb = settings.MAX_UPLOAD_SIZE_MB
        self.allowed_extensions = settings.ALLOWED_EXTENSIONS

    def validate_filename_and_type(self, raw_filename: str | None) -> tuple[str, str]:
        """Validate filename and ensure extension is supported (case-insensitive).

        Returns:
            Tuple of (sanitized_original_filename, normalized_file_type)
        """
        if not raw_filename or not raw_filename.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename cannot be empty.",
            )

        # Sanitize original filename by extracting only the base name (defense against path traversal)
        sanitized_name = Path(raw_filename).name
        if not sanitized_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid filename supplied.",
            )

        suffix = Path(sanitized_name).suffix.lower()
        if not suffix or suffix not in self.allowed_extensions:
            allowed_list = ", ".join(sorted(self.allowed_extensions))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file extension '{suffix}'. Allowed extensions: {allowed_list}",
            )

        file_type = suffix.lstrip(".")
        return sanitized_name, file_type

    async def save_uploaded_file(self, file: UploadFile) -> FileUploadResponse:
        """Stream uploaded file to disk with size verification and secure UUID naming."""
        sanitized_filename, file_type = self.validate_filename_and_type(file.filename)

        file_id = uuid.uuid4()
        stored_filename = f"{file_id}.{file_type}"
        destination_path = self.upload_dir / stored_filename

        bytes_written = 0

        try:
            with open(destination_path, "wb") as buffer:
                while chunk := await file.read(STREAM_CHUNK_SIZE):
                    bytes_written += len(chunk)
                    if bytes_written > self.max_size_bytes:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail=f"File exceeds maximum allowed upload size of {self.max_size_mb} MB.",
                        )
                    buffer.write(chunk)

            if bytes_written == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file is empty (0 bytes).",
                )

        except Exception:
            # Clean up partially written file if an exception occurred
            if destination_path.exists():
                destination_path.unlink()
            raise

        return FileUploadResponse(
            id=file_id,
            filename=sanitized_filename,
            stored_filename=stored_filename,
            file_type=file_type,
            size_bytes=bytes_written,
            status="UPLOADED",
        )
