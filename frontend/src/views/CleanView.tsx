import { Shield, Trash2, Sparkles } from 'lucide-react';
import type { DeleteSuggestion } from '../components/AppShell';

type CleanViewProps = {
    suggestions: DeleteSuggestion[];
    swipeIndex: number;
    onSwipe: (decision: 'keep' | 'delete') => void;
    onFindSuggestions: () => void;
    hasRoot: boolean;
    busy: string;
};

const formatBytes = (bytes: number) => {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = bytes;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }
    return `${value.toFixed(value > 10 ? 1 : 2)} ${units[unitIndex]}`;
};

export default function CleanView({
    suggestions,
    swipeIndex,
    onSwipe,
    onFindSuggestions,
    hasRoot,
    busy,
}: CleanViewProps) {
    const current = suggestions[swipeIndex] ?? null;
    const isDone = suggestions.length > 0 && swipeIndex >= suggestions.length;

    if (!hasRoot) {
        return (
            <div className="clean-container">
                <div className="clean-empty">
                    <Sparkles size={40} className="clean-empty-icon" />
                    <h3 className="clean-empty-title">No folder selected</h3>
                    <p className="clean-empty-desc">
                        Add a folder in the Scan view first, then come back to review cleanup suggestions.
                    </p>
                </div>
            </div>
        );
    }

    if (suggestions.length === 0) {
        return (
            <div className="clean-container">
                <div className="clean-empty">
                    <Sparkles size={40} className="clean-empty-icon" />
                    <h3 className="clean-empty-title">No suggestions yet</h3>
                    <p className="clean-empty-desc">
                        Find cleanup candidates in your indexed folders.
                    </p>
                    <button
                        className="btn btn-primary"
                        onClick={onFindSuggestions}
                        disabled={!!busy}
                    >
                        <Trash2 size={18} />
                        Find deletables
                    </button>
                </div>
            </div>
        );
    }

    if (isDone) {
        return (
            <div className="clean-container">
                <div className="clean-empty">
                    <Shield size={40} style={{ color: 'var(--success)' }} className="clean-empty-icon" />
                    <h3 className="clean-empty-title">All done!</h3>
                    <p className="clean-empty-desc">
                        You've reviewed all {suggestions.length} suggestions.
                    </p>
                    <button className="btn btn-secondary" onClick={onFindSuggestions} disabled={!!busy}>
                        Find more
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="clean-container">
            <div className="clean-progress-top">
                <div className="clean-progress-bar">
                    <div
                        className="clean-progress-fill"
                        style={{ width: `${((swipeIndex + 1) / suggestions.length) * 100}%` }}
                    />
                </div>
                <span className="clean-progress-text">
                    {swipeIndex + 1} / {suggestions.length}
                </span>
            </div>

            {current && (
                <div className="clean-card">
                    <span className="clean-card-badge">{current.type}</span>
                    <h2 className="clean-card-name">{current.name}</h2>
                    <p className="clean-card-reason">{current.reason}</p>
                    <div className="clean-card-meta">
                        <span>{formatBytes(current.size)}</span>
                        <span className="clean-card-meta-dot" />
                        <span>{current.ageDays}d old</span>
                        <span className="clean-card-meta-dot" />
                        <span>Score: {current.score}</span>
                    </div>
                    <div className="clean-card-path">{current.path}</div>
                </div>
            )}

            <div className="clean-actions">
                <button className="clean-btn clean-btn-keep" onClick={() => onSwipe('keep')}>
                    <Shield size={18} />
                    Keep
                </button>
                <button className="clean-btn clean-btn-quarantine" onClick={() => onSwipe('delete')}>
                    <Trash2 size={18} />
                    Quarantine
                </button>
            </div>

            <div className="clean-hint">Use ← to keep · → to quarantine</div>
        </div>
    );
}
