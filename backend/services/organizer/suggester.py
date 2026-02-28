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

from ai.generate import generate_structured
from services.embedding import store
from services.organizer.models import DirectorySuggestions


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
