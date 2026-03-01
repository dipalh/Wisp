import {
    FolderPlus,
    RefreshCw,
    Wand2,
    Trash2,
    Tags,
    Search,
    BarChart3,
    ArrowRight,
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

    /* ──────────────────────────────────────────────
     * Welcome state: 3 stacked scaffold cards
     * instead of a lonely centered empty state.
     * ────────────────────────────────────────────── */
    if (!hasRoot) {
        return (
            <div className="welcome-container">
                {/* Card 1 — Primary action */}
                <div className="scaffold-card">
                    <div className="scaffold-card-hero">
                        <div className="scaffold-card-icon">
                            <FolderPlus size={20} />
                        </div>
                        <div className="scaffold-card-body">
                            <h2 className="scaffold-card-title">Choose folders to index</h2>
                            <p className="scaffold-card-desc">
                                Select one or more directories. Wisp will scan, organize,
                                tag, and help you clean up files — all locally on your machine.
                            </p>
                            <button className="btn btn-primary btn-lg" onClick={onAddFolder}>
                                <FolderPlus size={15} />
                                Choose folder
                            </button>
                        </div>
                    </div>
                </div>

                {/* Card 2 — "What happens next" steps */}
                <div className="scaffold-card">
                    <h3 className="scaffold-card-title">What happens next</h3>
                    <p className="scaffold-card-desc" style={{ marginBottom: 'var(--sp-3)' }}>
                        After selecting a folder, Wisp walks through three stages:
                    </p>
                    <div className="step-list">
                        <div className="step-item">
                            <span className="step-number">1</span>
                            <div className="step-body">
                                <div className="step-title">Index</div>
                                <div className="step-desc">Scans every file — names, sizes, dates, structure</div>
                            </div>
                        </div>
                        <div className="step-item">
                            <span className="step-number">2</span>
                            <div className="step-body">
                                <div className="step-title">Analyze</div>
                                <div className="step-desc">Tags files by content, finds duplicates, scores importance</div>
                            </div>
                        </div>
                        <div className="step-item">
                            <span className="step-number">3</span>
                            <div className="step-body">
                                <div className="step-title">Review</div>
                                <div className="step-desc">Suggests files to delete, helps you organize what remains</div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Card 3 — Recent activity placeholder */}
                <div className="scaffold-card">
                    <h3 className="scaffold-card-title">Recent activity</h3>
                    <table className="scaffold-table">
                        <thead>
                            <tr>
                                <th>Action</th>
                                <th>Files</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td style={{ color: 'var(--text-disabled)' }}>No activity yet</td>
                                <td>—</td>
                                <td>—</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        );
    }

    /* ──────────────────────────────────────────────
     * Active state: action grid + pipeline + tags
     * ────────────────────────────────────────────── */
    return (
        <div>
            <div className="scan-grid">
                <button className="scan-action-card" onClick={onAddFolder} disabled={!!busy}>
                    <div className="scan-action-icon"><FolderPlus size={16} /></div>
                    <span className="scan-action-title">Add folder</span>
                    <span className="scan-action-desc">Index another directory</span>
                </button>

                <button className="scan-action-card" onClick={() => onScan(rootFolders[0])} disabled={!!busy}>
                    <div className="scan-action-icon"><RefreshCw size={16} /></div>
                    <span className="scan-action-title">Rescan</span>
                    <span className="scan-action-desc">Refresh the file index</span>
                </button>

                <button className="scan-action-card" onClick={onOrganize} disabled={!!busy}>
                    <div className="scan-action-icon"><Wand2 size={16} /></div>
                    <span className="scan-action-title">Organize</span>
                    <span className="scan-action-desc">Sort files by category</span>
                </button>

                <button className="scan-action-card" onClick={onSuggestDelete} disabled={!!busy}>
                    <div className="scan-action-icon"><Trash2 size={16} /></div>
                    <span className="scan-action-title">Find deletables</span>
                    <span className="scan-action-desc">Identify cleanup candidates</span>
                </button>

                <button className="scan-action-card" onClick={() => onTagFiles('local')} disabled={!!busy}>
                    <div className="scan-action-icon"><Tags size={16} /></div>
                    <span className="scan-action-title">Generate tags</span>
                    <span className="scan-action-desc">Auto-tag locally</span>
                </button>

                <button className="scan-action-card" onClick={() => onTagFiles('api')} disabled={!!busy}>
                    <div className="scan-action-icon"><Tags size={16} /></div>
                    <span className="scan-action-title">AI tags</span>
                    <span className="scan-action-desc">Richer tags via API</span>
                </button>
            </div>

            {/* Pipeline stats */}
            {pipeline.indexed > 0 && (
                <div className="scan-progress-section">
                    <h3 className="scan-file-list-title">Pipeline</h3>
                    <div className="card" style={{ display: 'flex', gap: 'var(--sp-4)' }}>
                        {[
                            { label: 'Indexed', value: pipeline.indexed },
                            { label: 'Previewed', value: pipeline.previewed },
                            { label: 'Embedded', value: pipeline.embedded },
                            { label: 'Scored', value: pipeline.scored },
                        ].map((stage) => (
                            <div key={stage.label} style={{ flex: 1 }}>
                                <div style={{ fontSize: 'var(--text-muted)', color: 'var(--text-tertiary)', marginBottom: '2px' }}>
                                    {stage.label}
                                </div>
                                <div style={{ fontSize: 'var(--text-title)', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                                    {stage.value > 0 ? stage.value.toLocaleString() : '—'}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Tagged files */}
            {taggedFiles.length > 0 && (
                <div className="scan-file-list">
                    <div className="scan-file-list-header">
                        <span className="scan-file-list-title">
                            Tagged files ({taggedFiles.length})
                        </span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
                        {taggedFiles.slice(0, 12).map((file) => (
                            <div className="file-item" key={file.path} title={file.path}>
                                <div className="file-item-info">
                                    <div className="file-item-name">{file.name}</div>
                                    <div style={{ display: 'flex', gap: 'var(--sp-1)', flexWrap: 'wrap', marginTop: '2px' }}>
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
                    </div>
                </div>
            )}
        </div>
    );
}
