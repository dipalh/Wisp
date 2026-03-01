### Decision A — Source of truth

**Filesystem is the truth.**
SQLite + Chroma are **indexes/caches** that must be rebuildable.

**Second-order effect:** your app must tolerate stale indexes and reconcile.
**Third-order:** you can ship even when indexing fails; you can always “Rescan”.

---

### Decision B — Action model

All mutations go through **one executor** (Action Engine), and every mutation is:

* **reversible** (Quarantine/Move/Restore)
* **scoped** (roots only)
* **audited** (Action log)

**Second-order:** Agent never “does”; it only **proposes**.
**Third-order:** you can prove safety to judges and avoid catastrophic bugs.

---

### Decision C — Indexing lifecycle (the “state machine”)

Your scan is not one thing; it’s a pipeline with states. You must define:

* `DISCOVERED` (metadata exists)
* `PREVIEWED` (thumb/snippet)
* `EMBEDDED` (chunks in Chroma)
* `SCORED` (heuristics computed)

**Second-order:** UI can show partial results early.
**Third-order:** you avoid “scan must finish before app works” (demo killer).

---

### Decision D — Consistency policy (how you deal with external changes)

You *cannot* guarantee real-time correctness in hackathon scope.

Choose one of these:

1. **Explicit resync**: “Scan” + “Rescan this folder”
2. Optional watcher later

**Second-order:** action failures become normal (“file moved externally”).
**Third-order:** design error messages + fallback behavior now.

---

### Decision E — What “agentic” actually means

Agentic ≠ “LLM randomly calls tools.”

Agentic means:

* There is a **tool router** with constraints
* The agent outputs **(answer + citations + proposals)**
* Execution requires **user accept**

**Second-order:** you keep determinism; you avoid accidental deletes.
**Third-order:** you can run MOCK mode without changing product behavior.

---

## 1) The invariants (non-negotiable rules)

These are what you should literally write on the diagram.

1. **Only Indexer + Action Engine touch filesystem**
2. **All filesystem ops pass Root Scope Guard**
3. **No hard delete** (delete = quarantine move)
4. **Indexes are rebuildable** (SQLite/Chroma can be blown away and regenerated)
5. **Agent cannot execute destructive actions without accept**
6. **Every suggestion has reasons + can be suppressed**

If any component violates these, your architecture is broken.

---

## 2) First-order architecture (the minimum “real” system)

This is what must exist for FileOS to be coherent:

### Core services

* **Indexer** (discover + update file records)
* **Preview Extractor** (thumb/snippet)
* **Embedding Pipeline** (chunk + embed + upsert)
* **Heuristics Engine** (junk_score + reasons + recommended_action)
* **Search Engine** (metadata + semantic)
* **Action Engine** (quarantine/archive/rename/undo)
* **Tool Router** (enforces rules + executes safe tools)
* **Agent Orchestrator** (LLM/MOCK planner that calls Tool Router)

### Storage

* **SQLite**: canonical *app state* (roots, file metadata, preview pointers, heuristic outputs, actions, job state)
* **Chroma**: semantic index (chunks + metadata)
* **AppData dir**: Quarantine/Archive/Thumbs

That’s the “real system.” Everything else is garnish.

---

## 3) Second-order effects you must design for (this is what was missing)

These are the reasons systems like this fail.

### A) Partial indexing must be a first-class UX

You will not finish embedding everything quickly.

So: UI must support:

* “Indexed: 10,234 files”
* “Embedded: 1,102 files”
* “Scored: 9,980 files”

Otherwise your app feels broken during scan.

### B) Staleness must be handled intentionally

Files will change outside the app.

So the Action Engine must return:

* `MISSING_EXTERNALLY`
* `PERMISSION_DENIED`
* `LOCKED`
* `COLLISION_RENAME`

And the UI must have one response pattern:

* show toast + “Rescan recommended”
* mark file as stale/missing

### C) Duplicate hashing is expensive and must be lazy

If you hash everything, you die.

So: duplicate hashing only runs for:

* top N candidates by junk score
* or files above a size threshold
* or when user opens “Duplicates” view

### D) Chunking + embedding must be idempotent

If you re-scan:

* old chunks must be deleted or versioned
* you must avoid “duplicate chunks in Chroma”

So store:

* `embed_version`
* `mtime_fingerprint`
  and on mismatch: delete-by-file_id then upsert.

### E) The assistant needs citations grounded in retrieval

Otherwise it’s fluff.

So: the agent must return:

* file_ids + snippet citations (from Chroma metadata / chunks table)
* confidence + explanation per proposal

---

## 4) Third-order effects (the “this wins hackathons” layer)

These are what make it mindblowing without overscope.

### A) Deterministic demo mode

MOCK mode should still call:

* real semantic search
* real previews
* real heuristics
  It only mocks “language + planning.”

This prevents “AI failed” demos.

### B) Safety narrative becomes a feature

You don’t “talk about” safety; you show it:

* Quarantine folder visible in UI
* Undo button always present
* “Proposals require accept”

### C) Performance failure modes are controlled

* All heavy work is async jobs
* UI never blocks on embedding
* Any view works with partial data

---

## 5) Now the flows (but only after the above)

If you accept the above, the “flows” become **short** and **meaningful**, not 60 steps.

### Flow 1: Scan pipeline (state machine)

* Discover (files table) → Preview (previews + thumbs) → Embed (Chroma) → Score (heuristics)
* Each stage is **incremental** and **resumable**
* UI reflects stage completion %s

### Flow 2: Treemap / Candidates (read model)

* Treemap reads `files` aggregation
* Candidates reads `files ⨝ heuristics ⨝ previews`
* No filesystem reads here

### Flow 3: Semantic search

* embed query → Chroma top-k → hydrate from SQLite → return citations

### Flow 4: Assistant (agentic)

* plan with Tool Router → semantic_search/get_preview → propose actions (no execution) → user accept → Action Engine executes

### Flow 5: Actions + Undo

* Action Engine mutates FS + updates SQLite + action log
* Undo reverses last action; collisions handled deterministically

---

## What you should do next (to unstick yourselves)

You don’t need more diagramming. You need **two written specs** that force alignment:

### Spec A — Indexing state machine (1 page)

Define:

* stages: DISCOVERED / PREVIEWED / EMBEDDED / SCORED
* what table(s) each stage writes
* what “done” means per stage
* how re-scan updates stages

### Spec B — Tool contract (1 page)

Define tool inputs/outputs for:

* semantic_search
* get_preview
* propose_cleanup
* propose_rename
* execute_action (only after accept)
* undo_last

If you write those two specs, the architecture stops being vibes and becomes implementable.