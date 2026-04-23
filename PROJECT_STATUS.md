# PROJECT STATUS — Wisp

> Last updated: 2026-04-18
> Source of truth: this file
> Product identity: **AI FileOS desktop app** for local-first scan, grounded memory/search, cleanup, and review-first organization proposals
> Current state: **Alpha hardening — materially improved backend core, but still not MVP-complete from a product/UX standpoint.** Backend safety, local-LLM policy, action durability, and indexed search are in much better shape than before. The app is still held back by UI quality, thick modules, operational complexity, a duplicate legacy scan stack, and planner depth that is better than “fake” but still not yet a serious FileOS-grade agent runtime.

## Terminology Note

This repo is **Wisp**, not Codeva.

Some earlier feedback in this workspace referenced a mentor/shell/pathway product from a different codebase. The equivalent Wisp product surfaces are:

- `Scan & Index`
- `Memory` / semantic search / assistant
- `Organize` / proposal review / apply / undo
- `Clean`
- `Extract` / OCR / transcription

Any status tracking here is grounded in **Wisp’s code**, not in the other project’s terminology.

---

## Verified Gates

These are the commands and outcomes verified during this pass.

### Backend

```bash
backend/venv/bin/pytest --collect-only -q backend/tests
```

- `216 tests collected`

```bash
backend/venv/bin/pytest -q backend/tests
```

- `41 files / 216 tests passing`

### Frontend

The shell in this environment does **not** expose global `node` / `npm` on PATH, so frontend gates were run via the repo’s Electron-bundled Node runtime from inside `frontend/`. That is an environment quirk, not a product failure.

```bash
cd frontend
ELECTRON_RUN_AS_NODE=1 ../node_modules/electron/dist/Electron.app/Contents/MacOS/Electron node_modules/vitest/vitest.mjs run
```

- `8 files / 60 tests passing`

```bash
cd frontend
ELECTRON_RUN_AS_NODE=1 ../node_modules/electron/dist/Electron.app/Contents/MacOS/Electron node_modules/vite/bin/vite.js build
```

- `build succeeded`
- warning: large chunks remain (`index` ~996 kB minified, `pdf.worker` ~1.08 MB)

### Runtime Stack

Verified locally during this session:

- FastAPI backend on `:8000`
- Redis on `:6379`
- Celery worker connected to Redis
- Ollama serving on `:11434`
- Wisp renderer served separately from other Electron apps on a dedicated port
- Electron app launched against the dedicated Wisp renderer

Important operational note:

- Scan/index was initially appearing “dead” because Celery inherited a stale Redis backlog of old scan jobs. That is now a known local-dev failure mode and should be treated as operational debt, not random flakiness.

---

## Kanban

The board below is the current source of truth. If an item is in **Done**, it is either directly verified by the gates above or clearly reflected in the live code path. If an item is in **Open**, it is not complete enough to claim.

### In Progress

| Item | Why it matters |
|---|---|
| Source-of-truth project tracking | `PROJECT_STATUS.md` now exists because the repo previously had plan packs and audit notes, but no single tracked root status file. |
| Scan/index operational hardening | The product path works, but stale Celery backlog / startup complexity still make local-dev behavior feel unreliable. |

### Blocked

| Item | Blocked on |
|---|---|
| High-signal performance budgets for scan/index | Needs a dedicated perf harness and stable fixture corpus; wall-clock timing tests alone would be noisy. |
| Cross-platform OS tagging parity | Current implementation is Finder-centric; Windows / Linux parity is not verified. |

### Open — Priority Order

#### P0: Product Correctness / Trust

| ID | Item | Status |
|---|---|---|
| P0.1 | Remove the duplicate legacy scan stack (`/api/v1/scan` + `services.jobs`) or clearly quarantine it from the live product path | Partial |
| P0.2 | Make search and assistant request-scoped by root, not only dependent on shared global root registry | Open |
| P0.3 | Rotate and remove committed secrets from `backend/.env`; stop treating checked-in credentials as acceptable local state | Open |
| P0.4 | Make scan/index startup operationally deterministic (`backend + Redis + Celery + Ollama + renderer + Electron`) with a single trusted dev entrypoint | Open |
| P0.5 | Strengthen planner depth beyond the current lightweight schema-driven tool loop | Open |

#### P1: Product Surface / UX

| ID | Item | Status |
|---|---|---|
| P1.1 | Replace current generic/uneven UI with a deliberate visual system and stronger motion language | Open |
| P1.2 | Improve truthful scan UX so slow embedding work feels progressive rather than “stuck” | Open |
| P1.3 | Tighten organization review UX: better strategy comparison, clearer citations, more explicit risk surfacing | Partial |
| P1.4 | Rationalize secondary surfaces (`Debloat`, `Privacy`, `Legal`) so the app reads as one product, not a stack of demos | Open |

#### P2: Architecture / Maintainability

| ID | Item | Status |
|---|---|---|
| P2.1 | Split thick modules (`backend/main.cjs`, `pipeline.py`, `AppShell.tsx`, `styles.css`) into cleaner seams | Open |
| P2.2 | Remove or formally retire dead/stale frontend files (`AssistantView.tsx`, `TreeVisualizer.tsx`) | Open |
| P2.3 | Align docs with code: `ARCHITECTURE.md` still says Chroma while runtime uses LanceDB | Open |
| P2.4 | Remove ambiguous runtime artifacts (`/Users/vishnu/Documents/Wisp/wisp_jobs.db` at repo root) | Open |

### Done — Verified Recent State

| Item | Evidence |
|---|---|
| Live app no longer exposes the legacy `/api/v1/scan` surface | [backend/tests/test_main_app_routes.py](/Users/vishnu/Documents/Wisp/backend/tests/test_main_app_routes.py) |
| Organizer is proposal-first rather than `organizeFolder` deterministic mutation | Organizer runtime policy tests and current Electron preload/main bridge |
| Action engine is durable, auditable, quarantine-first, and undo-capable | PLAN6 suites; `backend/tests/test_actions_plan6.py`, `test_executor.py`, `test_action_scope.py` |
| Assistant and search are grounded, state-aware, and degrade explicitly | PLAN7 suites; `backend/tests/test_plan7_contract.py`, `test_assistant_api_contract.py`, `test_search_api.py` |
| Metadata drift and file state surfacing exist across scan/search flows | PLAN8 suites; `backend/tests/test_plan8_contract.py`, `test_reconciliation.py`, `test_tagging_correctness.py` |
| Organizer tool router is root-scoped and more real than before | `backend/tests/test_organize_tool_router.py` |
| Desktop app now syncs roots explicitly to backend-scoped flows | `frontend/src/components/__tests__/AppShell.test.tsx`, IPC contract tests |

---

## Product Readout

## What Wisp Actually Is Today

Wisp today is:

- a real Electron desktop shell
- a real FastAPI backend
- a real Celery + Redis scan job system
- a real SQLite + LanceDB index layer
- a real local-only LLM policy targeting Ollama
- a partially real agentic organizer

Wisp today is **not yet**:

- a polished Cursor-class desktop product
- a deeply agentic multi-step planner with rich self-correction
- a low-friction consumer-grade local app that starts cleanly with one command and always “just works”
- a visually distinctive, high-confidence UX

## Can It Compete With Cursor Today?

No.

That is not because the entire codebase is fake. It is because:

- the UI/UX is still far behind
- the planner depth is still too shallow
- operational startup is still too fragile
- the app has too much architectural drift between “current path” and “legacy path”
- the product surface does not yet deliver a compelling “wow” moment consistently

The honest framing is:

- backend foundation: **promising**
- product correctness: **mixed**
- UX polish: **weak**
- operational reliability: **improving, not solved**

---

## Architecture At A Glance

### Live Product Path

- **Electron main process**: [backend/main.cjs](/Users/vishnu/Documents/Wisp/backend/main.cjs)
- **Electron preload bridge**: [backend/preload.cjs](/Users/vishnu/Documents/Wisp/backend/preload.cjs)
- **Renderer root**: [frontend/src/App.tsx](/Users/vishnu/Documents/Wisp/frontend/src/App.tsx)
- **Renderer shell/orchestration**: [frontend/src/components/AppShell.tsx](/Users/vishnu/Documents/Wisp/frontend/src/components/AppShell.tsx)
- **Backend API app**: [backend/main.py](/Users/vishnu/Documents/Wisp/backend/main.py)
- **Scan jobs**: [backend/api/v1/jobs.py](/Users/vishnu/Documents/Wisp/backend/api/v1/jobs.py) + [backend/tasks/scan.py](/Users/vishnu/Documents/Wisp/backend/tasks/scan.py)
- **Index metadata store**: [backend/services/job_db.py](/Users/vishnu/Documents/Wisp/backend/services/job_db.py)
- **Semantic store**: [backend/services/embedding/store.py](/Users/vishnu/Documents/Wisp/backend/services/embedding/store.py) using **LanceDB**
- **Embedding / retrieval pipeline**: [backend/services/embedding/pipeline.py](/Users/vishnu/Documents/Wisp/backend/services/embedding/pipeline.py)
- **Organizer planner**: [backend/services/organizer/suggester.py](/Users/vishnu/Documents/Wisp/backend/services/organizer/suggester.py)
- **Organizer tools**: [backend/services/organizer/tool_router.py](/Users/vishnu/Documents/Wisp/backend/services/organizer/tool_router.py)
- **Durable action engine**: [backend/services/actions/store.py](/Users/vishnu/Documents/Wisp/backend/services/actions/store.py), [backend/services/actions/executor.py](/Users/vishnu/Documents/Wisp/backend/services/actions/executor.py), [backend/services/actions/batch_executor.py](/Users/vishnu/Documents/Wisp/backend/services/actions/batch_executor.py)

### Core Invariants That Are Real in Code

- filesystem is the source of truth
- actions are scoped to registered roots
- hard delete is replaced by quarantine move in the core action model
- organizer proposes first, then apply/undo run through the durable action engine
- local-LLM policy exists and tests enforce Ollama-only inference paths

### Major Architecture Drift Still Present

1. `ARCHITECTURE.md` still references **Chroma**, but runtime uses **LanceDB**.
2. The backend codebase still contains **two scan systems**, even though only one is now mounted in the live app:
   - live: `/api/v1/jobs/*` + SQLite + Celery
   - legacy (unmounted): `/api/v1/scan/*` + in-memory `services.jobs`
3. The main Electron process is still a very thick orchestration layer, not a narrow shell.
4. Search/assistant rely on shared root state instead of purely explicit request scoping.

---

## Code Review — Biggest Real Issues

These are not theoretical. They are the most important issues surfaced by this pass.

| Severity | Issue | Evidence |
|---|---|---|
| Critical | Committed secrets exist in `backend/.env` | [backend/.env](/Users/vishnu/Documents/Wisp/backend/.env) contains live-looking API keys; this is unacceptable hygiene and should be rotated/removed. |
| High | Duplicate scan architecture still exists in code, even though the live app no longer mounts it | [backend/api/v1/scan.py](/Users/vishnu/Documents/Wisp/backend/api/v1/scan.py) + [backend/services/jobs.py](/Users/vishnu/Documents/Wisp/backend/services/jobs.py) still exist alongside the real `/api/v1/jobs` + Celery stack. |
| High | Local-dev scan reliability is operationally fragile | Fresh jobs can appear dead if Redis contains stale Celery backlog; this happened during live validation. |
| High | Planner is real but still shallow | [backend/services/organizer/suggester.py](/Users/vishnu/Documents/Wisp/backend/services/organizer/suggester.py) has a tool loop, but it is still a lightweight schema-driven planner rather than a richer agent runtime. |
| High | Search/assistant root scope is still not explicit enough | Organizer now accepts explicit `root_path`, but search/assistant still depend on shared registered roots rather than per-request scope. |
| Medium | Oversized modules hurt maintainability | [backend/main.cjs](/Users/vishnu/Documents/Wisp/backend/main.cjs) `840` lines, [backend/services/embedding/pipeline.py](/Users/vishnu/Documents/Wisp/backend/services/embedding/pipeline.py) `1175` lines, [frontend/src/components/AppShell.tsx](/Users/vishnu/Documents/Wisp/frontend/src/components/AppShell.tsx) `570` lines, [frontend/src/styles.css](/Users/vishnu/Documents/Wisp/frontend/src/styles.css) `5181` lines. |
| Medium | Stale or orphaned frontend files remain | [frontend/src/views/AssistantView.tsx](/Users/vishnu/Documents/Wisp/frontend/src/views/AssistantView.tsx) and [frontend/src/TreeVisualizer.tsx](/Users/vishnu/Documents/Wisp/frontend/src/TreeVisualizer.tsx) appear unreferenced in the current renderer path. |
| Medium | Root-level `wisp_jobs.db` artifact is misleading | `/Users/vishnu/Documents/Wisp/wisp_jobs.db` exists separately from [backend/wisp_jobs.db](/Users/vishnu/Documents/Wisp/backend/wisp_jobs.db); it should not exist if backend DB ownership is clear. |
| Medium | Docs drift weakens trust | [ARCHITECTURE.md](/Users/vishnu/Documents/Wisp/ARCHITECTURE.md) still says Chroma; README is closer to truth, but the docs are not fully aligned. |
| Low | Frontend build is green but bundle size is too large | Build output shows ~996 kB main chunk and ~1.08 MB PDF worker. |

---

## Operational Truth

## Minimum Local Stack

Wisp is not a single-process app.

To exercise the real product path, the following must exist together:

- renderer dev server
- Electron app
- FastAPI backend
- Redis
- Celery worker
- Ollama

### Why This Matters

When one of these is missing, the app often does not fail loudly enough. Instead it can feel “dysfunctional.”

### Known Local-Dev Failure Mode

If Redis contains stale Celery scan jobs:

- the worker may spend all its time on old jobs
- new scan jobs remain `queued`
- the UI looks dead or misleading

This is a real problem and should eventually be solved in product/dev tooling, not by tribal knowledge.

---

## Test Inventory

### Backend

- `41` test files
- `216` tests
- strongest coverage areas:
  - action safety / undo / root scope
  - organizer contract, tool router, and runtime policy
  - scan progress, reconciliation, and file states
  - search / assistant response contracts
  - extraction contracts
  - local-LLM endpoint policy

Representative suites:

- [backend/tests/test_actions_plan6.py](/Users/vishnu/Documents/Wisp/backend/tests/test_actions_plan6.py)
- [backend/tests/test_organize_agent_contract.py](/Users/vishnu/Documents/Wisp/backend/tests/test_organize_agent_contract.py)
- [backend/tests/test_organize_tool_router.py](/Users/vishnu/Documents/Wisp/backend/tests/test_organize_tool_router.py)
- [backend/tests/test_scan_progress.py](/Users/vishnu/Documents/Wisp/backend/tests/test_scan_progress.py)
- [backend/tests/test_search_api.py](/Users/vishnu/Documents/Wisp/backend/tests/test_search_api.py)
- [backend/tests/test_plan7_contract.py](/Users/vishnu/Documents/Wisp/backend/tests/test_plan7_contract.py)
- [backend/tests/test_plan8_contract.py](/Users/vishnu/Documents/Wisp/backend/tests/test_plan8_contract.py)

### Frontend

- `8` test files
- `60` tests

Covered surfaces:

- IPC contract
- AppShell root sync behavior
- OrganizeModal truthful proposal/apply flow
- Undo toast
- Error banner
- MemoryView
- ScanView

Representative suites:

- [frontend/src/test/__tests__/wispApiContract.test.ts](/Users/vishnu/Documents/Wisp/frontend/src/test/__tests__/wispApiContract.test.ts)
- [frontend/src/components/__tests__/AppShell.test.tsx](/Users/vishnu/Documents/Wisp/frontend/src/components/__tests__/AppShell.test.tsx)
- [frontend/src/components/__tests__/OrganizeModal.test.tsx](/Users/vishnu/Documents/Wisp/frontend/src/components/__tests__/OrganizeModal.test.tsx)
- [frontend/src/views/__tests__/MemoryView.test.tsx](/Users/vishnu/Documents/Wisp/frontend/src/views/__tests__/MemoryView.test.tsx)
- [frontend/src/views/__tests__/ScanView.test.tsx](/Users/vishnu/Documents/Wisp/frontend/src/views/__tests__/ScanView.test.tsx)

### Important Testing Nuance

Frontend tests must be run from `frontend/` context (or with equivalent config), not blindly from repo root, otherwise jsdom/setup is bypassed and the suite produces false negatives like `window is not defined`.

---

## File Map — Current Truth

```text
Wisp/
  PROJECT_STATUS.md                # Root source of truth for status
  README.md                        # Current product thesis and canonical commands
  ARCHITECTURE.md                  # High-level architecture notes (contains drift)

  backend/
    main.py                        # FastAPI app
    main.cjs                       # Electron main process (thick)
    preload.cjs                    # Electron preload bridge
    celery_app.py                  # Celery app / Redis broker wiring
    api/v1/
      actions.py                   # Apply / undo action APIs
      assistant.py                 # Grounded assistant
      extract.py                   # Extraction API
      jobs.py                      # Live scan job API
      organize.py                  # Proposal-first organize API
      roots.py                     # Root registry
      scan.py                      # Legacy scan API (drift)
      search.py                    # Semantic search API
    services/
      actions/                     # Durable action engine
      embedding/                   # LanceDB + ingest/search pipeline
      file_processor/              # Extraction dispatch
      ingestor/                    # File discovery / scanner
      organizer/                   # Planner, tool router, proposal state
      os_tags/                     # Finder tagging integration
      job_db.py                    # SQLite job / indexed file metadata
      jobs.py                      # Legacy in-memory scan jobs (drift)
      proposer.py                  # Cleanup proposals from hits
      roots.py                     # Root scope registry
    tasks/
      scan.py                      # Celery scan task
    tests/                         # 40 backend test files / 215 tests

  frontend/
    src/
      App.tsx
      main.tsx
      components/
        AppShell.tsx               # Renderer orchestration (thick)
        OrganizeModal.tsx          # Proposal review/apply modal
        ScanModal.tsx              # Scan progress modal
        ContextPanel.tsx
        UndoToast.tsx
      views/
        ScanView.tsx
        MemoryView.tsx
        OrganizeView.tsx
        CleanView.tsx
        ExtractView.tsx
        DebloatView.tsx
        PrivacyView.tsx
        LegalView.tsx
        AssistantView.tsx          # Appears stale/unwired
      TreeVisualizer.tsx           # Appears stale/unwired
      styles.css                   # Global stylesheet (very large)
      test-setup.ts
      test/                        # Shared IPC contract helpers

  docs/
    audit/AGENTIC_AUDIT.md         # Living audit / research log
    polish/PLAN*.md                # Backend/platform plan pack
    ui/PLAN*.md                    # UI plan pack

  Downloads/                       # Local workspace noise / fixtures; not product source
```

---

## MVP Definition

Wisp reaches MVP when a user can:

1. choose a local folder
2. run a truthful scan/index job without operational guesswork
3. search and ask grounded questions about indexed files
4. review safe organization/cleanup proposals with reasons and citations
5. apply and undo those proposals safely

### MVP Gate Checklist

| # | Gate | Status | Notes |
|---|---|---|---|
| 1 | Backend test harness is stable | ✅ | `215 passed` |
| 2 | Frontend component/contract tests are stable | ✅ | `60 passed` |
| 3 | Local-only LLM policy is enforced | ✅ | backend policy tests exist |
| 4 | Organizer is propose-first, not direct mutation | ✅ | live runtime path |
| 5 | Apply/undo is durable and auditable | ✅ | action engine + PLAN6 suites |
| 6 | Search/assistant are grounded in local index | ✅ | search + assistant suites |
| 7 | File states are surfaced in responses | ✅ | stale/missing/quarantined coverage exists |
| 8 | Scan/index runtime is operationally reliable for normal local use | ❌ | too fragile; stale backlog and startup complexity still matter |
| 9 | UI is polished enough to feel like a coherent product | ❌ | not there yet |
| 10 | Agentic organizer is deep enough to feel genuinely intelligent | ❌ | better than before, still not enough |

**MVP is not complete.**

The backend is much closer than the product experience.

---

## Principal-Engineer Read

This repo is no longer “all vibes.” There is real engineering value here now:

- real tests
- real invariants
- real durable actions
- real local LLM policy
- real search / assistant / organizer infrastructure

But the app is still behind where it needs to be.

The most important truth is this:

**Wisp’s biggest remaining problem is no longer whether there is any architecture. It is whether that architecture is cleanly expressed, operationally reliable, and presented through a product surface that people can trust.**

If we keep the next passes disciplined, the right next order is:

1. remove legacy/duplicate scan path drift
2. harden scan/index operational behavior and truthfulness
3. deepen planner/tool quality
4. split thick modules and remove stale files
5. overhaul UI/visual system so the product actually feels intentional

That is the path from “promising alpha” to “real MVP.”
