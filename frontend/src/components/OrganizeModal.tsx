import { useEffect, useRef, useState, useCallback } from 'react';
import {
    X, Loader2, CheckCircle2, XCircle, FolderSync, FileText, Image,
    Music, Video, Archive, Code2, Package, Zap, FolderTree, ChevronRight,
} from 'lucide-react';

/* ── Types ───────────────────────────────────────────────────────────────── */

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
    onOrganize: () => Promise<OrganizeResult>;
};

type Phase = 'running' | 'success' | 'failed';

/* ── Stage definitions for the simulated pipeline ────────────────────────── */

type Stage = {
    label: string;
    logs: string[];
    duration: number;
};

const STAGES: Stage[] = [
    {
        label: 'Scanning directory',
        logs: [
            'Reading file manifest from target folder...',
            'Enumerating top-level entries...',
            'Filtering hidden files and existing subdirectories...',
        ],
        duration: 1200,
    },
    {
        label: 'Analyzing file types',
        logs: [
            'Inspecting file extensions and MIME types...',
            'Classifying documents, images, audio, video...',
            'Identifying archives and source code files...',
            'Building file-type frequency map...',
        ],
        duration: 1400,
    },
    {
        label: 'Planning folder structure',
        logs: [
            'Generating optimal category folders...',
            'Mapping each file to its target directory...',
            'Resolving naming conflicts...',
            'Validating proposed file moves...',
        ],
        duration: 1600,
    },
    {
        label: 'Executing file moves',
        logs: [
            'Creating category subdirectories...',
            'Moving documents to Documents/...',
            'Moving images to Images/...',
            'Moving audio files to Audio/...',
            'Moving video files to Videos/...',
            'Moving archives to Archives/...',
            'Moving source code to Code/...',
            'Moving remaining files to Others/...',
        ],
        duration: 2000,
    },
    {
        label: 'Verifying results',
        logs: [
            'Confirming all files reached their destinations...',
            'Checking for orphaned entries...',
            'Generating summary report...',
        ],
        duration: 800,
    },
];

const TOTAL_STAGE_WEIGHT = STAGES.length;

const CATEGORY_ICONS: Record<string, typeof FileText> = {
    Documents: FileText,
    Images: Image,
    Audio: Music,
    Videos: Video,
    Archives: Archive,
    Code: Code2,
    Others: Package,
};

/* ── Component ───────────────────────────────────────────────────────────── */

export default function OrganizeModal({ open, folder, onClose, onError, onOrganize }: OrganizeModalProps) {
    const [phase, setPhase] = useState<Phase>('running');
    const [result, setResult] = useState<OrganizeResult | null>(null);
    const [elapsed, setElapsed] = useState(0);
    const [errorMsg, setErrorMsg] = useState('');
    const [started, setStarted] = useState(false);

    /* Simulated pipeline state */
    const [stageIdx, setStageIdx] = useState(0);
    const [logs, setLogs] = useState<string[]>([]);
    const [pct, setPct] = useState(0);
    const [currentMessage, setCurrentMessage] = useState('Preparing...');

    const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const stageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const logTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pctTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const logsEndRef = useRef<HTMLDivElement>(null);
    const realDoneRef = useRef(false);
    const realResultRef = useRef<OrganizeResult | null>(null);
    const realErrorRef = useRef<string | null>(null);

    const cleanup = useCallback(() => {
        if (elapsedRef.current) { clearInterval(elapsedRef.current); elapsedRef.current = null; }
        if (stageTimerRef.current) { clearTimeout(stageTimerRef.current); stageTimerRef.current = null; }
        if (logTimerRef.current) { clearInterval(logTimerRef.current); logTimerRef.current = null; }
        if (pctTimerRef.current) { clearInterval(pctTimerRef.current); pctTimerRef.current = null; }
    }, []);

    useEffect(() => () => cleanup(), [cleanup]);

    /* Auto-scroll logs */
    useEffect(() => {
        logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    /* ── Kick off on open ────────────────────────────────────────────────── */
    useEffect(() => {
        if (!open || started || !folder) return;
        setStarted(true);
        setPhase('running');
        setResult(null);
        setElapsed(0);
        setStageIdx(0);
        setLogs(['Initializing organize pipeline...']);
        setPct(0);
        setCurrentMessage('Preparing...');
        setErrorMsg('');
        realDoneRef.current = false;
        realResultRef.current = null;
        realErrorRef.current = null;

        /* Elapsed timer */
        const t0 = Date.now();
        elapsedRef.current = setInterval(() => {
            setElapsed(Math.round((Date.now() - t0) / 1000));
        }, 1000);

        /* Start the real work in the background */
        (async () => {
            try {
                const res = await onOrganize();
                realResultRef.current = res;
            } catch (e: any) {
                realErrorRef.current = e?.message ?? String(e);
            }
            realDoneRef.current = true;
        })();

        /* Start simulated pipeline */
        runStage(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open, started, folder]);

    /* ── Run one stage ───────────────────────────────────────────────────── */
    function runStage(idx: number) {
        if (idx >= STAGES.length) {
            waitForReal();
            return;
        }

        const stage = STAGES[idx];
        setStageIdx(idx);
        setCurrentMessage(stage.label + '...');
        setLogs(prev => [...prev, `[Stage ${idx + 1}/${STAGES.length}] ${stage.label}`]);

        /* Drip-feed log lines */
        let logIdx = 0;
        const logInterval = Math.max(250, stage.duration / (stage.logs.length + 1));
        if (logTimerRef.current) clearInterval(logTimerRef.current);
        logTimerRef.current = setInterval(() => {
            if (logIdx < stage.logs.length) {
                setLogs(prev => {
                    const next = [...prev, `  ${stage.logs[logIdx]}`];
                    return next.length > 60 ? next.slice(-60) : next;
                });
                logIdx++;
            }
        }, logInterval);

        /* Animate progress within this stage */
        const basePct = Math.round((idx / TOTAL_STAGE_WEIGHT) * 100);
        const nextPct = Math.round(((idx + 1) / TOTAL_STAGE_WEIGHT) * 100);
        const pctRange = nextPct - basePct;
        const pctSteps = 8;
        let pctStep = 0;
        const pctInterval = stage.duration / pctSteps;
        if (pctTimerRef.current) clearInterval(pctTimerRef.current);
        pctTimerRef.current = setInterval(() => {
            pctStep++;
            const eased = Math.min(pctStep / pctSteps, 1);
            setPct(Math.round(basePct + pctRange * eased));
            if (pctStep >= pctSteps && pctTimerRef.current) {
                clearInterval(pctTimerRef.current);
                pctTimerRef.current = null;
            }
        }, pctInterval);

        /* Move to next stage after duration */
        stageTimerRef.current = setTimeout(() => {
            if (logTimerRef.current) { clearInterval(logTimerRef.current); logTimerRef.current = null; }
            if (pctTimerRef.current) { clearInterval(pctTimerRef.current); pctTimerRef.current = null; }
            setPct(nextPct);
            runStage(idx + 1);
        }, stage.duration);
    }

    /* ── Wait for real backend result ────────────────────────────────────── */
    function waitForReal() {
        setCurrentMessage('Finalizing...');
        const check = () => {
            if (realDoneRef.current) {
                cleanup();
                if (realErrorRef.current) {
                    setErrorMsg(realErrorRef.current);
                    setPhase('failed');
                    onError(`Organize failed: ${realErrorRef.current}`);
                } else {
                    setPct(100);
                    setLogs(prev => [...prev, '', 'Organization complete.']);
                    setResult(realResultRef.current);
                    setPhase('success');
                }
            } else {
                stageTimerRef.current = setTimeout(check, 200);
            }
        };
        check();
    }

    /* ── Close handler ───────────────────────────────────────────────────── */
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
    const cats = result ? Object.entries(result.categories).sort((a, b) => b[1] - a[1]) : [];

    return (
        <div className="modal-overlay" onClick={isDone ? handleClose : undefined}>
            <div className="modal-content scan-modal organize-modal" onClick={e => e.stopPropagation()}>

                {/* Header */}
                <div className="modal-header">
                    <h3 className="modal-title">
                        {phase === 'success' && <CheckCircle2 size={20} className="modal-icon-success" />}
                        {phase === 'failed' && <XCircle size={20} className="modal-icon-error" />}
                        {phase === 'running' && <Loader2 size={20} className="spin" />}
                        {phase === 'success' ? 'Organize Complete'
                            : phase === 'failed' ? 'Organize Failed'
                            : 'Organizing Files...'}
                    </h3>
                    {isDone && (
                        <button className="modal-close" onClick={handleClose}>
                            <X size={16} />
                        </button>
                    )}
                </div>

                {/* Stats row (mirrors ScanModal) */}
                <div className="scan-modal-stats-row">
                    <div className="scan-modal-stat">
                        <FolderSync size={14} />
                        <span className="scan-modal-stat-value">{folderName}</span>
                        <span className="scan-modal-stat-label">Folder</span>
                    </div>
                    <div className="scan-modal-stat">
                        <Zap size={14} />
                        <span className="scan-modal-stat-value">{formatElapsed(elapsed)}</span>
                        <span className="scan-modal-stat-label">Elapsed</span>
                    </div>
                    <div className="scan-modal-stat">
                        <FolderTree size={14} />
                        <span className="scan-modal-stat-value">
                            {isDone ? (result ? `${result.moved + result.skipped}` : '0') : `Stage ${stageIdx + 1}/${STAGES.length}`}
                        </span>
                        <span className="scan-modal-stat-label">{isDone ? 'Files' : 'Progress'}</span>
                    </div>
                </div>

                {/* Progress bar (determinate) */}
                <div className="scan-modal-progress">
                    <div className="scan-modal-bar-track">
                        <div
                            className={`scan-modal-bar-fill ${phase === 'failed' ? 'error' : ''} ${!isDone && pct > 0 ? 'animating' : ''}`}
                            style={{ width: `${pct}%` }}
                        />
                    </div>
                    <div className="scan-modal-stats">
                        <span>{pct}% complete</span>
                        <span>{STAGES[Math.min(stageIdx, STAGES.length - 1)]?.label ?? 'Done'}</span>
                    </div>
                </div>

                {/* Current operation message */}
                <div className="scan-modal-message">
                    <span className={`scan-modal-message-dot${isDone ? ' done' : ''}`} />
                    {isDone ? (phase === 'success' ? 'All files organized successfully' : 'Organization failed') : currentMessage}
                </div>

                {/* Log output (same style as ScanModal) */}
                <div className="scan-modal-logs">
                    {logs.map((line, i) => (
                        <div key={i} className={`scan-modal-log-line ${i === logs.length - 1 ? 'latest' : ''}`}>
                            <span className="scan-modal-log-ts">{String(i + 1).padStart(3, ' ')}</span>
                            {line}
                        </div>
                    ))}
                    <div ref={logsEndRef} />
                </div>

                {/* Success — result panel with folder tree + stats */}
                {phase === 'success' && result && (
                    <div className="organize-modal-result">
                        {/* Stats */}
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

                        {/* Resulting folder tree */}
                        {cats.length > 0 && (
                            <div className="organize-modal-tree">
                                <p className="organize-modal-tree-title">Resulting folder structure</p>
                                <div className="organize-modal-tree-content">
                                    {cats.map(([cat, count]) => {
                                        const Icon = CATEGORY_ICONS[cat] ?? Package;
                                        return (
                                            <div className="organize-modal-tree-row" key={cat}>
                                                <ChevronRight size={11} className="organize-modal-tree-chevron" />
                                                <Icon size={13} className="organize-modal-tree-icon" />
                                                <span className="organize-modal-tree-name">{cat}/</span>
                                                <span className="organize-modal-tree-count">{count} file{count !== 1 ? 's' : ''}</span>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {result.moved === 0 && (
                            <p className="organize-modal-note">All files were already sorted — nothing to move.</p>
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
                        <>
                            {phase === 'success' && (
                                <span className="scan-modal-footer-summary">
                                    {result && result.moved > 0
                                        ? `Organized ${result.moved} files into ${cats.length} folders in ${formatElapsed(elapsed)}`
                                        : `Completed in ${formatElapsed(elapsed)}`}
                                </span>
                            )}
                            <button className="btn btn-primary" onClick={handleClose}>
                                {phase === 'success' ? 'Done' : 'Close'}
                            </button>
                        </>
                    ) : (
                        <span className="scan-modal-footer-hint">
                            AI agent is analyzing and organizing your files...
                        </span>
                    )}
                </div>
            </div>
        </div>
    );
}
