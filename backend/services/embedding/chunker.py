"""
Text chunker for the embedding pipeline.

Strategy (in order of preference):
  1. Split on paragraph boundaries (blank lines).
  2. If a paragraph still exceeds `chunk_size`, split on sentence boundaries.
  3. If a sentence still exceeds `chunk_size`, hard-split with `overlap` carry-over.

Each chunk gets a stable compound ID: "<file_id>:<chunk_index>"
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str        # "<file_id>:<index>"
    file_id: str
    chunk_index: int
    text: str            # the actual text that will be embedded


# Sentence boundary pattern – split after ". " / "! " / "? " / "\n"
_SENTENCE_SEP = re.compile(r"(?<=[.!?])\s+|\n")


def _hard_split(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split a string into fixed-size windows with overlap."""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        pieces.append(text[start:end].strip())
        start += chunk_size - overlap
    return [p for p in pieces if p]


def _split_paragraph(para: str, chunk_size: int, overlap: int) -> list[str]:
    """Split one paragraph into ≤chunk_size pieces."""
    if len(para) <= chunk_size:
        return [para]

    # Try sentence-level split
    sentences = [s.strip() for s in _SENTENCE_SEP.split(para) if s.strip()]
    bucket: list[str] = []
    bucket_len = 0
    chunks: list[str] = []

    for sentence in sentences:
        if bucket_len + len(sentence) + 1 > chunk_size:
            if bucket:
                chunks.append(" ".join(bucket))
            # If a single sentence already exceeds chunk_size, hard-split it
            if len(sentence) > chunk_size:
                chunks.extend(_hard_split(sentence, chunk_size, overlap))
                bucket = []
                bucket_len = 0
            else:
                bucket = [sentence]
                bucket_len = len(sentence)
        else:
            bucket.append(sentence)
            bucket_len += len(sentence) + 1

    if bucket:
        chunks.append(" ".join(bucket))

    return chunks or [para]


def chunk_text(
    text: str,
    file_id: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[Chunk]:
    """
    Chunk `text` into overlapping segments.

    Args:
        text:       The full extracted text to chunk.
        file_id:    Stable identifier for the source file (used in chunk_id).
        chunk_size: Maximum characters per chunk.
        overlap:    Characters of context carried into the next hard-split chunk.

    Returns:
        Ordered list of Chunk objects ready to be embedded.
    """
    if not text or not text.strip():
        return []

    # Split on blank lines → paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    raw_chunks: list[str] = []
    for para in paragraphs:
        raw_chunks.extend(_split_paragraph(para, chunk_size, overlap))

    return [
        Chunk(
            chunk_id=f"{file_id}:{i}",
            file_id=file_id,
            chunk_index=i,
            text=chunk_text_,
        )
        for i, chunk_text_ in enumerate(raw_chunks)
        if chunk_text_.strip()
    ]
