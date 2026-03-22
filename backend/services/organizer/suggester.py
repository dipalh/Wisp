"""
Directory suggestion pipeline.

Reads the LanceDB index-card rows (one per ingested file), builds a manifest,
and asks Gemini to propose 2-3 distinct directory organization schemes using
structured output (JSON mode). The result is a validated DirectorySuggestions
Pydantic model.

Public surface
--------------
  suggest_directories() -> DirectorySuggestions
"""
from __future__ import annotations

from pathlib import Path

from ai.generate import generate_structured
from services.embedding import store
from services.roots import get_roots, is_under_root
from services.organizer.models import DirectoryProposal, DirectorySuggestions, FileMapping


# ── Tree builder ──────────────────────────────────────────────────────────────


def _build_tree_string(file_paths: list[str]) -> str:
    """Return an indented ASCII tree of the current directory structure."""
    # Build a trie: directories are dicts, files are None
    tree: dict = {}
    for raw in sorted(file_paths):
        parts = [p for p in raw.replace("\\", "/").split("/") if p]
        node = tree
        for part in parts[:-1]:          # directory components
            node = node.setdefault(part, {})
        node[parts[-1]] = None           # file leaf

    lines: list[str] = []

    def _render(node: dict, indent: int) -> None:
        dirs = {k: v for k, v in sorted(node.items()) if isinstance(v, dict)}
        files = [k for k, v in sorted(node.items()) if v is None]
        for name, subtree in dirs.items():
            lines.append("  " * indent + name + "/")
            _render(subtree, indent + 1)
        for name in files:
            lines.append("  " * indent + name)

    _render(tree, 0)
    return "\n".join(lines)

# ── Gemini system prompt ──────────────────────────────────────────────────────

_SYSTEM = """\
You are Wisp, an intelligent file organizer. The user has a messy collection of files \
that have been indexed with their content summaries. You will be given:
  1. The CURRENT directory tree showing exactly how the files are organized now.
  2. A list of each file with its type and a content summary.

Your job is to propose 2 to 3 distinct directory structures that would organize \
these files more semantically than the current layout.

Rules:
- Study the current structure first — your proposals must be meaningfully different \
  from it and from each other (e.g. by project/topic, by file type, by workflow stage).
- Every file in the manifest must appear in every proposal's mappings list.
- original_path in each mapping must exactly match the file's path as listed in the manifest.
- suggested_path values must be relative (no leading slash) and use forward slashes.
- folder_tree lists only directories, not files.
- rationale should be 1-2 sentences: explain what makes this scheme useful.
- recommendation should name the best scheme and give a one-sentence reason why.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_manifest(files: list[dict]) -> str:
    """Format the file list into a human-readable prompt block.

    Includes two sections:
      1. Current directory tree — the existing layout Gemini should improve on.
      2. Per-file details — type and content summary for each file.
    """
    # ── Section 1: current tree ───────────────────────────────────────────────
    paths = [f["file_path"] for f in files if f.get("file_path")]
    tree_str = _build_tree_string(paths)

    lines = [
        "=== CURRENT DIRECTORY STRUCTURE ===",
        "(This is how the files are organized RIGHT NOW. Your proposals must improve on this.)",
        "",
        tree_str,
        "",
        "=== FILE DETAILS ===",
        "",
    ]

    # ── Section 2: per-file summaries ─────────────────────────────────────────
    for f in files:
        lines.append(f"- {f['file_path']}  (type: {f['ext']})")
        summary = f["text"].replace("[FILE INDEX] ", "")
        lines.append(f"  Summary: {summary}")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────


async def suggest_directories() -> DirectorySuggestions:
    """
    Read all indexed files from LanceDB and ask Gemini to propose directory structures.

    Returns:
        DirectorySuggestions with 2-3 proposals and a recommendation.
        If no files are indexed yet, returns an empty proposals list with an
        explanatory recommendation string.
    """
    files = store.list_files()

    if not files:
        return DirectorySuggestions(
            proposals=[],
            recommendation=(
                "No files have been indexed yet. "
                "Run the ingestion pipeline first, then request suggestions."
            ),
        )

    manifest = _build_manifest(files)
    return await generate_structured(manifest, DirectorySuggestions, system=_SYSTEM)


def _mock_destination(file_path: str, ext: str) -> str:
    name = Path(file_path).name
    ext_l = (ext or "").lower()
    if ext_l in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        return f"Media/Images/{name}"
    if ext_l in {".mp4", ".mov", ".avi", ".mkv"}:
        return f"Media/Videos/{name}"
    if ext_l in {".pdf", ".doc", ".docx", ".txt", ".md"}:
        return f"Documents/{name}"
    return f"Misc/{name}"


def _mock_suggestions(files: list[dict]) -> DirectorySuggestions:
    ordered = sorted(files, key=lambda f: (f.get("file_path") or "", f.get("ext") or ""))
    mappings = [
        FileMapping(
            original_path=f["file_path"],
            suggested_path=_mock_destination(f["file_path"], f.get("ext", "")),
        )
        for f in ordered
    ]
    citations = [f["file_path"] for f in ordered[: min(3, len(ordered))]]
    proposal = DirectoryProposal(
        name="Deterministic File Type Strategy",
        rationale="Groups files by stable media/document buckets for predictable demo-safe organization.",
        reasons=[
            "Stable categorization by extension is deterministic and reproducible.",
            "Layout is easy to review before any action is applied.",
        ],
        citations=citations,
        folder_tree=sorted({Path(m.suggested_path).parent.as_posix() + "/" for m in mappings}),
        mappings=mappings,
    )
    return DirectorySuggestions(
        proposals=[proposal],
        recommendation="Use Deterministic File Type Strategy for a predictable review-first organization pass.",
    )


def _degraded_budget_response() -> DirectorySuggestions:
    return DirectorySuggestions(
        proposals=[],
        recommendation=(
            "Degraded organizer response: tool budget exhausted before planning. "
            "Increase budget and retry."
        ),
    )


def _outside_root_targets(files: list[dict]) -> list[str]:
    if not get_roots():
        return []
    outside: list[str] = []
    for f in files:
        file_path = f.get("file_path")
        if not file_path:
            continue
        if not is_under_root(file_path):
            outside.append(file_path)
    return sorted(set(outside))


async def suggest_directories(
    mock_mode: bool = False,
    tool_budget: int | None = None,
) -> DirectorySuggestions:
    """
    Read all indexed files from LanceDB and ask Gemini to propose directory structures.

    Args:
        mock_mode: When True, bypass model generation and return deterministic
            suggestions from file metadata only.
        tool_budget: Optional planning budget. Values <= 0 return a deterministic
            degraded response instead of raising.

    Returns:
        DirectorySuggestions with proposals and a recommendation.
        If no files are indexed yet, returns an empty proposals list with an
        explanatory recommendation string.
    """
    files = store.list_files()

    if not files:
        return DirectorySuggestions(
            proposals=[],
            recommendation=(
                "No files have been indexed yet. "
                "Run the ingestion pipeline first, then request suggestions."
            ),
        )

    outside = _outside_root_targets(files)
    if outside:
        return DirectorySuggestions(
            proposals=[],
            recommendation=(
                "Rejected organizer planning because one or more targets are outside "
                "registered roots."
            ),
        )

    if tool_budget is not None and tool_budget <= 0:
        return _degraded_budget_response()

    if mock_mode:
        return _mock_suggestions(files)

    manifest = _build_manifest(files)
    try:
        return await generate_structured(manifest, DirectorySuggestions, system=_SYSTEM)
    except Exception as exc:
        fallback = _mock_suggestions(files)
        fallback.recommendation = (
            "Degraded organizer response: Ollama unavailable; "
            f"using deterministic mock strategy. ({exc})"
        )
        return fallback
