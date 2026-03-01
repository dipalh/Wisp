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

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, []);

    const startScanJob = async () => {
        if (jobBusy) return;
        setJobBusy(true);
        setJob(null);
        try {
            const { job_id } = await window.wispApi.startScanJob();
            setJob({
                job_id,
                status: 'queued',
                progress_current: 0,
                progress_total: 0,
                progress_message: 'Starting...',
            });

            // Poll every 1s
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
                    }
                } catch {
                    // If polling fails, keep trying
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

    /* ──────────────────────────────────────────────
     * Empty state — icon + title + desc + button
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
     * Active state — action cards + job progress
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
                    <div className="scan-action-icon"><RefreshCw size={16} /></div>
                    <span className="scan-action-title">Scan (Celery)</span>
                    <span className="scan-action-desc">Run background job</span>
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
                            {job.status === 'queued' && 'Queued…'}
                            {job.status === 'running' && 'Scanning…'}
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
                        {job.progress_message || '—'}
                    </div>
                </div>
            )}

            {/* Pipeline stats */}
            {pipeline.indexed > 0 && (
                <div className="scan-stats">
                    {[
                        { label: 'Indexed', value: pipeline.indexed },
                        { label: 'Previewed', value: pipeline.previewed },
                        { label: 'Embedded', value: pipeline.embedded },
                        { label: 'Scored', value: pipeline.scored },
                    ].map((s) => (
                        <div className="scan-stat" key={s.label}>
                            <span className="scan-stat-value">
                                {s.value > 0 ? s.value.toLocaleString() : '—'}
                            </span>
                            <span className="scan-stat-label">{s.label}</span>
                        </div>
                    ))}
                </div>
            )}

            {/* Tagged files */}
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
