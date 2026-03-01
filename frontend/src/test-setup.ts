import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
    cleanup();
});

// Stub window.wispApi so component imports don't blow up.
// Individual tests override specific methods via vi.fn().
(window as any).wispApi = {
    pickFolder: () => Promise.resolve(null),
    scanFolder: () => Promise.resolve(null),
    organizeFolder: () => Promise.resolve({ moved: 0, skipped: 0 }),
    tagFiles: () => Promise.resolve([]),
    suggestDelete: () => Promise.resolve([]),
    trashPath: () => Promise.resolve({ ok: false }),
    startScanJob: () => Promise.resolve({ job_id: 'stub' }),
    pollJob: () => Promise.resolve({
        job_id: 'stub', type: 'scan', status: 'queued' as const,
        progress_current: 0, progress_total: 0, progress_message: '',
        updated_at: '',
    }),
    getIndexedFiles: () => Promise.resolve({ files: [], total: 0 }),
    openFile: () => Promise.resolve({ ok: true }),
    searchMemory: () => Promise.resolve({ results: [], query: '', total: 0 }),
};
