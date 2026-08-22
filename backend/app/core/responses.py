from pathlib import Path

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.storage.base import StoredFile

PRIVATE_FILE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; sandbox",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Download-Options": "noopen",
}


def private_file_response(
    file: str | Path | StoredFile, *, filename: str, media_type: str
) -> FileResponse:
    """Return an authenticated private object as a forced, non-cacheable download."""
    stored = file if isinstance(file, StoredFile) else StoredFile(Path(file))
    background = BackgroundTask(stored.path.unlink, missing_ok=True) if stored.temporary else None
    return FileResponse(
        stored.path,
        filename=filename,
        media_type=media_type,
        content_disposition_type="attachment",
        headers=PRIVATE_FILE_HEADERS,
        background=background,
    )
