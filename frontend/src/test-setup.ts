import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
import { assertWispApiContract } from './test/wispApiContract';

afterEach(() => {
    cleanup();
});

// Stub window.wispApi so component imports don't blow up.
// Individual tests override specific methods via vi.fn().
window.wispApi = {
    getUsername: () => 'test-user',
    pickFolder: () => Promise.resolve(null),
    scanFolder: () => Promise.resolve(null),
    organizeFolder: () => Promise.resolve({ moved: 0, skipped: 0 }),
    tagFiles: () => Promise.resolve([]),
    suggestDelete: () => Promise.resolve([]),
    trashPath: () => Promise.resolve({ ok: false }),
    readFileBase64: () => Promise.resolve(''),
    pickFileForOcr: () => Promise.resolve(null),
    extractText: () => Promise.resolve({ filename: '', text: '', confidence: 0 }),
    extractTextFromBuffer: () => Promise.resolve({ filename: '', text: '', confidence: 0 }),
    transcribeFile: () => Promise.resolve({ filename: '', text: '', duration_seconds: 0 }),
    speakText: () => Promise.resolve(''),
    getVoices: () => Promise.resolve({ voices: [] }),
    showInFolder: () => Promise.resolve({ ok: true }),
    openPath: () => Promise.resolve({ ok: true }),
    askAssistant: () => Promise.resolve({
        answer: '',
        proposals: [],
        query: '',
        sources: [],
        deepened_files: [],
    }),
    startScanJob: () => Promise.resolve({ job_id: 'stub' }),
    pollJob: () => Promise.resolve({
        job_id: 'stub', type: 'scan', status: 'queued' as const,
        progress_current: 0, progress_total: 0, progress_message: '',
        updated_at: '',
    }),
    getIndexedFiles: () => Promise.resolve({ files: [], total: 0 }),
    openFile: () => Promise.resolve({ ok: true }),
    searchMemory: () => Promise.resolve({ results: [], query: '', total: 0 }),
    undoOrganize: () => Promise.resolve({ ok: true, reversed: 0, failed: 0, details: { reversed: [], failed: [] } }),
    canUndoOrganize: () => Promise.resolve({ canUndo: false }),
    onUndoTriggered: () => () => {},
    onUndoAvailable: () => () => {},
};

assertWispApiContract(window.wispApi);
