import { useEffect, useMemo, useState } from 'react';
import {
    CheckCircle2,
    FileText,
    FolderSync,
    Image,
    Info,
    Loader2,
    Music,
    Package,
    Video,
    Archive,
    Code2,
    X,
    XCircle,
} from 'lucide-react';
import type { OrganizeResult } from './organizeOutcome';

type OrganizeStrategy = {
    proposal_id: string;
    name: string;
    rationale: string;
    reasons: string[];
    citations: string[];
    folder_tree: string[];
    mappings: Array<{
        original_path: string;
        suggested_path: string;
    }>;
};

type OrganizeProposalEnvelope = {
    recommendation: string;
    degraded: boolean;
    strategies: OrganizeStrategy[];
};

type OrganizeModalProps = {
    open: boolean;
    folder: string;
    onClose: () => void;
    onError: (msg: string) => void;
    onLoadProposals: () => Promise<OrganizeProposalEnvelope>;
    onApplyStrategy: (strategy: OrganizeStrategy) => Promise<OrganizeResult>;
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

type Phase = 'loading' | 'ready' | 'applying' | 'success' | 'error';

function fileNameFromPath(targetPath: string): string {
    return targetPath.split(/[\\/]/).pop() || targetPath;
}

export default function OrganizeModal({
    open,
    folder,
    onClose,
    onError,
    onLoadProposals,
    onApplyStrategy,
}: OrganizeModalProps) {
    const [phase, setPhase] = useState<Phase>('loading');
    const [proposals, setProposals] = useState<OrganizeProposalEnvelope | null>(null);
    const [selectedProposalId, setSelectedProposalId] = useState<string>('');
    const [result, setResult] = useState<OrganizeResult | null>(null);
    const [errorMsg, setErrorMsg] = useState('');

    useEffect(() => {
        if (!open || !folder) return;

        let cancelled = false;
        setPhase('loading');
        setProposals(null);
        setSelectedProposalId('');
        setResult(null);
        setErrorMsg('');

        (async () => {
            try {
                const next = await onLoadProposals();
                if (cancelled) return;
                setProposals(next);
                setSelectedProposalId(next.strategies[0]?.proposal_id ?? '');
                setPhase('ready');
            } catch (error: any) {
                if (cancelled) return;
                const message = error?.message ?? String(error);
                setErrorMsg(message);
                setPhase('error');
                onError(`Organize failed: ${message}`);
            }
        })();

        return () => {
            cancelled = true;
        };
    }, [folder, onError, onLoadProposals, open]);

    const selectedStrategy = useMemo(
        () => proposals?.strategies.find((strategy) => strategy.proposal_id === selectedProposalId) ?? null,
        [proposals, selectedProposalId],
    );

    const handleClose = () => {
        if (phase === 'applying') return;
        onClose();
    };

    const handleApply = async () => {
        if (!selectedStrategy) return;
        setPhase('applying');
        try {
            const next = await onApplyStrategy(selectedStrategy);
            setResult(next);
            setPhase('success');
        } catch (error: any) {
            const message = error?.message ?? String(error);
            setErrorMsg(message);
            setPhase('error');
            onError(`Organize failed: ${message}`);
        }
    };

    if (!open) return null;

    const folderName = fileNameFromPath(folder);
    const categories = Object.entries(result?.categories ?? {}).sort((a, b) => b[1] - a[1]);

    return (
        <div className="modal-overlay" onClick={phase === 'applying' ? undefined : handleClose}>
            <div className="modal-content scan-modal organize-modal" onClick={(event) => event.stopPropagation()}>
                <div className="modal-header">
                    <h3 className="modal-title">
                        {phase === 'loading' || phase === 'applying' ? <Loader2 size={20} className="spin" /> : null}
                        {phase === 'success' ? <CheckCircle2 size={20} className="modal-icon-success" /> : null}
                        {phase === 'error' ? <XCircle size={20} className="modal-icon-error" /> : null}
                        {phase === 'loading' && 'Loading organization strategies'}
                        {phase === 'ready' && 'Review Organization Plan'}
                        {phase === 'applying' && 'Applying Organization Plan'}
                        {phase === 'success' && (result?.partial ? 'Organization Applied With Warnings' : 'Organization Applied Successfully')}
                        {phase === 'error' && 'Organization Failed'}
                    </h3>
                    {phase !== 'applying' && (
                        <button className="modal-close" onClick={handleClose}>
                            <X size={16} />
                        </button>
                    )}
                </div>

                <div className="scan-modal-stats-row">
                    <div className="scan-modal-stat">
                        <FolderSync size={14} />
                        <span className="scan-modal-stat-value">{folderName}</span>
                        <span className="scan-modal-stat-label">Folder</span>
                    </div>
                    <div className="scan-modal-stat">
                        <Info size={14} />
                        <span className="scan-modal-stat-value">{proposals?.strategies.length ?? 0}</span>
                        <span className="scan-modal-stat-label">Strategies</span>
                    </div>
                    <div className="scan-modal-stat">
                        <Package size={14} />
                        <span className="scan-modal-stat-value">{selectedStrategy?.mappings.length ?? result?.moved ?? 0}</span>
                        <span className="scan-modal-stat-label">
                            {phase === 'success' ? (result?.partial ? 'Files moved' : 'Files moved') : 'Planned moves'}
                        </span>
                    </div>
                </div>

                {phase === 'loading' && (
                    <div className="scan-modal-message">
                        <span className="scan-modal-message-dot" />
                        Loading organization strategies from the backend planner...
                    </div>
                )}

                {phase === 'ready' && proposals && (
                    <div className="organize-modal-result">
                        <div className="organize-info-box" style={{ marginTop: 0 }}>
                            <Info size={14} />
                            <p>{proposals.recommendation || 'Review the available organization strategies below.'}</p>
                        </div>

                        {proposals.degraded && (
                            <div className="organize-info-box" style={{ marginTop: 12 }}>
                                <Info size={14} />
                                <p>Planner is running in degraded mode. Strategies are still reviewable, but they may be less contextual.</p>
                            </div>
                        )}

                        {proposals.strategies.length === 0 ? (
                            <div className="organize-modal-note">No organization strategies were generated for this folder.</div>
                        ) : (
                            <div className="organize-cats-grid" role="radiogroup" aria-label="Organization strategies">
                                {proposals.strategies.map((strategy) => {
                                    const checked = strategy.proposal_id === selectedProposalId;
                                    return (
                                        <label
                                            key={strategy.proposal_id}
                                            className="organize-cat-card"
                                            aria-label={strategy.name}
                                        >
                                            <input
                                                type="radio"
                                                name="organize-strategy"
                                                aria-label={strategy.name}
                                                checked={checked}
                                                onChange={() => setSelectedProposalId(strategy.proposal_id)}
                                            />
                                            <div className="organize-cat-card-info">
                                                <span className="organize-cat-card-name">{strategy.name}</span>
                                                <span className="organize-cat-card-count">{strategy.mappings.length} file move{strategy.mappings.length === 1 ? '' : 's'}</span>
                                                <p>{strategy.rationale}</p>
                                                <p>{strategy.reasons.join(' • ')}</p>
                                                <p>{strategy.citations.map(fileNameFromPath).join(', ')}</p>
                                            </div>
                                        </label>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                )}

                {phase === 'applying' && selectedStrategy && (
                    <div className="scan-modal-message">
                        <span className="scan-modal-message-dot" />
                        Applying “{selectedStrategy.name}” through the backend action engine...
                    </div>
                )}

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
                                <span className="organize-modal-stat-value">{result.failed}</span>
                                <span className="organize-modal-stat-label">Failed</span>
                            </div>
                        </div>

                        {result.partial ? (
                            <p>{result.moved} file moved and {result.failed} failed during apply.</p>
                        ) : (
                            <p>{result.moved} file moved with the selected reviewed strategy.</p>
                        )}

                        {result.warnings.length > 0 && (
                            <div className="organize-info-box" style={{ marginTop: 12 }}>
                                <Info size={14} />
                                <div>
                                    <p>Some actions could not be completed.</p>
                                    <ul>
                                        {result.warnings.map((warning) => (
                                            <li key={warning}>{warning}</li>
                                        ))}
                                    </ul>
                                </div>
                            </div>
                        )}

                        {categories.length > 0 && (
                            <div className="organize-modal-tree">
                                <p className="organize-modal-tree-title">Applied category summary</p>
                                <div className="organize-modal-tree-content">
                                    {categories.map(([category, count]) => {
                                        const Icon = CATEGORY_ICONS[category] ?? Package;
                                        return (
                                            <div className="organize-modal-tree-row" key={category}>
                                                <Icon size={13} className="organize-modal-tree-icon" />
                                                <span className="organize-modal-tree-name">{category}</span>
                                                <span className="organize-modal-tree-count">{count}</span>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {phase === 'error' && (
                    <div className="organize-modal-error">
                        <XCircle size={36} />
                        <p>{errorMsg || 'An unexpected error occurred.'}</p>
                    </div>
                )}

                <div className="scan-modal-footer">
                    {phase === 'ready' ? (
                        <>
                            <span className="scan-modal-footer-summary">
                                Review the recommended strategy before any files are moved.
                            </span>
                            <button
                                className="btn btn-primary"
                                onClick={handleApply}
                                disabled={!selectedStrategy}
                            >
                                Apply Selected Plan
                            </button>
                        </>
                    ) : (
                        <button className="btn btn-primary" onClick={handleClose} disabled={phase === 'applying'}>
                            {phase === 'success' ? 'Done' : 'Close'}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
