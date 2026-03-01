import { useEffect, useRef, useState, useCallback } from 'react';
import { X, Loader2, CheckCircle2, XCircle } from 'lucide-react';

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
        setLogs(['Starting scan...']);

        const t0 = Date.now();
        elapsedRef.current = setInterval(() => {
            setElapsed(Math.round((Date.now() - t0) / 1000));
        }, 1000);

        (async () => {
            try {
                const { job_id } = await window.wispApi.startScanJob(rootFolders);
                setJob({ job_id, status: 'queued', progress_current: 0, progress_total: 0, progress_message: 'Queued...' });
                setLogs(prev => [...prev, `Job ${job_id.slice(0, 8)} created`]);

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
                <div className="modal-header">
                    <h3 className="modal-title">
                        {job?.status === 'success' && <CheckCircle2 size={18} className="modal-icon-success" />}
                        {job?.status === 'failed' && <XCircle size={18} className="modal-icon-error" />}
                        {(!isDone) && <Loader2 size={18} className="spin" />}
                        {job?.status === 'success' ? 'Scan Complete' :
                         job?.status === 'failed' ? 'Scan Failed' : 'Scanning...'}
                    </h3>
                    {isDone && (
                        <button className="modal-close" onClick={handleClose}>
                            <X size={16} />
                        </button>
                    )}
                </div>

                <div className="scan-modal-progress">
                    <div className="scan-modal-bar-track">
                        <div
                            className={`scan-modal-bar-fill ${job?.status === 'failed' ? 'error' : ''}`}
                            style={{ width: `${isDone && job?.status === 'success' ? 100 : pct}%` }}
                        />
                    </div>
                    <div className="scan-modal-stats">
                        <span>{pct}%</span>
                        <span>{job?.progress_current ?? 0} / {job?.progress_total ?? '?'} files</span>
                        <span>{formatElapsed(elapsed)}</span>
                    </div>
                </div>

                <div className="scan-modal-message">
                    {job?.progress_message || 'Preparing...'}
                </div>

                <div className="scan-modal-logs">
                    {logs.map((line, i) => (
                        <div key={i} className="scan-modal-log-line">{line}</div>
                    ))}
                    <div ref={logsEndRef} />
                </div>

                {isDone && (
                    <div className="scan-modal-footer">
                        <button className="btn btn-primary" onClick={handleClose}>
                            Done
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
