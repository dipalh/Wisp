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
    ".gif":  "image/gif",
    ".ico":  "image/x-icon",
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
    ".tex":  "text/plain",
    ".sol":  "text/plain",
    ".wl":   "text/plain",
    ".mermaid": "text/plain",
    ".r":    "text/plain",
    ".lua":  "text/plain",
    ".pl":   "text/plain",
    ".zig":  "text/plain",
    ".h":    "text/plain",
    ".hpp":  "text/plain",
    ".m":    "text/plain",
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
TEXT_LIKE_EXTENSIONS = {
    ".txt", ".md", ".html", ".htm", ".css", ".csv", ".xml", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".log", ".sql",
    ".reg", ".nfo", ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c",
    ".cpp", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".sh", ".bash",
    ".bat", ".cmd", ".ps1", ".psm1", ".psd1", ".vbs", ".eml", ".ics", ".vcf",
    ".tex", ".sol", ".wl", ".mermaid", ".r", ".lua", ".pl", ".zig",
    ".h", ".hpp", ".m",
}


def _category_for_ext(ext: str) -> str:
    if ext == ".txt":
        return "text"
    if ext in OFFICE_MIME_TYPES:
        return "office"
    if ext in ARCHIVE_MIME_TYPES:
        return "archive"
    if ext in EXECUTABLE_MIME_TYPES:
        return "binary"
    if ext in TEXT_LIKE_EXTENSIONS:
        return "text"
    if ext in VIDEO_EXTENSIONS or ext in {".wav", ".mp3", ".aiff", ".aac", ".ogg", ".flac", ".m4a", ".opus"}:
        return "media"
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".svg", ".gif", ".ico"}:
        return "image"
    return "document"


def _build_result(filename: str, mime_type: str, content: str, engine_used: str, ext: str, fallback_used: bool = False, errors: list[str] | None = None) -> ContentResult:
    return ContentResult(
        filename=filename,
        file_name=filename,
        mime_type=mime_type,
        category=_category_for_ext(ext),
        content=content,
        text=content,
        engine_used=engine_used,
        fallback_used=fallback_used,
        errors=errors or [],
    )


def _fake_gemini_content(file_bytes: bytes, ext: str, filename: str) -> str:
    normalized_ext = ext.lstrip(".")
    if ext in TEXT_LIKE_EXTENSIONS:
        preview = file_bytes.decode("utf-8", errors="replace").strip()
        if preview:
            return f"DEMO_EXTRACT:{normalized_ext}:{preview[:80]}"
    return f"DEMO_EXTRACT:{normalized_ext}:{filename}"


def _extract_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="replace")


async def extract(file_bytes: bytes, filename: str) -> ContentResult:
    from pathlib import Path
    ext = Path(filename).suffix.lower()

    # ── Plain text & code — read locally, no API call needed ──────────────
    if ext in TEXT_LIKE_EXTENSIONS:
        try:
            content = _extract_txt(file_bytes)
            mime = GEMINI_MIME_TYPES.get(ext, "text/plain")
            return _build_result(filename, mime, content, engine_used="local", ext=ext)
        except Exception:
            return _build_result(
                filename,
                GEMINI_MIME_TYPES.get(ext, "text/plain"),
                _fake_gemini_content(file_bytes, ext, filename),
                engine_used="fake",
                ext=ext,
                fallback_used=True,
            )

    if ext in OFFICE_MIME_TYPES:
        content = office.extract(file_bytes, ext)
        return _build_result(filename, OFFICE_MIME_TYPES[ext], content, engine_used="local", ext=ext)

    if ext in ARCHIVE_MIME_TYPES:
        content = archive.extract(file_bytes, ext)
        return _build_result(filename, ARCHIVE_MIME_TYPES[ext], content, engine_used="local", ext=ext)

    if ext in EXECUTABLE_MIME_TYPES:
        content = binary.extract(file_bytes, ext)
        return _build_result(filename, EXECUTABLE_MIME_TYPES[ext], content, engine_used="local", ext=ext)

    if ext in GEMINI_MIME_TYPES:
        mime_type = GEMINI_MIME_TYPES[ext]
        force_files_api = ext in VIDEO_EXTENSIONS
        try:
            content = await gemini.extract(file_bytes, mime_type, ext, force_files_api=force_files_api)
            return _build_result(filename, mime_type, content, engine_used="gemini", ext=ext)
        except Exception:
            return _build_result(
                filename,
                mime_type,
                _fake_gemini_content(file_bytes, ext, filename),
                engine_used="fake",
                ext=ext,
                fallback_used=True,
            )

    # ── Unknown / unsupported — try reading as text, else return stub ─────
    try:
        content = file_bytes.decode("utf-8")
        if content.strip():
            return _build_result(filename, "text/plain", content, engine_used="local-guess", ext=ext)
    except (UnicodeDecodeError, ValueError):
        pass

    return _build_result(
        filename,
        "application/octet-stream",
        f"[Binary file: {filename}]",
        engine_used="stub",
        ext=ext,
    )
