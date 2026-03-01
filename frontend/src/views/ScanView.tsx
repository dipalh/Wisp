import {
    FolderPlus,
    RefreshCw,
    Wand2,
    Trash2,
    Tags,
} from 'lucide-react';
import type { PipelineStatus, TaggedFile } from '../components/AppShell';

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

    if (!hasRoot) {
        return (
            <div className="welcome-container">
                <div className="welcome-content">
                    <div className="welcome-icon">
                        <FolderPlus size={48} />
                    </div>
                    <h1 className="welcome-title">Welcome to Wisp</h1>
                    <p className="welcome-subtitle">
                        Choose a folder to start scanning, organizing, and cleaning your files.
                    </p>
                    <button className="btn btn-primary btn-lg" onClick={onAddFolder}>
                        <FolderPlus size={18} />
                        Choose folder
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div>
            {/* Action grid */}
            <div className="scan-grid">
                <button
                    className="scan-action-card"
                    onClick={onAddFolder}
                    disabled={!!busy}
                >
                    <div className="scan-action-icon">
                        <FolderPlus size={18} />
                    </div>
                    <span className="scan-action-title">Add folder</span>
                    <span className="scan-action-desc">Index another directory</span>
                </button>

                <button
                    className="scan-action-card"
                    onClick={() => onScan(rootFolders[0])}
                    disabled={!!busy}
                >
                    <div className="scan-action-icon">
                        <RefreshCw size={18} />
                    </div>
                    <span className="scan-action-title">Rescan</span>
                    <span className="scan-action-desc">Refresh the file index</span>
                </button>

                <button
                    className="scan-action-card"
                    onClick={onOrganize}
                    disabled={!!busy}
                >
                    <div className="scan-action-icon">
                        <Wand2 size={18} />
                    </div>
                    <span className="scan-action-title">Organize</span>
                    <span className="scan-action-desc">Sort files by category</span>
                </button>

                <button
                    className="scan-action-card"
                    onClick={onSuggestDelete}
                    disabled={!!busy}
                >
                    <div className="scan-action-icon">
                        <Trash2 size={18} />
                    </div>
                    <span className="scan-action-title">Find deletables</span>
                    <span className="scan-action-desc">Identify cleanup candidates</span>
                </button>

                <button
                    className="scan-action-card"
                    onClick={() => onTagFiles('local')}
                    disabled={!!busy}
                >
                    <div className="scan-action-icon">
                        <Tags size={18} />
                    </div>
                    <span className="scan-action-title">Generate tags</span>
                    <span className="scan-action-desc">Auto-tag files locally</span>
                </button>

                <button
                    className="scan-action-card"
                    onClick={() => onTagFiles('api')}
                    disabled={!!busy}
                >
                    <div className="scan-action-icon">
                        <Tags size={18} />
                    </div>
                    <span className="scan-action-title">AI tags</span>
                    <span className="scan-action-desc">Use AI for richer tags</span>
                </button>
            </div>

            {/* Pipeline status */}
            {pipeline.indexed > 0 && (
                <div className="scan-progress-section">
                    <h3 style={{ fontSize: 'var(--text-md)', fontWeight: 600, marginBottom: 'var(--sp-3)' }}>
                        Pipeline
                    </h3>
                    <div className="card" style={{ display: 'flex', gap: 'var(--sp-6)' }}>
                        {[
                            { label: 'Indexed', value: pipeline.indexed },
                            { label: 'Previewed', value: pipeline.previewed },
                            { label: 'Embedded', value: pipeline.embedded },
                            { label: 'Scored', value: pipeline.scored },
                        ].map((stage) => (
                            <div key={stage.label} style={{ flex: 1 }}>
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginBottom: 'var(--sp-1)' }}>
                                    {stage.label}
                                </div>
                                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                                    {stage.value > 0 ? stage.value.toLocaleString() : '—'}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Tagged files summary */}
            {taggedFiles.length > 0 && (
                <div className="scan-file-list" style={{ marginTop: 'var(--sp-6)' }}>
                    <div className="scan-file-list-header">
                        <span className="scan-file-list-title">
                            Tagged files ({taggedFiles.length})
                        </span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
                        {taggedFiles.slice(0, 12).map((file) => (
                            <div className="file-item" key={file.path} title={file.path}>
                                <div className="file-item-info">
                                    <div className="file-item-name">{file.name}</div>
                                    <div style={{ display: 'flex', gap: 'var(--sp-1)', flexWrap: 'wrap', marginTop: 'var(--sp-1)' }}>
                                        {file.tags.slice(0, 4).map((tag) => (
                                            <span className="tag" key={tag}>{tag}</span>
                                        ))}
                                        {file.tags.length > 4 && (
                                            <span className="tag" style={{ color: 'var(--text-disabled)' }}>
                                                +{file.tags.length - 4}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                        {taggedFiles.length > 12 && (
                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)', padding: 'var(--sp-2)' }}>
                                and {taggedFiles.length - 12} more...
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
