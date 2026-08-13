from typing import Optional
from fastapi import UploadFile

from core.config import settings
from core.exceptions import (
    FileTooLargeException,
    InvalidFileExtensionException,
    InvalidMimeTypeException,
)

# MIME type magic bytes — first bytes of a file identify its real type.
# This prevents a renamed file attack (e.g. script.exe renamed to book.pdf).
_MAGIC_BYTES: dict[str, bytes] = {
    "application/pdf": b"%PDF"
}

MAX_FILE_SIZE_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


def get_file_extension(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    if len(parts) < 2:
        return ""
    return parts[1].lower()


def validate_extension(filename: str) -> str:
    ext = get_file_extension(filename)
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise InvalidFileExtensionException(
            f"File type '.{ext}' is not allowed. "
            f"Accepted: {', '.join('.' + e for e in settings.ALLOWED_EXTENSIONS)}"
        )
    return ext


def validate_content_type(content_type: Optional[str]) -> str:
    if not content_type or content_type not in settings.ALLOWED_MIME_TYPES:
        raise InvalidMimeTypeException(
            f"Content-Type '{content_type}' is not allowed. "
            f"Accepted: {', '.join(settings.ALLOWED_MIME_TYPES)}"
        )
    return content_type


def validate_magic_bytes(file_bytes: bytes, expected_content_type: str) -> None:
    """
    Verify the actual file contents match the declared content type.
    Catches renamed files — e.g. a .exe renamed to .pdf.
    """
    magic = _MAGIC_BYTES.get(expected_content_type)
    if magic and not file_bytes.startswith(magic):
        raise InvalidMimeTypeException(
            "File contents do not match the declared file type"
        )


def validate_size(file_bytes: bytes) -> None:
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeException(
            f"File size exceeds the {settings.MAX_FILE_SIZE_MB}MB limit"
        )


async def validate_upload(file: UploadFile) -> tuple[bytes, str, str]:
    """
    Full validation pipeline for an uploaded file.
    Returns (file_bytes, extension, content_type) if all checks pass.
    Raises an appropriate LibraryException otherwise.

    Usage in a route handler:
        file_bytes, ext, content_type = await validate_upload(file)
    """
    validate_extension(file.filename or "")
    content_type = validate_content_type(file.content_type)

    file_bytes = await file.read()

    validate_size(file_bytes)
    validate_magic_bytes(file_bytes, content_type)

    return file_bytes, get_file_extension(file.filename or ""), content_type