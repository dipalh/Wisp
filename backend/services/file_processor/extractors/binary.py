import io


def extract(file_bytes: bytes, ext: str) -> str:
    if ext in (".exe", ".dll"):
        return _extract_pe(file_bytes, ext)
    if ext == ".msi":
        return _extract_msi(file_bytes)
    raise ValueError(f"Unsupported binary format: {ext}")


def _extract_pe(file_bytes: bytes, ext: str) -> str:
    """Extract version/product info from a Windows PE executable or DLL."""
    try:
        import pefile

        pe = pefile.PE(data=file_bytes, fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]]
        )

        fields = {}
        if hasattr(pe, "FileInfo"):
            for file_info in pe.FileInfo:
                for entry in file_info:
                    if hasattr(entry, "StringTable"):
                        for st in entry.StringTable:
                            for k, v in st.entries.items():
                                key = k.decode("utf-8", errors="replace").strip()
                                val = v.decode("utf-8", errors="replace").strip()
                                if key and val:
                                    fields[key] = val

        if not fields:
            return f"Windows {'executable' if ext == '.exe' else 'library'} ({ext})"

        lines = [f"{k}: {v}" for k, v in fields.items()]
        return "\n".join(lines)
    except Exception as e:
        return f"Windows {'executable' if ext == '.exe' else 'library'} ({ext}) — metadata unavailable: {e}"


def _extract_msi(file_bytes: bytes) -> str:
    """Extract SummaryInformation properties from a Windows Installer package."""
    try:
        import olefile

        ole = olefile.OleFileIO(io.BytesIO(file_bytes))
        props = ole.get_metadata()
        lines = []
        for attr in ("title", "subject", "author", "keywords", "comments", "last_saved_by"):
            val = getattr(props, attr, None)
            if val:
                if isinstance(val, bytes):
                    val = val.decode("utf-8", errors="replace")
                lines.append(f"{attr.replace('_', ' ').title()}: {val}")
        ole.close()
        return "\n".join(lines) if lines else "Windows Installer package (.msi)"
    except Exception as e:
        return f"Windows Installer package (.msi) — metadata unavailable: {e}"
