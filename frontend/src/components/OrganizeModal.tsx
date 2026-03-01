import { useEffect, useRef, useState, useCallback } from 'react';
import { X, Loader2, CheckCircle2, XCircle, FolderSync, FileText, Image, Music, Video, Archive, Code2, Package } from 'lucide-react';

type OrganizeResult = {
    moved: number;
    skipped: number;
    categories: Record<string, number>;
};

type OrganizeModalProps = {
    open: boolean;
    folder: string;
    onClose: () => void;
    onError: (msg: string) => void;
    /** Runs the organize operation and returns the result. Should NOT set busy externally. */
    onOrganize: () => Promise<OrganizeResult>;
};

const CATEGORY_ICONS: Record<string, typeof FileText> = {
    Documents: FileText,
    Images: Image,
    Audio: Music,
    Videos: Video,
    Archives: Archive,
    Code: Code2,
    Others: Package,
};

type Phase = 'running' | 'success' | 'failed';

export default function OrganizeModal({ open, folder, onClose, onError, onOrganize }: OrganizeModalProps) {
    const [phase, setPhase] = useState<Phase>('running');
    const [result, setResult] = useState<OrganizeResult | null>(null);
    const [elapsed, setElapsed] = useState(0);
    const [errorMsg, setErrorMsg] = useState('');
    const [started, setStarted] = useState(false);
    const [tick, setTick] = useState(0);
    const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const cleanup = useCallback(() => {
        if (elapsedRef.current) { clearInterval(elapsedRef.current); elapsedRef.current = null; }
    }, []);

    useEffect(() => () => cleanup(), [cleanup]);

    useEffect(() => {
        if (!open || started || !folder) return;
        setStarted(true);
        setPhase('running');
        setResult(null);
        setElapsed(0);
        setTick(0);
        setErrorMsg('');

        const t0 = Date.now();
        elapsedRef.current = setInterval(() => {
            setElapsed(Math.round((Date.now() - t0) / 1000));
            setTick(t => t + 1);
        }, 400);

        const MIN_DISPLAY_MS = 900; // keep spinner visible at least this long for visual feedback

        const run = async () => {
            const startedAt = Date.now();
            try {
                const res = await onOrganize();
                const spent = Date.now() - startedAt;
                if (spent < MIN_DISPLAY_MS) {
                    await new Promise(resolve => setTimeout(resolve, MIN_DISPLAY_MS - spent));
                }
                cleanup();
                setResult(res);
                setPhase('success');
            } catch (e: any) {
                cleanup();
                const msg = e?.message ?? String(e);
                setErrorMsg(msg);
                setPhase('failed');
                onError(`Organize failed: ${msg}`);
            }
        };
        run();
    }, [open, started, folder, onOrganize, cleanup, onError]);

    const handleClose = () => {
        if (phase === 'running') return;
        cleanup();
        setStarted(false);
        onClose();
    };

    if (!open) return null;

    const isDone = phase === 'success' || phase === 'failed';

    const formatElapsed = (s: number) => {
        const m = Math.floor(s / 60);
        const sec = s % 60;
        return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
    };

    const folderName = folder.split(/[\\/]/).pop() || folder;

    /* Animated "working" dots */
    const dots = '.'.repeat((tick % 3) + 1);

    const cats = result
        ? Object.entries(result.categories).sort((a, b) => b[1] - a[1])
        : [];

    return (
        <div className="modal-overlay" onClick={isDone ? handleClose : undefined}>
            <div className="modal-content organize-modal" onClick={e => e.stopPropagation()}>

                {/* Header */}
                <div className="modal-header">
                    <h3 className="modal-title">
                        {phase === 'success' && <CheckCircle2 size={20} className="modal-icon-success" />}
                        {phase === 'failed' && <XCircle size={20} className="modal-icon-error" />}
                        {phase === 'running' && <Loader2 size={20} className="spin" />}
                        {phase === 'success' ? 'Organize Complete' :
                         phase === 'failed' ? 'Organize Failed' : `Organizing${dots}`}
                    </h3>
                    {isDone && (
                        <button className="modal-close" onClick={handleClose}>
                            <X size={16} />
                        </button>
                    )}
                </div>

                {/* Folder + elapsed strip */}
                <div className="organize-modal-meta">
                    <div className="organize-modal-meta-item">
                        <FolderSync size={13} />
                        <span className="organize-modal-meta-label">{folderName}</span>
                    </div>
                    <div className="organize-modal-meta-sep" />
                    <div className="organize-modal-meta-item">
                        <span>{formatElapsed(elapsed)}</span>
                    </div>
                </div>

                {/* Running — animated bar */}
                {phase === 'running' && (
                    <div className="organize-modal-progress">
                        <div className="organize-modal-bar-track">
                            <div className="organize-modal-bar-indeterminate" />
                        </div>
                        <p className="organize-modal-hint">Sorting files by type into category folders...</p>
                    </div>
                )}

                {/* Success — stats + category breakdown */}
                {phase === 'success' && result && (
                    <div className="organize-modal-result">
                        <div className="organize-modal-stats">
                            <div className="organize-modal-stat">
                                <span className="organize-modal-stat-value">{result.moved}</span>
                                <span className="organize-modal-stat-label">Moved</span>
                            </div>
                            <div className="organize-modal-stat">
                                <span className="organize-modal-stat-value">{result.skipped}</span>
                                <span className="organize-modal-stat-label">Skipped</span>
                            </div>
                            <div className="organize-modal-stat">
                                <span className="organize-modal-stat-value">{cats.length}</span>
                                <span className="organize-modal-stat-label">Categories</span>
                            </div>
                        </div>

                        {cats.length > 0 && (
                            <div className="organize-modal-cats">
                                {cats.map(([cat, count]) => {
                                    const Icon = CATEGORY_ICONS[cat] ?? Package;
                                    return (
                                        <div className="organize-modal-cat-row" key={cat}>
                                            <Icon size={13} className="organize-modal-cat-icon" />
                                            <span className="organize-modal-cat-name">{cat}/</span>
                                            <span className="organize-modal-cat-count">{count}</span>
                                        </div>
                                    );
                                })}
                            </div>
                        )}

                        {result.moved === 0 && (
                            <p className="organize-modal-note">All files were already sorted. Nothing to move.</p>
                        )}
                    </div>
                )}

                {/* Error */}
                {phase === 'failed' && (
                    <div className="organize-modal-error">
                        <XCircle size={36} />
                        <p>{errorMsg || 'An unexpected error occurred.'}</p>
                    </div>
                )}

                {/* Footer */}
                <div className="scan-modal-footer">
                    {isDone ? (
                        <button className="btn btn-primary" onClick={handleClose}>
                            {phase === 'success' ? 'Done' : 'Close'}
                        </button>
                    ) : (
                        <span className="scan-modal-footer-hint">
                            Files are being moved locally — this only takes a moment.
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}
