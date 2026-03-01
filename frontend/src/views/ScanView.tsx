import { useState, useEffect, useRef } from 'react';
import {
    FolderPlus,
    FolderOpen,
    Wand2,
    Trash2,
    Tags,
    CheckCircle2,
    XCircle,
    Loader2,
    FileText,
    AlertTriangle,
    Search,
} from 'lucide-react';
import type { TaggedFile } from '../components/AppShell';

/* ── Job progress state ── */
type JobState = {
    job_id: string;
    status: 'queued' | 'running' | 'success' | 'failed';
    progress_current: number;
    progress_total: number;
    progress_message: string;
} | null;

type IndexedFile = {
    file_id: string;
    job_id: string;
    file_path: string;
    name: string;
    ext: string;
    depth: string;
    chunk_count: number;
    engine: string;
    is_deletable: number;
    tagged_os: number;
    updated_at: string;
};

type ScanViewProps = {
    rootFolders: string[];
    onAddFolder: () => void;
    onOrganize: () => void;
    onSuggestDelete: () => void;
    onTagFiles: (provider: 'local' | 'api') => void;
    taggedFiles: TaggedFile[];
    busy: string;
    onError: (message: string) => void;
    onOpenScanModal?: () => void;
    completedJobId?: string | null;
};

const DEPTH_LABELS: Record<string, string> = {
    deep: 'Full',
    preview: 'Preview',
    card: 'Card',
};

const DEPTH_COLORS: Record<string, string> = {
    deep: 'var(--accent)',
    preview: '#d69e2e',
    card: 'var(--text-faint)',
};

const MAX_POLL_FAILURES = 3;

export default function ScanView({
    rootFolders,
    onAddFolder,
    onOrganize,
    onSuggestDelete,
    onTagFiles,
    taggedFiles,
    busy,
    onError,
    onOpenScanModal,
    completedJobId,
}: ScanViewProps) {
    const hasRoot = rootFolders.length > 0;

    /* ── Celery job polling ── */
    const [job, setJob] = useState<JobState>(null);
    const [jobBusy, setJobBusy] = useState(false);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollFailures = useRef(0);

    /* ── Debug / truth panel ── */
    const [scanStartTime, setScanStartTime] = useState<number | null>(null);
    const [elapsed, setElapsed] = useState(0);
    const [debugLog, setDebugLog] = useState<string[]>([]);
    const [showDebug, setShowDebug] = useState(false);
    const [lastPollTime, setLastPollTime] = useState('');
    const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);

    /* ── Indexed files ── */
    const [indexedFiles, setIndexedFiles] = useState<IndexedFile[]>([]);
    const [showFiles, setShowFiles] = useState(false);

    useEffect(() => {
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
            if (elapsedRef.current) clearInterval(elapsedRef.current);
        };
    }, []);

    /* When modal scan completes, fetch results */
    useEffect(() => {
        if (completedJobId) {
            fetchIndexedFiles(completedJobId);
            setShowFiles(true);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [completedJobId]);

    const fetchIndexedFiles = async (jobId?: string) => {
        try {
            const data = await window.wispApi.getIndexedFiles(jobId);
            setIndexedFiles(data.files || []);
        } catch (e: any) {
            onError(`Failed to load indexed files: ${e?.message ?? e}`);
        }
    };

    const handleOpenFile = async (filePath: string) => {
        try {
            await window.wispApi.openFile(filePath);
        } catch (e: any) {
            onError(`Open failed: ${e?.message ?? e}`);
        }
    };

    const stopElapsedTimer = () => {
        if (elapsedRef.current) {
            clearInterval(elapsedRef.current);
            elapsedRef.current = null;
        }
    };

    const startScanJob = async () => {
        if (jobBusy || rootFolders.length === 0) return;
        setJobBusy(true);
        setJob(null);
        setIndexedFiles([]);
        pollFailures.current = 0;

        const t0 = Date.now();
        setScanStartTime(t0);
        setElapsed(0);
        setDebugLog(['Starting scan…']);
        setLastPollTime('');

        stopElapsedTimer();
        elapsedRef.current = setInterval(() => {
            setElapsed(Math.round((Date.now() - t0) / 1000));
        }, 1000);

        try {
            const { job_id } = await window.wispApi.startScanJob(rootFolders);
            setJob({
                job_id,
                status: 'queued',
                progress_current: 0,
                progress_total: 0,
                progress_message: 'Starting\u2026',
            });

            timerRef.current = setInterval(async () => {
                try {
                    const data = await window.wispApi.pollJob(job_id);
                    pollFailures.current = 0;
                    setLastPollTime(new Date().toLocaleTimeString());
                    setJob({
                        job_id: data.job_id,
                        status: data.status,
                        progress_current: data.progress_current,
                        progress_total: data.progress_total,
                        progress_message: data.progress_message,
                    });

                    if (data.progress_message) {
                        setDebugLog(prev => {
                            const next = [...prev, data.progress_message];
                            return next.length > 20 ? next.slice(-20) : next;
                        });
                    }

                    if (data.status === 'success' || data.status === 'failed') {
                        if (timerRef.current) clearInterval(timerRef.current);
                        timerRef.current = null;
                        stopElapsedTimer();
                        setJobBusy(false);
                        if (data.status === 'success') {
                            fetchIndexedFiles(job_id);
                            setShowFiles(true);
                        }
                    }
                } catch (e: any) {
                    pollFailures.current += 1;
                    if (pollFailures.current >= MAX_POLL_FAILURES) {
                        if (timerRef.current) clearInterval(timerRef.current);
                        timerRef.current = null;
                        stopElapsedTimer();
                        setJobBusy(false);
                        onError(`Poll failed after ${MAX_POLL_FAILURES} attempts: ${e?.message ?? e}`);
                    }
                }
            }, 1000);
        } catch (e: any) {
            setJobBusy(false);
            setJob(null);
            stopElapsedTimer();
            onError(`Scan failed: ${e?.message ?? e}`);
        }
    };

    const pct = job && job.progress_total > 0
        ? Math.round((job.progress_current / job.progress_total) * 100)
        : 0;

    const isTerminal = job?.status === 'success' || job?.status === 'failed';

    /* ── Stats from indexed files ── */
    const deepCount = indexedFiles.filter(f => f.depth === 'deep').length;
    const previewCount = indexedFiles.filter(f => f.depth === 'preview').length;
    const cardCount = indexedFiles.filter(f => f.depth === 'card').length;
    const deletableCount = indexedFiles.filter(f => f.is_deletable).length;

    /* ──────────────────────────────────────────────
     * Empty state
     * ────────────────────────────────────────────── */
    if (!hasRoot) {
        return (
            <div className="empty-state">
                <div className="empty-state-icon">
                    <FolderPlus size={24} strokeWidth={1.5} />
                </div>
                <h2 className="empty-state-title">Choose a folder to get started</h2>
                <p className="empty-state-desc">
                    Wisp will index, tag, and help you clean up your files, all locally on your machine.
                </p>
                <button className="btn btn-primary" onClick={onAddFolder}>
                    <FolderPlus size={15} />
                    Choose folder
                </button>
            </div>
        );
    }

    /* ──────────────────────────────────────────────
     * Active state
     * ────────────────────────────────────────────── */
    return (
        <div className="doc-flow">
            <div className="scan-grid">
                <button className="scan-action-card" onClick={onAddFolder} disabled={!!busy || jobBusy}>
                    <div className="scan-action-icon"><FolderPlus size={16} /></div>
                    <span className="scan-action-title">Add folder</span>
                    <span className="scan-action-desc">Index another directory</span>
                </button>

                <button className="scan-action-card" onClick={() => { if (onOpenScanModal) onOpenScanModal(); else startScanJob(); }} disabled={!!busy || jobBusy}>
                    <div className="scan-action-icon"><Search size={16} /></div>
                    <span className="scan-action-title">Scan &amp; Index</span>
                    <span className="scan-action-desc">Embed files via AI pipeline</span>
                </button>

                <button className="scan-action-card" onClick={onOrganize} disabled={!!busy || jobBusy}>
                    <div className="scan-action-icon"><Wand2 size={16} /></div>
                    <span className="scan-action-title">Organize</span>
                    <span className="scan-action-desc">Sort by category</span>
                </button>

                <button className="scan-action-card" onClick={onSuggestDelete} disabled={!!busy || jobBusy}>
                    <div className="scan-action-icon"><Trash2 size={16} /></div>
                    <span className="scan-action-title">Find deletables</span>
                    <span className="scan-action-desc">Cleanup candidates</span>
                </button>

                <button className="scan-action-card" onClick={() => onTagFiles('local')} disabled={!!busy || jobBusy}>
                    <div className="scan-action-icon"><Tags size={16} /></div>
                    <span className="scan-action-title">Generate tags</span>
                    <span className="scan-action-desc">Auto-tag locally</span>
                </button>

                <button className="scan-action-card" onClick={() => onTagFiles('api')} disabled={!!busy || jobBusy}>
                    <div className="scan-action-icon"><Tags size={16} /></div>
                    <span className="scan-action-title">AI tags</span>
                    <span className="scan-action-desc">Richer tags via API</span>
                </button>
            </div>

            {/* ── Job Progress Panel ── */}
            {job && (
                <div className="job-progress-panel">
                    <div className="job-progress-header">
                        {job.status === 'running' && <Loader2 size={16} className="spin" />}
                        {job.status === 'success' && <CheckCircle2 size={16} style={{ color: 'var(--accent)' }} />}
                        {job.status === 'failed' && <XCircle size={16} style={{ color: '#e53e3e' }} />}
                        <span className="job-progress-status">
                            {job.status === 'queued' && 'Queued\u2026'}
                            {job.status === 'running' && 'Indexing\u2026'}
                            {job.status === 'success' && 'Scan complete'}
                            {job.status === 'failed' && 'Scan failed'}
                        </span>
                        {job.progress_total > 0 && (
                            <span className="job-progress-count">
                                {job.progress_current} / {job.progress_total}
                            </span>
                        )}
                        {pct > 0 && (
                            <span className="job-progress-pct">{pct}%</span>
                        )}
                    </div>

                    <div className="job-progress-track">
                        <div
                            className={`job-progress-fill ${isTerminal ? (job.status === 'success' ? 'done' : 'error') : ''}`}
                            style={{ width: `${pct}%` }}
                        />
                    </div>

                    <div className="job-progress-footer">
                        <span className="job-progress-message">
                            {job.progress_message || '\u2014'}
                        </span>
                        {scanStartTime && (
                            <span className="job-progress-elapsed">
                                Elapsed: {elapsed}s
                            </span>
                        )}
                    </div>

                    {/* ── Debug / Truth Panel (collapsible) ── */}
                    <div className="debug-panel">
                        <div
                            className="debug-panel-toggle"
                            onClick={() => setShowDebug(v => !v)}
                        >
                            Debug {showDebug ? '▾' : '▸'}
                        </div>
                        {showDebug && (
                            <div className="debug-panel-body">
                                <div className="debug-row">
                                    <span className="debug-label">Job ID</span>
                                    <span className="debug-value">{job.job_id}</span>
                                </div>
                                <div className="debug-row">
                                    <span className="debug-label">Folders</span>
                                    <span className="debug-value">{rootFolders.join(', ')}</span>
                                </div>
                                <div className="debug-row">
                                    <span className="debug-label">Status</span>
                                    <span className="debug-value">{job.status}</span>
                                </div>
                                <div className="debug-row">
                                    <span className="debug-label">Progress</span>
                                    <span className="debug-value">{job.progress_current}/{job.progress_total}</span>
                                </div>
                                <div className="debug-row">
                                    <span className="debug-label">Last poll</span>
                                    <span className="debug-value">{lastPollTime || '-'}</span>
                                </div>
                                {debugLog.length > 0 && (
                                    <div className="debug-log">
                                        <span className="debug-label">Log</span>
                                        <div className="debug-log-entries">
                                            {debugLog.map((msg, i) => (
                                                <div key={i} className="debug-log-entry">{msg}</div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ── Indexed files summary ── */}
            {indexedFiles.length > 0 && (
                <div className="scan-stats">
                    {[
                        { label: 'Indexed', value: indexedFiles.length },
                        { label: 'Deep', value: deepCount },
                        { label: 'Preview', value: previewCount },
                        { label: 'Card', value: cardCount },
                        { label: 'Deletable', value: deletableCount },
                    ].map((s) => (
                        <div className="scan-stat" key={s.label}>
                            <span className="scan-stat-value">
                                {s.value > 0 ? s.value.toLocaleString() : '\u2014'}
                            </span>
                            <span className="scan-stat-label">{s.label}</span>
                        </div>
                    ))}
                </div>
            )}

            {/* ── Empty prompt — no job has run yet ── */}
            {!job && indexedFiles.length === 0 && taggedFiles.length === 0 && (
                <div className="scan-empty-prompt">
                    <Search size={18} style={{ color: 'var(--text-faint)' }} />
                    <span>Run <strong>Scan &amp; Index</strong> to analyze your files with the AI pipeline.</span>
                </div>
            )}

            {/* ── Indexed files list ── */}
            {indexedFiles.length > 0 && (
                <>
                    <div className="doc-divider" />
                    <div
                        className="scan-file-list-title"
                        style={{ marginTop: 16, cursor: 'pointer', userSelect: 'none' }}
                        onClick={() => setShowFiles(v => !v)}
                    >
                        Indexed files · {indexedFiles.length}
                        <span style={{ fontSize: 11, marginLeft: 6, color: 'var(--text-faint)' }}>
                            {showFiles ? '▾' : '▸'}
                        </span>
                    </div>
                    {showFiles && indexedFiles.slice(0, 100).map((file) => (
                        <div className="file-item" key={file.file_id} title={file.file_path}>
                            <div className="file-item-info">
                                <div className="file-item-name" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <FileText size={13} style={{ flexShrink: 0, color: 'var(--text-faint)' }} />
                                    {file.name}
                                    <span
                                        className="tag"
                                        style={{
                                            fontSize: 10,
                                            color: DEPTH_COLORS[file.depth] || 'var(--text-faint)',
                                            borderColor: DEPTH_COLORS[file.depth] || 'var(--border)',
                                        }}
                                    >
                                        {DEPTH_LABELS[file.depth] || file.depth}
                                    </span>
                                    {file.chunk_count > 0 && (
                                        <span className="tag" style={{ fontSize: 10 }}>
                                            {file.chunk_count} chunks
                                        </span>
                                    )}
                                    {file.is_deletable === 1 && (
                                        <span className="tag" style={{ fontSize: 10, color: '#e53e3e', borderColor: '#e53e3e' }}>
                                            <AlertTriangle size={10} style={{ marginRight: 2 }} />
                                            Deletable
                                        </span>
                                    )}
                                </div>
                                <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 1, paddingLeft: 19 }}>
                                    {file.file_path}
                                </div>
                            </div>
                            <button
                                className="file-item-open"
                                aria-label={`Open ${file.name}`}
                                onClick={() => handleOpenFile(file.file_path)}
                            >
                                <FolderOpen size={13} />
                                Open
                            </button>
                        </div>
                    ))}
                    {indexedFiles.length > 100 && showFiles && (
                        <div style={{ fontSize: 12, color: 'var(--text-faint)', padding: '8px 0' }}>
                            … and {indexedFiles.length - 100} more files
                        </div>
                    )}
                </>
            )}

            {/* ── Tagged files ── */}
            {taggedFiles.length > 0 && (
                <>
                    <div className="doc-divider" />
                    <div className="scan-file-list-title" style={{ marginTop: 16 }}>
                        Tagged files · {taggedFiles.length}
                    </div>
                    {taggedFiles.slice(0, 12).map((file) => (
                        <div className="file-item" key={file.path} title={file.path}>
                            <div className="file-item-info">
                                <div className="file-item-name">{file.name}</div>
                                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '2px' }}>
                                    {file.tags.slice(0, 4).map((tag) => (
                                        <span className="tag" key={tag}>{tag}</span>
                                    ))}
                                    {file.tags.length > 4 && (
                                        <span className="tag" style={{ color: 'var(--text-faint)' }}>
                                            +{file.tags.length - 4}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                </>
            )}
        </div>
    );
}
