"""
Directory suggestion pipeline.

This module now uses a small explicit planner loop:

1. Read indexed files.
2. Ask the local planner which tool to call next.
3. Execute the requested tool through OrganizerToolRouter.
4. Feed the observations back into the planner.
5. Finalize into DirectorySuggestions.

If Ollama is unavailable or the planner exhausts budget, we degrade to a
deterministic review-safe strategy instead of failing closed.
"""
from __future__ import annotations

from pathlib import Path
import os

from ai.generate import generate_structured
from services.embedding import store
from services.organizer.models import (
    DirectoryProposal,
    DirectorySuggestions,
    FileMapping,
    PlannerDecision,
)
from services.organizer.tool_router import OrganizerToolRouter
from services.roots import get_roots, is_under_root


_SYSTEM = """\
You are Wisp, an intelligent file organizer. The user has a messy collection of files
that have been indexed with summaries. You will be given:
  1. The current directory tree.
  2. File summaries.
  3. Tool observations gathered during planning.

Your job is to propose 2 to 3 distinct directory structures that organize the files
more semantically than the current layout.

Rules:
- Every file in the manifest must appear in every proposal's mappings list.
- original_path in each mapping must exactly match the file's path as listed.
- suggested_path values must be relative, using forward slashes.
- folder_tree lists directories only.
- rationale should be 1-2 sentences.
- recommendation should name the best scheme and explain why.
"""

_PLANNER_SYSTEM = """\
You are the Wisp organizer planner. Decide the single best next tool action to gather
missing context before proposing organization strategies.

Available actions:
- get_folder_manifest
- get_preview
- get_file_metadata
- semantic_search
- finalize

Rules:
- Request only one action at a time.
- Prefer inspecting folder structure first, then representative files.
- Use finalize when you have enough evidence to produce safe, reviewable strategies.
- Keep queries concise and targeted.
"""


def _build_tree_string(file_paths: list[str]) -> str:
    tree: dict = {}
    for raw in sorted(file_paths):
        parts = [p for p in raw.replace("\\", "/").split("/") if p]
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None

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


def _build_manifest(files: list[dict], tool_observations: list[str] | None = None) -> str:
    paths = [f["file_path"] for f in files if f.get("file_path")]
    tree_str = _build_tree_string(paths)

    lines = [
        "=== CURRENT DIRECTORY STRUCTURE ===",
        "(This is how the files are organized RIGHT NOW. Your proposals must improve on this.)",
        "",
        tree_str,
        "",
    ]

    if tool_observations:
        lines.extend([
            "=== TOOL OBSERVATIONS ===",
            "",
            *tool_observations,
            "",
        ])

    lines.extend([
        "=== FILE DETAILS ===",
        "",
    ])

    for f in files:
        lines.append(f"- {f['file_path']}  (type: {f['ext']})")
        summary = f["text"].replace("[FILE INDEX] ", "")
        lines.append(f"  Summary: {summary}")

    return "\n".join(lines)


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


def _degraded_mock_response(files: list[dict], reason: str) -> DirectorySuggestions:
    fallback = _mock_suggestions(files)
    fallback.recommendation = (
        "Degraded organizer response: invalid planner tool request; "
        f"using deterministic mock strategy. ({reason})"
    )
    return fallback


def _outside_root_targets(files: list[dict]) -> list[str]:
    if not get_roots():
        return []
    outside: list[str] = []
    for f in files:
        file_path = f.get("file_path")
        if file_path and not is_under_root(file_path):
            outside.append(file_path)
    return sorted(set(outside))


def _infer_planning_root(files: list[dict]) -> str:
    roots = get_roots()
    if roots:
        return roots[0]
    paths = [Path(f["file_path"]) for f in files if f.get("file_path")]
    if not paths:
        return ""
    common = Path(os.path.commonpath([str(p) for p in paths]))
    if common.is_file() or common.suffix:
        common = common.parent
    if len(paths) == 1 and len(paths[0].parents) >= 2:
        return str(paths[0].parents[1])
    return str(common)


def _build_planner_prompt(
    files: list[dict],
    *,
    planning_root: str,
    tool_observations: list[str],
    remaining_steps: int,
) -> str:
    sample_files = "\n".join(
        f"- {item['file_path']} ({item['ext']})"
        for item in files[:5]
    )
    observation_block = "\n".join(tool_observations) if tool_observations else "None yet."
    return (
        f"Planning root: {planning_root or 'unknown'}\n"
        f"Remaining tool steps: {remaining_steps}\n\n"
        "Indexed sample files:\n"
        f"{sample_files}\n\n"
        "Current observations:\n"
        f"{observation_block}\n\n"
        "Return the single next planner action."
    )


def _summarize_observation(action: str, payload: object) -> str:
    if isinstance(payload, list):
        preview = payload[:3]
    elif isinstance(payload, dict):
        preview = payload
    else:
        preview = str(payload)
    return f"{action}: {preview}"


def _execute_planner_action(
    router: OrganizerToolRouter,
    decision: PlannerDecision,
    planning_root: str,
) -> str:
    if decision.action == "get_folder_manifest":
        folder_path = decision.folder_path or planning_root
        if not folder_path:
            raise ValueError("Planner requested get_folder_manifest without a folder path")
        return _summarize_observation(
            decision.action,
            router.get_folder_manifest(folder_path),
        )

    if decision.action == "get_preview":
        if not decision.path:
            raise ValueError("Planner requested get_preview without a path")
        return _summarize_observation(
            decision.action,
            router.get_preview(decision.path, max_chars=decision.max_chars),
        )

    if decision.action == "get_file_metadata":
        if not decision.path:
            raise ValueError("Planner requested get_file_metadata without a path")
        return _summarize_observation(decision.action, router.get_file_metadata(decision.path))

    if decision.action == "semantic_search":
        if not decision.query:
            raise ValueError("Planner requested semantic_search without a query")
        return _summarize_observation(
            decision.action,
            router.semantic_search(decision.query, limit=decision.limit),
        )

    raise ValueError(f"Unsupported planner action: {decision.action}")


async def suggest_directories(
    mock_mode: bool = False,
    tool_budget: int | None = None,
) -> DirectorySuggestions:
    files = store.list_files()

    if not files:
        return DirectorySuggestions(
            proposals=[],
            recommendation="No files have been indexed yet. Run the ingestion pipeline first, then request suggestions.",
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

    router = OrganizerToolRouter()
    planning_root = _infer_planning_root(files)
    remaining_steps = tool_budget if tool_budget is not None else 2
    tool_observations: list[str] = []

    try:
        while remaining_steps > 0:
            decision = await generate_structured(
                _build_planner_prompt(
                    files,
                    planning_root=planning_root,
                    tool_observations=tool_observations,
                    remaining_steps=remaining_steps,
                ),
                PlannerDecision,
                system=_PLANNER_SYSTEM,
            )
            if decision.action == "finalize":
                break
            try:
                tool_observations.append(_execute_planner_action(router, decision, planning_root))
            except ValueError as exc:
                message = f"Invalid planner tool request: {exc}"
                tool_observations.append(message)
                remaining_steps -= 1
                if remaining_steps <= 0:
                    return _degraded_mock_response(files, message)
                continue
            remaining_steps -= 1
        else:
            return _degraded_budget_response()

        manifest = _build_manifest(files, tool_observations=tool_observations)
        return await generate_structured(manifest, DirectorySuggestions, system=_SYSTEM)
    except Exception as exc:
        fallback = _mock_suggestions(files)
        fallback.recommendation = (
            "Degraded organizer response: planner/runtime failure; "
            f"using deterministic mock strategy. ({exc})"
        )
        return fallback
