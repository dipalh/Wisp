import bz2
import gzip
import io
import lzma
import zipfile


def extract(file_bytes: bytes, ext: str) -> str:
    if ext == ".zip":
        return _extract_zip(file_bytes)
    if ext == ".7z":
        return _extract_7z(file_bytes)
    if ext in (".tar", ".tgz"):
        return _extract_tar(file_bytes, ext)
    if ext == ".gz":
        return _decompress_single(file_bytes, gzip.decompress, ".gz")
    if ext == ".bz2":
        return _decompress_single(file_bytes, bz2.decompress, ".bz2")
    if ext == ".xz":
        return _decompress_single(file_bytes, lzma.decompress, ".xz")
    raise ValueError(f"Unsupported archive format: {ext}")


def _extract_zip(file_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        names = zf.namelist()
    return f"ZIP archive containing {len(names)} file(s):\n" + "\n".join(names)


def _extract_7z(file_bytes: bytes) -> str:
    import py7zr

    with py7zr.SevenZipFile(io.BytesIO(file_bytes)) as zf:
        names = zf.getnames()
    return f"7-Zip archive containing {len(names)} file(s):\n" + "\n".join(names)


def _extract_tar(file_bytes: bytes, ext: str) -> str:
    import tarfile

    mode = "r:gz" if ext == ".tgz" else "r:*"
    with tarfile.open(fileobj=io.BytesIO(file_bytes), mode=mode) as tf:
        names = tf.getnames()
    return f"TAR archive containing {len(names)} file(s):\n" + "\n".join(names)


def _decompress_single(file_bytes: bytes, decompress_fn, ext: str) -> str:
    """For standalone .gz/.bz2/.xz — usually a compressed text/log file."""
    try:
        content = decompress_fn(file_bytes)
        return content.decode("utf-8", errors="replace")
    except Exception:
        return f"Compressed binary file ({ext})"
