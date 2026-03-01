import { useEffect, useRef, useState, useCallback } from 'react';
import { X, Loader2, CheckCircle2, XCircle, FolderSearch, Zap, FileText } from 'lucide-react';

type JobState = {
    job_id: string;
    status: 'queued' | 'running' | 'success' | 'failed';
    progress_current: number;
    progress_total: number;
    progress_message: string;
};

type ScanModalProps = {
    open: boolean;
    rootFolders: string[];
    onClose: () => void;
    onError: (msg: string) => void;
    onComplete: (jobId: string) => void;
};

export default function ScanModal({ open, rootFolders, onClose, onError, onComplete }: ScanModalProps) {
    const [job, setJob] = useState<JobState | null>(null);
    const [elapsed, setElapsed] = useState(0);
    const [logs, setLogs] = useState<string[]>([]);
    const [started, setStarted] = useState(false);
    const [filesProcessed, setFilesProcessed] = useState(0);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const logsEndRef = useRef<HTMLDivElement>(null);

    const cleanup = useCallback(() => {
        if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
        if (elapsedRef.current) { clearInterval(elapsedRef.current); elapsedRef.current = null; }
    }, []);

    useEffect(() => () => cleanup(), [cleanup]);

    useEffect(() => {
        logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    useEffect(() => {
        if (!open || started || rootFolders.length === 0) return;
        setStarted(true);
        setJob(null);
        setElapsed(0);
        setFilesProcessed(0);
        setLogs(['Initializing scan pipeline...']);

        const t0 = Date.now();
        elapsedRef.current = setInterval(() => {
            setElapsed(Math.round((Date.now() - t0) / 1000));
        }, 1000);

        (async () => {
            try {
                const { job_id } = await window.wispApi.startScanJob(rootFolders);
                setJob({ job_id, status: 'queued', progress_current: 0, progress_total: 0, progress_message: 'Queued...' });
                setLogs(prev => [...prev, `Job ${job_id.slice(0, 8)} created`, 'Waiting for worker...']);

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
                        setFilesProcessed(data.progress_current || 0);
                        if (data.progress_message) {
                            setLogs(prev => {
                                const next = [...prev, data.progress_message];
                                return next.length > 50 ? next.slice(-50) : next;
                            });
                        }
                        if (data.status === 'success' || data.status === 'failed') {
                            cleanup();
                            if (data.status === 'success') onComplete(job_id);
                        }
                    } catch {
                        // poll failure — keep going
                    }
                }, 1500);
            } catch (e: any) {
                cleanup();
                onError(`Scan failed to start: ${e?.message ?? e}`);
                setJob({ job_id: '', status: 'failed', progress_current: 0, progress_total: 0, progress_message: e?.message ?? 'Failed' });
            }
        })();
    }, [open, started, rootFolders, cleanup, onError, onComplete]);

    const handleClose = () => {
        if (job?.status === 'running' || job?.status === 'queued') return;
        cleanup();
        setStarted(false);
        onClose();
    };

    if (!open) return null;

    const pct = job && job.progress_total > 0
        ? Math.round((job.progress_current / job.progress_total) * 100)
        : 0;

    const isDone = job?.status === 'success' || job?.status === 'failed';

    const formatElapsed = (s: number) => {
        const m = Math.floor(s / 60);
        const sec = s % 60;
        return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
    };

    return (
        <div className="modal-overlay" onClick={isDone ? handleClose : undefined}>
            <div className="modal-content scan-modal" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="modal-header">
                    <h3 className="modal-title">
                        {job?.status === 'success' && <CheckCircle2 size={20} className="modal-icon-success" />}
                        {job?.status === 'failed' && <XCircle size={20} className="modal-icon-error" />}
                        {(!isDone) && <Loader2 size={20} className="spin" />}
                        {job?.status === 'success' ? 'Scan Complete' :
                         job?.status === 'failed' ? 'Scan Failed' : 'Scanning Files...'}
                    </h3>
                    {isDone && (
                        <button className="modal-close" onClick={handleClose}>
                            <X size={16} />
                        </button>
                    )}
                </div>

                {/* Stats row */}
                <div className="scan-modal-stats-row">
                    <div className="scan-modal-stat">
                        <FolderSearch size={14} />
                        <span className="scan-modal-stat-value">{rootFolders.length}</span>
                        <span className="scan-modal-stat-label">Folders</span>
                    </div>
                    <div className="scan-modal-stat">
                        <FileText size={14} />
                        <span className="scan-modal-stat-value">{filesProcessed}</span>
                        <span className="scan-modal-stat-label">Processed</span>
                    </div>
                    <div className="scan-modal-stat">
                        <Zap size={14} />
                        <span className="scan-modal-stat-value">{formatElapsed(elapsed)}</span>
                        <span className="scan-modal-stat-label">Elapsed</span>
                    </div>
                </div>

                {/* Progress */}
                <div className="scan-modal-progress">
                    <div className="scan-modal-bar-track">
                        <div
                            className={`scan-modal-bar-fill ${job?.status === 'failed' ? 'error' : ''} ${!isDone && pct > 0 ? 'animating' : ''}`}
                            style={{ width: `${isDone && job?.status === 'success' ? 100 : pct}%` }}
                        />
                    </div>
                    <div className="scan-modal-stats">
                        <span>{pct}% complete</span>
                        <span>{job?.progress_current ?? 0} / {job?.progress_total ?? '?'} files</span>
                    </div>
                </div>

                {/* Current operation message */}
                <div className="scan-modal-message">
                    <span className="scan-modal-message-dot" />
                    {job?.progress_message || 'Preparing...'}
                </div>

                {/* Log output */}
                <div className="scan-modal-logs">
                    {logs.map((line, i) => (
                        <div key={i} className={`scan-modal-log-line ${i === logs.length - 1 ? 'latest' : ''}`}>
                            <span className="scan-modal-log-ts">{String(i + 1).padStart(3, ' ')}</span>
                            {line}
                        </div>
                    ))}
                    <div ref={logsEndRef} />
                </div>

                {/* Footer */}
                {isDone ? (
                    <div className="scan-modal-footer">
                        {job?.status === 'success' && (
                            <span className="scan-modal-footer-summary">
                                Successfully indexed {job.progress_total} files in {formatElapsed(elapsed)}
                            </span>
                        )}
                        <button className="btn btn-primary" onClick={handleClose}>
                            {job?.status === 'success' ? 'View Results' : 'Close'}
                        </button>
                    </div>
                ) : (
                    <div className="scan-modal-footer">
                        <span className="scan-modal-footer-hint">
                            This may take a few minutes depending on the number of files...
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
}
