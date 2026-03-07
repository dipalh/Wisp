import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import ScanView from '../ScanView';

function renderScanView(overrides: Partial<Parameters<typeof ScanView>[0]> = {}) {
    const defaults = {
        rootFolders: ['/Users/test/Documents'],
        onAddFolder: vi.fn(),
        onOrganize: vi.fn(),
        onSuggestDelete: vi.fn(),
        onTagFiles: vi.fn(),
        taggedFiles: [] as any[],
        busy: '',
        onError: vi.fn(),
    };
    const props = { ...defaults, ...overrides };
    const result = render(<ScanView {...props} />);
    return { ...result, props };
}

/** Flush all pending microtasks (resolved promises). */
const flushMicrotasks = () => act(() => Promise.resolve());

describe('ScanView error propagation', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    /** Get the actual "Scan & Index" action button (not the text in the prompt). */
    function getScanButton() {
        return screen.getByRole('button', { name: /scan.*index/i });
    }

    it('calls onError when startScanJob IPC throws', async () => {
        window.wispApi.startScanJob = vi.fn().mockRejectedValue(
            new Error('Connection refused'),
        );

        const { props } = renderScanView();

        await act(async () => {
            fireEvent.click(getScanButton());
        });

        expect(props.onError).toHaveBeenCalledWith(
            expect.stringContaining('Connection refused'),
        );
    });

    it('calls onError when pollJob fails 3 consecutive times', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-1' });
        window.wispApi.pollJob = vi.fn().mockRejectedValue(
            new Error('Network error'),
        );

        const { props } = renderScanView();

        await act(async () => {
            fireEvent.click(getScanButton());
        });

        for (let i = 0; i < 3; i++) {
            await act(async () => {
                vi.advanceTimersByTime(1100);
            });
        }

        expect(props.onError).toHaveBeenCalledWith(
            expect.stringContaining('Network error'),
        );
    });

    it('resets poll failure counter on a successful poll', async () => {
        let callCount = 0;
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-2' });
        window.wispApi.pollJob = vi.fn().mockImplementation(() => {
            callCount++;
            if (callCount <= 2 || callCount >= 4) {
                return Promise.reject(new Error('Flaky'));
            }
            return Promise.resolve({
                job_id: 'j-2', type: 'scan', status: 'running',
                progress_current: 5, progress_total: 10,
                progress_message: 'Working…', updated_at: '',
            });
        });

        const { props } = renderScanView();

        await act(async () => {
            fireEvent.click(getScanButton());
        });

        for (let i = 0; i < 5; i++) {
            await act(async () => {
                vi.advanceTimersByTime(1100);
            });
        }

        expect(props.onError).not.toHaveBeenCalled();
    });

    it('calls onError when fetchIndexedFiles fails after success', async () => {
        window.wispApi.getIndexedFiles = vi.fn().mockRejectedValue(
            new Error('DB unavailable'),
        );
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-3' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-3', type: 'scan', status: 'success',
            progress_current: 10, progress_total: 10,
            progress_message: 'Done', updated_at: '',
        });

        const { props } = renderScanView();

        await act(async () => {
            fireEvent.click(getScanButton());
        });

        await act(async () => {
            vi.advanceTimersByTime(1100);
        });

        expect(props.onError).toHaveBeenCalledWith(
            expect.stringContaining('DB unavailable'),
        );
    });
});

describe('ScanView misleading state fixes', () => {
    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('does NOT call getIndexedFiles on mount', () => {
        const spy = vi.fn().mockResolvedValue({ files: [], total: 0 });
        window.wispApi.getIndexedFiles = spy;

        renderScanView();

        expect(spy).not.toHaveBeenCalled();
    });

    it('does NOT render a Rescan button', () => {
        renderScanView();
        expect(screen.queryByText('Rescan')).toBeNull();
    });

    it('does NOT render pipeline stats fallback (Previewed/Embedded/Scored labels)', () => {
        renderScanView();

        expect(screen.queryByText('Previewed')).toBeNull();
        expect(screen.queryByText('Embedded')).toBeNull();
        expect(screen.queryByText('Scored')).toBeNull();
    });

    it('shows prompt to run Scan & Index when no job has been run and no indexed files exist', () => {
        renderScanView();

        const prompt = screen.getByText(/analyze your files/i);
        expect(prompt).toBeInTheDocument();
    });

    it('does NOT show scan-stats section when no indexed files exist (no fake counts)', () => {
        renderScanView();

        expect(screen.queryByText('Deep')).toBeNull();
        expect(screen.queryByText('Preview')).toBeNull();
        expect(screen.queryByText('Card')).toBeNull();
        expect(screen.queryByText('Deletable')).toBeNull();
    });
});

describe('ScanView enhanced progress & debug panel', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    function getScanButton() {
        return screen.getByRole('button', { name: /scan.*index/i });
    }

    it('shows elapsed time during a running scan', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-elapsed' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-elapsed', type: 'scan', status: 'running',
            progress_current: 3, progress_total: 10,
            progress_message: 'Working…', updated_at: '',
        });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });

        // First poll
        await act(async () => { vi.advanceTimersByTime(1100); });

        // Advance 4 more seconds so elapsed ~5s
        await act(async () => { vi.advanceTimersByTime(4000); });

        const elapsedEl = screen.getByText(/elapsed/i);
        expect(elapsedEl).toBeInTheDocument();
        expect(elapsedEl.textContent).toMatch(/\d+s/);
    });

    it('shows percentage text alongside the progress bar', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-pct' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-pct', type: 'scan', status: 'running',
            stage: 'EMBEDDED',
            stats: {
                discovered: 20,
                previewed: 10,
                embedded: 5,
                scored: 2,
                cached: 1,
                failed: 0,
            },
            progress_current: 5, progress_total: 20,
            progress_message: 'Indexing…', updated_at: '',
        });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });

        expect(screen.getByText('25%')).toBeInTheDocument();
    });

    it('shows stage and stats in the debug panel from poll payloads', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-stage' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-stage', type: 'scan', status: 'running',
            stage: 'EMBEDDED',
            stats: {
                discovered: 12,
                previewed: 8,
                embedded: 4,
                scored: 3,
                cached: 2,
                failed: 1,
            },
            progress_current: 4, progress_total: 12,
            progress_message: 'Embedding files', updated_at: '',
        });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });
        await act(async () => { fireEvent.click(screen.getByText(/debug/i)); });

        expect(screen.getByText('Stage')).toBeInTheDocument();
        expect(screen.getByText('EMBEDDED')).toBeInTheDocument();
        expect(screen.getByText('Discovered')).toBeInTheDocument();
        expect(screen.getByText('12')).toBeInTheDocument();
        expect(screen.getByText('Failed')).toBeInTheDocument();
        expect(screen.getByText('1')).toBeInTheDocument();
    });

    it('accumulates debug log messages from polls', async () => {
        let pollCount = 0;
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-log' });
        window.wispApi.pollJob = vi.fn().mockImplementation(() => {
            pollCount++;
            return Promise.resolve({
                job_id: 'j-log', type: 'scan', status: 'running',
                progress_current: pollCount, progress_total: 10,
                progress_message: `Indexing file-${pollCount}.pdf`,
                updated_at: '',
            });
        });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });

        // 3 polls
        for (let i = 0; i < 3; i++) {
            await act(async () => { vi.advanceTimersByTime(1100); });
        }

        // Expand debug panel
        const toggle = screen.getByText(/debug/i);
        await act(async () => { fireEvent.click(toggle); });

        // file-1 and file-2 appear only in the debug log
        expect(screen.getByText(/file-1\.pdf/)).toBeInTheDocument();
        expect(screen.getByText(/file-2\.pdf/)).toBeInTheDocument();
        // file-3 appears in both the progress message AND the debug log
        expect(screen.getAllByText(/file-3\.pdf/).length).toBeGreaterThanOrEqual(1);
    });

    it('shows job_id and folders in the debug panel', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'abc-123-def' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'abc-123-def', type: 'scan', status: 'running',
            progress_current: 1, progress_total: 5,
            progress_message: 'Working…', updated_at: '',
        });

        renderScanView({ rootFolders: ['/Users/test/Downloads'] });

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });

        // Expand debug panel
        const toggle = screen.getByText(/debug/i);
        await act(async () => { fireEvent.click(toggle); });

        expect(screen.getByText(/abc-123-def/)).toBeInTheDocument();
        expect(screen.getByText(/\/Users\/test\/Downloads/)).toBeInTheDocument();
    });

    it('shows last poll time in the debug panel', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-poll-time' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-poll-time', type: 'scan', status: 'running',
            progress_current: 2, progress_total: 10,
            progress_message: 'Indexing…', updated_at: '',
        });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });

        const toggle = screen.getByText(/debug/i);
        await act(async () => { fireEvent.click(toggle); });

        // Should show some timestamp-like string for last poll
        expect(screen.getByText(/last poll/i)).toBeInTheDocument();
    });

    it('debug panel is collapsed by default', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-collapsed' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-collapsed', type: 'scan', status: 'running',
            progress_current: 1, progress_total: 5,
            progress_message: 'Working…', updated_at: '',
        });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });

        // Debug toggle exists but content is not visible
        expect(screen.getByText(/debug/i)).toBeInTheDocument();
        expect(screen.queryByText(/job id/i)).toBeNull();
    });
});

describe('ScanView Open in Finder + job-filtered files', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    function getScanButton() {
        return screen.getByRole('button', { name: /scan.*index/i });
    }

    const fakeFiles = [
        {
            file_id: 'f1', job_id: 'j-open', file_path: '/Users/test/report.pdf',
            name: 'report.pdf', ext: '.pdf', depth: 'deep', chunk_count: 5,
            engine: 'gemini', is_deletable: 0, tagged_os: 0, updated_at: '',
        },
        {
            file_id: 'f2', job_id: 'j-open', file_path: '/Users/test/photo.png',
            name: 'photo.png', ext: '.png', depth: 'card', chunk_count: 1,
            engine: 'gemini', is_deletable: 1, tagged_os: 1, updated_at: '',
        },
        {
            file_id: 'f3', job_id: 'j-open', file_path: '/Users/test/notes.md',
            name: 'notes.md', ext: '.md', depth: 'preview', chunk_count: 3,
            engine: 'gemini', is_deletable: 0, tagged_os: 0, updated_at: '',
        },
    ];

    async function runScanToCompletion() {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-open' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-open', type: 'scan', status: 'success',
            progress_current: 10, progress_total: 10,
            progress_message: 'Done', updated_at: '',
        });
        window.wispApi.getIndexedFiles = vi.fn().mockResolvedValue({
            files: fakeFiles, total: 3,
        });
        window.wispApi.openFile = vi.fn().mockResolvedValue({ ok: true });

        const result = renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        // First poll returns success → triggers fetchIndexedFiles
        await act(async () => { vi.advanceTimersByTime(1100); });
        // Let fetchIndexedFiles promise resolve
        await act(async () => { vi.advanceTimersByTime(0); });

        return result;
    }

    it('calls getIndexedFiles with the specific job_id after scan success', async () => {
        await runScanToCompletion();

        expect(window.wispApi.getIndexedFiles).toHaveBeenCalledWith('j-open');
    });

    it('renders all indexed files after scan completes', async () => {
        await runScanToCompletion();

        expect(screen.getByText('report.pdf')).toBeInTheDocument();
        expect(screen.getByText('photo.png')).toBeInTheDocument();
        expect(screen.getByText('notes.md')).toBeInTheDocument();
    });

    it('renders an Open button for each indexed file', async () => {
        await runScanToCompletion();

        const openButtons = screen.getAllByRole('button', { name: /open/i });
        expect(openButtons.length).toBe(3);
    });

    it('calls openFile with the correct path when Open is clicked', async () => {
        await runScanToCompletion();

        const openButtons = screen.getAllByRole('button', { name: /open/i });
        await act(async () => { fireEvent.click(openButtons[0]); });

        expect(window.wispApi.openFile).toHaveBeenCalledWith('/Users/test/report.pdf');
    });

    it('calls onError when openFile fails', async () => {
        window.wispApi.openFile = vi.fn().mockRejectedValue(
            new Error('File not found: /Users/test/report.pdf'),
        );
        // Need to re-mock the other APIs since runScanToCompletion overrides them
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-err' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-err', type: 'scan', status: 'success',
            progress_current: 10, progress_total: 10,
            progress_message: 'Done', updated_at: '',
        });
        window.wispApi.getIndexedFiles = vi.fn().mockResolvedValue({
            files: [fakeFiles[0]], total: 1,
        });

        const { props } = renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });
        await act(async () => { vi.advanceTimersByTime(0); });

        const openBtn = screen.getByRole('button', { name: /open/i });
        await act(async () => { fireEvent.click(openBtn); });

        expect(props.onError).toHaveBeenCalledWith(
            expect.stringContaining('File not found'),
        );
    });

    it('shows the correct indexed file count in the summary stats', async () => {
        await runScanToCompletion();

        // Should show "3" for Indexed stat
        expect(screen.getByText('3')).toBeInTheDocument();
    });

    it('shows a stable state badge for files missing externally', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-missing' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-missing', type: 'scan', status: 'success',
            progress_current: 1, progress_total: 1,
            progress_message: 'Done', updated_at: '',
        });
        window.wispApi.getIndexedFiles = vi.fn().mockResolvedValue({
            files: [{
                file_id: 'f-missing',
                job_id: 'j-missing',
                file_path: '/Users/test/missing.txt',
                name: 'missing.txt',
                ext: '.txt',
                depth: 'deep',
                chunk_count: 1,
                engine: 'local',
                is_deletable: 0,
                tagged_os: 0,
                updated_at: '',
                file_state: 'MISSING_EXTERNALLY',
                error_code: '',
                error_message: '',
            }],
            total: 1,
        });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });
        await act(async () => { vi.advanceTimersByTime(0); });

        expect(screen.getByText('Missing externally')).toBeInTheDocument();
        expect(screen.getByText(/rescan to refresh/i)).toBeInTheDocument();
    });
});

describe('ScanView validation — edge cases', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    function getScanButton() {
        return screen.getByRole('button', { name: /scan.*index/i });
    }

    it('shows "Scan failed" with error icon when job status is failed', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-fail' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-fail', type: 'scan', status: 'failed',
            progress_current: 3, progress_total: 10,
            progress_message: 'Error processing file.txt', updated_at: '',
        });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });

        expect(screen.getByText(/scan failed/i)).toBeInTheDocument();
    });

    it('does NOT fetch indexed files when job fails', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-fail2' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-fail2', type: 'scan', status: 'failed',
            progress_current: 0, progress_total: 10,
            progress_message: 'Crashed', updated_at: '',
        });
        window.wispApi.getIndexedFiles = vi.fn().mockResolvedValue({ files: [], total: 0 });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });

        expect(window.wispApi.getIndexedFiles).not.toHaveBeenCalled();
    });

    it('shows "Scan complete" with green check when job succeeds with 0 files', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-empty' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-empty', type: 'scan', status: 'success',
            progress_current: 0, progress_total: 0,
            progress_message: 'No files found', updated_at: '',
        });
        window.wispApi.getIndexedFiles = vi.fn().mockResolvedValue({ files: [], total: 0 });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });
        await act(async () => { vi.advanceTimersByTime(0); });

        expect(screen.getByText(/scan complete/i)).toBeInTheDocument();
    });

    it('does NOT show summary stats when scan succeeds but returns 0 files', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-empty2' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-empty2', type: 'scan', status: 'success',
            progress_current: 0, progress_total: 0,
            progress_message: 'No files found', updated_at: '',
        });
        window.wispApi.getIndexedFiles = vi.fn().mockResolvedValue({ files: [], total: 0 });

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });
        await act(async () => { vi.advanceTimersByTime(0); });

        expect(screen.queryByText('Indexed')).toBeNull();
        expect(screen.queryByText('Deep')).toBeNull();
    });

    it('disables all action buttons during an active scan', async () => {
        let resolveStart!: (v: any) => void;
        window.wispApi.startScanJob = vi.fn().mockImplementation(
            () => new Promise((r) => { resolveStart = r; }),
        );

        renderScanView();

        await act(async () => { fireEvent.click(getScanButton()); });

        const buttons = screen.getAllByRole('button');
        const disabledButtons = buttons.filter(b => (b as HTMLButtonElement).disabled);
        expect(disabledButtons.length).toBeGreaterThanOrEqual(6);

        await act(async () => {
            resolveStart({ job_id: 'j-buttons' });
        });
    });

    it('clears previous indexed files when starting a new scan', async () => {
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-clear' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-clear', type: 'scan', status: 'success',
            progress_current: 5, progress_total: 5,
            progress_message: 'Done', updated_at: '',
        });
        window.wispApi.getIndexedFiles = vi.fn().mockResolvedValue({
            files: [{
                file_id: 'f1', job_id: 'j-clear', file_path: '/a/b.txt',
                name: 'b.txt', ext: '.txt', depth: 'deep', chunk_count: 2,
                engine: 'gemini', is_deletable: 0, tagged_os: 0, updated_at: '',
            }],
            total: 1,
        });

        renderScanView();

        // First scan
        await act(async () => { fireEvent.click(getScanButton()); });
        await act(async () => { vi.advanceTimersByTime(1100); });
        await act(async () => { vi.advanceTimersByTime(0); });

        expect(screen.getByText('b.txt')).toBeInTheDocument();

        // Start second scan — files should clear
        window.wispApi.startScanJob = vi.fn().mockResolvedValue({ job_id: 'j-clear2' });
        window.wispApi.pollJob = vi.fn().mockResolvedValue({
            job_id: 'j-clear2', type: 'scan', status: 'running',
            progress_current: 1, progress_total: 10,
            progress_message: 'Indexing...', updated_at: '',
        });

        await act(async () => { fireEvent.click(getScanButton()); });

        expect(screen.queryByText('b.txt')).toBeNull();
    });
});
