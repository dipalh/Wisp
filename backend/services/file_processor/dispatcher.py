from services.file_processor.models import ContentResult
from services.file_processor.extractors import gemini, office, archive, binary

# ── Gemini-native types ───────────────────────────────────────────────────────
GEMINI_MIME_TYPES: dict[str, str] = {
    # Images
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".svg":  "image/svg+xml",
    # Video
    ".mp4":  "video/mp4",
    ".mpeg": "video/mpeg",
    ".mpg":  "video/mpg",
    ".mov":  "video/mov",
    ".avi":  "video/avi",
    ".flv":  "video/x-flv",
    ".webm": "video/webm",
    ".wmv":  "video/wmv",
    ".3gp":  "video/3gpp",
    # Audio
    ".wav":  "audio/wav",
    ".mp3":  "audio/mp3",
    ".aiff": "audio/aiff",
    ".aac":  "audio/aac",
    ".ogg":  "audio/ogg",
    ".flac": "audio/flac",
    ".m4a":  "audio/m4a",
    ".opus": "audio/opus",
    # Documents (Gemini-native)
    ".pdf":  "application/pdf",
    ".rtf":  "text/rtf",
    # Plain text & markup
    ".txt":  "text/plain",
    ".md":   "text/plain",
    ".html": "text/html",
    ".htm":  "text/html",
    ".css":  "text/css",
    ".csv":  "text/csv",
    ".xml":  "text/xml",
    ".json": "application/json",
    # Config & data
    ".yaml": "text/plain",
    ".yml":  "text/plain",
    ".toml": "text/plain",
    ".ini":  "text/plain",
    ".cfg":  "text/plain",
    ".conf": "text/plain",
    ".log":  "text/plain",
    ".sql":  "text/plain",
    ".reg":  "text/plain",
    ".nfo":  "text/plain",
    # Scripts & code
    ".py":   "text/plain",
    ".js":   "text/plain",
    ".ts":   "text/plain",
    ".tsx":  "text/plain",
    ".jsx":  "text/plain",
    ".java": "text/plain",
    ".c":    "text/plain",
    ".cpp":  "text/plain",
    ".go":   "text/plain",
    ".rs":   "text/plain",
    ".rb":   "text/plain",
    ".php":  "text/plain",
    ".swift":"text/plain",
    ".kt":   "text/plain",
    ".sh":   "text/plain",
    ".bash": "text/plain",
    # Windows scripts
    ".bat":  "text/plain",
    ".cmd":  "text/plain",
    ".ps1":  "text/plain",
    ".psm1": "text/plain",
    ".psd1": "text/plain",
    ".vbs":  "text/plain",
    # Personal data (text-based formats)
    ".eml":  "text/plain",
    ".ics":  "text/plain",
    ".vcf":  "text/plain",
}

# ── Modern OpenXML + OpenDocument office formats ──────────────────────────────
OFFICE_MIME_TYPES: dict[str, str] = {
    # Modern OpenXML
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Legacy binary Office
    ".doc":  "application/msword",
    ".ppt":  "application/vnd.ms-powerpoint",
    ".xls":  "application/vnd.ms-excel",
    # OpenDocument
    ".odt":  "application/vnd.oasis.opendocument.text",
    ".odp":  "application/vnd.oasis.opendocument.presentation",
    ".ods":  "application/vnd.oasis.opendocument.spreadsheet",
}

# ── Archive formats ───────────────────────────────────────────────────────────
ARCHIVE_MIME_TYPES: dict[str, str] = {
    ".zip":  "application/zip",
    ".7z":   "application/x-7z-compressed",
    ".tar":  "application/x-tar",
    ".tgz":  "application/x-tar",
    ".gz":   "application/gzip",
    ".bz2":  "application/x-bzip2",
    ".xz":   "application/x-xz",
}

# ── Executables & installers ──────────────────────────────────────────────────
EXECUTABLE_MIME_TYPES: dict[str, str] = {
    ".exe":  "application/x-msdownload",
    ".dll":  "application/x-msdownload",
    ".msi":  "application/x-msi",
}

ALL_MIME_TYPES: dict[str, str] = {
    **GEMINI_MIME_TYPES,
    **OFFICE_MIME_TYPES,
    **ARCHIVE_MIME_TYPES,
    **EXECUTABLE_MIME_TYPES,
}

VIDEO_EXTENSIONS = {".mp4", ".mpeg", ".mpg", ".mov", ".avi", ".flv", ".webm", ".wmv", ".3gp"}


async def extract(file_bytes: bytes, filename: str) -> ContentResult:
    from pathlib import Path
    ext = Path(filename).suffix.lower()

    if ext in OFFICE_MIME_TYPES:
        content = office.extract(file_bytes, ext)
        return ContentResult(filename=filename, mime_type=OFFICE_MIME_TYPES[ext], content=content)

    if ext in ARCHIVE_MIME_TYPES:
        content = archive.extract(file_bytes, ext)
        return ContentResult(filename=filename, mime_type=ARCHIVE_MIME_TYPES[ext], content=content)

    if ext in EXECUTABLE_MIME_TYPES:
        content = binary.extract(file_bytes, ext)
        return ContentResult(filename=filename, mime_type=EXECUTABLE_MIME_TYPES[ext], content=content)

    if ext in GEMINI_MIME_TYPES:
        mime_type = GEMINI_MIME_TYPES[ext]
        force_files_api = ext in VIDEO_EXTENSIONS
        content = await gemini.extract(file_bytes, mime_type, ext, force_files_api=force_files_api)
        return ContentResult(filename=filename, mime_type=mime_type, content=content)

    raise ValueError(
        f"Unsupported file type '{ext}'. "
        f"Supported: {', '.join(sorted(ALL_MIME_TYPES))}"
    )
