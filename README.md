# Wisp

Wisp is an AI FileOS desktop app for local-first scan, memory, cleanup, and safe file action proposals.

## Product Thesis

Wisp is not a generic upload sandbox, not a deterministic organizer-first app, and not an auto-destructive cleanup tool. The product center is:

- scan local folders directly from the desktop app
- build a resilient, rebuildable index over those files
- let search and the assistant ground answers in local file evidence
- let the agent propose safe actions with citations and explicit user acceptance

Filesystem state is the truth. SQLite and LanceDB are rebuildable caches and indexes.

## Architecture At A Glance

- Electron handles native folder/file access and desktop shell behavior.
- FastAPI exposes the backend APIs for scan, search, assistant, extraction, actions, and jobs.
- Celery + Redis run background scan jobs.
- SQLite stores job and indexed-file metadata.
- LanceDB stores semantic chunks for retrieval.

## Canonical Test Commands

Backend:

```bash
cd backend
./venv/bin/pytest --collect-only -q
./run_tests.sh -q
```

Frontend:

```bash
cd frontend
./node_modules/.bin/vitest --run src/__tests__/wispApiContract.test.ts
./node_modules/.bin/vitest --run src/views/__tests__/MemoryView.test.tsx
./node_modules/.bin/vitest --run src/views/__tests__/ScanView.test.tsx
```

## Plan Pack

The implementation program lives in:

- [docs/polish/PLAN1.md](docs/polish/PLAN1.md)
- [docs/ui/PLAN1.md](docs/ui/PLAN1.md)

Those files define the domain-pack rollout for backend/platform and UI work.
