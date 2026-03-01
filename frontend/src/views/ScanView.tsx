import { useState, useEffect, useRef } from 'react';
import {
    FolderPlus,
    RefreshCw,
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
import type { PipelineStatus, TaggedFile } from '../components/AppShell';

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
    onScan: (folder: string) => void;
    onOrganize: () => void;
    onSuggestDelete: () => void;
    onTagFiles: (provider: 'local' | 'api') => void;
    pipeline: PipelineStatus;
    taggedFiles: TaggedFile[];
    busy: string;
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

export default function ScanView({
    rootFolders,
    onAddFolder,
    onScan,
    onOrganize,
    onSuggestDelete,
    onTagFiles,
    pipeline,
    taggedFiles,
    busy,
}: ScanViewProps) {
    const hasRoot = rootFolders.length > 0;

    /* ── Celery job polling ── */
    const [job, setJob] = useState<JobState>(null);
    const [jobBusy, setJobBusy] = useState(false);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    /* ── Indexed files ── */
    const [indexedFiles, setIndexedFiles] = useState<IndexedFile[]>([]);
    const [showFiles, setShowFiles] = useState(false);

    useEffect(() => {
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, []);

    const fetchIndexedFiles = async (jobId?: string) => {
        try {
            const data = await window.wispApi.getIndexedFiles(jobId);
            setIndexedFiles(data.files || []);
        } catch {
            // Silently ignore — files will just be empty
        }
    };

    // Load any existing indexed files on mount
    useEffect(() => {
        fetchIndexedFiles();
    }, []);

    const startScanJob = async () => {
        if (jobBusy || rootFolders.length === 0) return;
        setJobBusy(true);
        setJob(null);
        setIndexedFiles([]);
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
                    setJob({
                        job_id: data.job_id,
                        status: data.status,
                        progress_current: data.progress_current,
                        progress_total: data.progress_total,
                        progress_message: data.progress_message,
                    });

                    if (data.status === 'success' || data.status === 'failed') {
                        if (timerRef.current) clearInterval(timerRef.current);
                        timerRef.current = null;
                        setJobBusy(false);
                        if (data.status === 'success') {
                            fetchIndexedFiles(job_id);
                            setShowFiles(true);
                        }
                    }
                } catch {
                    // keep polling
                }
            }, 1000);
        } catch {
            setJobBusy(false);
            setJob(null);
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
                    Wisp will index, tag, and help you clean up your files — all locally on your machine.
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

                <button className="scan-action-card" onClick={startScanJob} disabled={!!busy || jobBusy}>
                    <div className="scan-action-icon"><Search size={16} /></div>
                    <span className="scan-action-title">Scan &amp; Index</span>
                    <span className="scan-action-desc">Embed files via AI pipeline</span>
                </button>

                <button className="scan-action-card" onClick={() => onScan(rootFolders[0])} disabled={!!busy || jobBusy}>
                    <div className="scan-action-icon"><RefreshCw size={16} /></div>
                    <span className="scan-action-title">Rescan</span>
                    <span className="scan-action-desc">Refresh file index</span>
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
                    </div>

                    <div className="job-progress-track">
                        <div
                            className={`job-progress-fill ${isTerminal ? (job.status === 'success' ? 'done' : 'error') : ''}`}
                            style={{ width: `${pct}%` }}
                        />
                    </div>

                    <div className="job-progress-message">
                        {job.progress_message || '\u2014'}
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

            {/* ── Pipeline stats (from Electron scan, if any) ── */}
            {pipeline.indexed > 0 && indexedFiles.length === 0 && (
                <div className="scan-stats">
                    {[
                        { label: 'Indexed', value: pipeline.indexed },
                        { label: 'Previewed', value: pipeline.previewed },
                        { label: 'Embedded', value: pipeline.embedded },
                        { label: 'Scored', value: pipeline.scored },
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
