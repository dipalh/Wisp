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

    /* ──────────────────────────────────────────────
     * Empty state: document-flow, top-down.
     * Primary action block, then a content area below.
     * ────────────────────────────────────────────── */
    if (!hasRoot) {
        return (
            <div className="doc-flow">
                {/* Primary action section */}
                <section className="doc-section">
                    <div className="doc-action-row">
                        <div className="doc-action-content">
                            <h2 className="doc-heading">Choose a folder to get started</h2>
                            <p className="doc-body">
                                Wisp will index, tag, and help you clean up your files — all locally.
                            </p>
                        </div>
                        <button className="btn btn-primary" onClick={onAddFolder}>
                            <FolderPlus size={14} />
                            Choose folder
                        </button>
                    </div>
                </section>

                {/* Content area — what you'll be able to do */}
                <div className="doc-divider" />

                <section className="doc-section">
                    <div className="doc-steps">
                        <div className="doc-step">
                            <span className="doc-step-num">1</span>
                            <div>
                                <span className="doc-step-title">Index</span>
                                <span className="doc-step-desc"> — scans files, names, structure</span>
                            </div>
                        </div>
                        <div className="doc-step">
                            <span className="doc-step-num">2</span>
                            <div>
                                <span className="doc-step-title">Analyze</span>
                                <span className="doc-step-desc"> — tags, duplicates, scoring</span>
                            </div>
                        </div>
                        <div className="doc-step">
                            <span className="doc-step-num">3</span>
                            <div>
                                <span className="doc-step-title">Review</span>
                                <span className="doc-step-desc"> — cleanup suggestions</span>
                            </div>
                        </div>
                    </div>
                </section>
            </div>
        );
    }

    /* ──────────────────────────────────────────────
     * Active state: compact action grid + content
     * ────────────────────────────────────────────── */
    return (
        <div className="doc-flow">
            <div className="scan-grid">
                <button className="scan-action-card" onClick={onAddFolder} disabled={!!busy}>
                    <div className="scan-action-icon"><FolderPlus size={15} /></div>
                    <span className="scan-action-title">Add folder</span>
                    <span className="scan-action-desc">Index another directory</span>
                </button>

                <button className="scan-action-card" onClick={() => onScan(rootFolders[0])} disabled={!!busy}>
                    <div className="scan-action-icon"><RefreshCw size={15} /></div>
                    <span className="scan-action-title">Rescan</span>
                    <span className="scan-action-desc">Refresh file index</span>
                </button>

                <button className="scan-action-card" onClick={onOrganize} disabled={!!busy}>
                    <div className="scan-action-icon"><Wand2 size={15} /></div>
                    <span className="scan-action-title">Organize</span>
                    <span className="scan-action-desc">Sort by category</span>
                </button>

                <button className="scan-action-card" onClick={onSuggestDelete} disabled={!!busy}>
                    <div className="scan-action-icon"><Trash2 size={15} /></div>
                    <span className="scan-action-title">Find deletables</span>
                    <span className="scan-action-desc">Cleanup candidates</span>
                </button>

                <button className="scan-action-card" onClick={() => onTagFiles('local')} disabled={!!busy}>
                    <div className="scan-action-icon"><Tags size={15} /></div>
                    <span className="scan-action-title">Generate tags</span>
                    <span className="scan-action-desc">Auto-tag locally</span>
                </button>

                <button className="scan-action-card" onClick={() => onTagFiles('api')} disabled={!!busy}>
                    <div className="scan-action-icon"><Tags size={15} /></div>
                    <span className="scan-action-title">AI tags</span>
                    <span className="scan-action-desc">Richer tags via API</span>
                </button>
            </div>

            {/* Pipeline stats — inline, not a card */}
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
                    <div className="scan-file-list-title">
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
