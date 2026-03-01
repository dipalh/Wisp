import {
    ChevronDown,
    Folder,
    X,
    FileText,
    File,
    Activity,
    Clock,
    HardDrive,
    Tag,
    Trash2,
    ExternalLink,
    FolderSync,
    Package,
    Image,
    Music,
    Video,
    Archive,
    Code2,
    Search,
    Zap,
    Brain,
} from 'lucide-react';
import { useState } from 'react';
import type { PipelineStatus, ActivityEntry, TaggedFile, DeleteSuggestion, ViewId } from './AppShell';

type OrganizeResult = {
    moved: number;
    skipped: number;
    categories: Record<string, number>;
};

type ContextPanelProps = {
    pipeline: PipelineStatus;
    rootFolders: string[];
    recentFiles: { name: string; path: string }[];
    onRemoveFolder: (folder: string) => void;
    activityLog: ActivityEntry[];
    fileCount: number;
    totalSize: number;
    busy: string;
    taggedFiles: TaggedFile[];
    suggestions: DeleteSuggestion[];
    activeView: ViewId;
    organizeResult: OrganizeResult | null;
    onOpenFile: (path: string) => void;
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

const PIPELINE_STAGES = [
    { key: 'indexed' as const, label: 'Indexed' },
    { key: 'previewed' as const, label: 'Previewed' },
    { key: 'embedded' as const, label: 'Embedded' },
    { key: 'scored' as const, label: 'Scored' },
];

function formatBytes(bytes: number): string {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit++; }
    return `${value.toFixed(value > 10 ? 1 : 2)} ${units[unit]}`;
}

function timeAgo(timestamp: number): string {
    const diff = Date.now() - timestamp;
    if (diff < 5_000) return 'Just now';
    if (diff < 60_000) return `${Math.floor(diff / 1000)}s ago`;
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return `${Math.floor(diff / 86_400_000)}d ago`;
}

export default function ContextPanel({
    pipeline,
    rootFolders,
    recentFiles,
    onRemoveFolder,
    activityLog,
    fileCount,
    totalSize,
    busy,
    taggedFiles,
    suggestions,
    activeView,
    organizeResult,
    onOpenFile,
}: ContextPanelProps) {
    const [foldersOpen, setFoldersOpen] = useState(true);
    const [contextOpen, setContextOpen] = useState(true);
    const [activityOpen, setActivityOpen] = useState(true);
    const [filesOpen, setFilesOpen] = useState(false);

    const folderName = (p: string) => p.split(/[\\/]/).pop() || p;
    const hasRoot = rootFolders.length > 0;

    const renderViewContext = () => {
        switch (activeView) {
            case 'scan': {
                const hasScanned = pipeline.indexed > 0;
                return (
                    <div className="panel-card">
                        <button className="panel-card-header" onClick={() => setContextOpen(v => !v)}>
                            <span className="panel-card-title"><Search size={12} style={{ marginRight: 6, opacity: 0.6 }} />Scan status</span>
                            <ChevronDown size={13} className={`panel-card-chevron ${!contextOpen ? 'collapsed' : ''}`} />
                        </button>
                        {contextOpen && (
                            <div className="panel-card-body">
                                {hasScanned ? (
                                    <>
                                        <div className="ctx-stat-grid">
                                            <div className="ctx-stat"><span className="ctx-stat-value">{pipeline.indexed.toLocaleString()}</span><span className="ctx-stat-label">Indexed</span></div>
                                            <div className="ctx-stat"><span className="ctx-stat-value">{pipeline.embedded.toLocaleString()}</span><span className="ctx-stat-label">Embedded</span></div>
                                            <div className="ctx-stat"><span className="ctx-stat-value">{pipeline.scored.toLocaleString()}</span><span className="ctx-stat-label">Scored</span></div>
                                        </div>
                                        {pipeline.total > 0 && (
                                            <div className="ctx-progress-track">
                                                <div className="ctx-progress-fill" style={{ width: `${Math.min(100, Math.round((pipeline.indexed / pipeline.total) * 100))}%` }} />
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    <div className="panel-empty-hint"><Search size={14} /><span>Run Scan & Index to embed your files.</span></div>
                                )}
                            </div>
                        )}
                    </div>
                );
            }
            case 'organize': {
                return (
                    <div className="panel-card">
                        <button className="panel-card-header" onClick={() => setContextOpen(v => !v)}>
                            <span className="panel-card-title"><FolderSync size={12} style={{ marginRight: 6, opacity: 0.6 }} />Organize</span>
                            <ChevronDown size={13} className={`panel-card-chevron ${!contextOpen ? 'collapsed' : ''}`} />
                        </button>
                        {contextOpen && (
                            <div className="panel-card-body">
                                {organizeResult ? (
                                    <>
                                        <div className="ctx-stat-grid">
                                            <div className="ctx-stat"><span className="ctx-stat-value">{organizeResult.moved}</span><span className="ctx-stat-label">Moved</span></div>
                                            <div className="ctx-stat"><span className="ctx-stat-value">{organizeResult.skipped}</span><span className="ctx-stat-label">Skipped</span></div>
                                            <div className="ctx-stat"><span className="ctx-stat-value">{Object.keys(organizeResult.categories).length}</span><span className="ctx-stat-label">Categories</span></div>
                                        </div>
                                        <div className="ctx-cat-list">
                                            {Object.entries(organizeResult.categories)
                                                .sort((a, b) => b[1] - a[1])
                                                .map(([cat, count]) => {
                                                    const Icon = CATEGORY_ICONS[cat] ?? Package;
                                                    return (
                                                        <div className="ctx-cat-row" key={cat}>
                                                            <Icon size={12} className="ctx-cat-icon" />
                                                            <span className="ctx-cat-name">{cat}</span>
                                                            <span className="ctx-cat-count">{count}</span>
                                                        </div>
                                                    );
                                                })}
                                        </div>
                                    </>
                                ) : (
                                    <div className="panel-empty-hint"><FolderSync size={14} /><span>Press Organize Now to sort your files.</span></div>
                                )}
                            </div>
                        )}
                    </div>
                );
            }
            case 'clean': {
                return (
                    <div className="panel-card">
                        <button className="panel-card-header" onClick={() => setContextOpen(v => !v)}>
                            <span className="panel-card-title"><Trash2 size={12} style={{ marginRight: 6, opacity: 0.6 }} />Clean Up</span>
                            <ChevronDown size={13} className={`panel-card-chevron ${!contextOpen ? 'collapsed' : ''}`} />
                        </button>
                        {contextOpen && (
                            <div className="panel-card-body">
                                {suggestions.length > 0 ? (
                                    <div className="ctx-stat-grid">
                                        <div className="ctx-stat"><span className="ctx-stat-value">{suggestions.length}</span><span className="ctx-stat-label">Suggestions</span></div>
                                        <div className="ctx-stat"><span className="ctx-stat-value">{formatBytes(suggestions.reduce((s, i) => s + (i.size || 0), 0))}</span><span className="ctx-stat-label">Reclaimable</span></div>
                                    </div>
                                ) : (
                                    <div className="panel-empty-hint"><Trash2 size={14} /><span>Scan for cleanup suggestions first.</span></div>
                                )}
                            </div>
                        )}
                    </div>
                );
            }
            case 'memory': {
                return (
                    <div className="panel-card">
                        <button className="panel-card-header" onClick={() => setContextOpen(v => !v)}>
                            <span className="panel-card-title"><Brain size={12} style={{ marginRight: 6, opacity: 0.6 }} />Memory</span>
                            <ChevronDown size={13} className={`panel-card-chevron ${!contextOpen ? 'collapsed' : ''}`} />
                        </button>
                        {contextOpen && (
                            <div className="panel-card-body">
                                {taggedFiles.length > 0 ? (
                                    <div className="ctx-stat-grid">
                                        <div className="ctx-stat"><span className="ctx-stat-value">{taggedFiles.length}</span><span className="ctx-stat-label">Tagged</span></div>
                                        <div className="ctx-stat"><span className="ctx-stat-value">{[...new Set(taggedFiles.flatMap(f => f.tags))].length}</span><span className="ctx-stat-label">Unique tags</span></div>
                                    </div>
                                ) : (
                                    <div className="panel-empty-hint"><Tag size={14} /><span>Index your files to build memory.</span></div>
                                )}
                            </div>
                        )}
                    </div>
                );
            }
            case 'debloat': {
                return (
                    <div className="panel-card">
                        <button className="panel-card-header" onClick={() => setContextOpen(v => !v)}>
                            <span className="panel-card-title"><Zap size={12} style={{ marginRight: 6, opacity: 0.6 }} />Debloat</span>
                            <ChevronDown size={13} className={`panel-card-chevron ${!contextOpen ? 'collapsed' : ''}`} />
                        </button>
                        {contextOpen && (
                            <div className="panel-card-body">
                                <div className="panel-empty-hint"><Zap size={14} /><span>Windows-only. Select options and run.</span></div>
                            </div>
                        )}
                    </div>
                );
            }
            default:
                return null;
        }
    };

    return (
        <aside className="context-panel">

            {/* ── Summary strip ── */}
            <div className="panel-summary-strip">
                <div className="panel-summary-item">
                    <HardDrive size={12} />
                    <span>{hasRoot ? formatBytes(totalSize) : '--'}</span>
                </div>
                <div className="panel-summary-sep" />
                <div className="panel-summary-item">
                    <FileText size={12} />
                    <span>{hasRoot ? `${fileCount.toLocaleString()} files` : 'No folder'}</span>
                </div>
                {busy && (
                    <>
                        <div className="panel-summary-sep" />
                        <div className="panel-summary-item panel-summary-busy">
                            <span className="panel-summary-pulse" />
                            <span>{busy}</span>
                        </div>
                    </>
                )}
            </div>

            {/* ── Folders ── */}
            <div className="panel-card">
                <button className="panel-card-header" onClick={() => setFoldersOpen(v => !v)}>
                    <span className="panel-card-title">Folders</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                        {rootFolders.length > 0 && <span className="panel-card-count">{rootFolders.length}</span>}
                        <ChevronDown size={13} className={`panel-card-chevron ${!foldersOpen ? 'collapsed' : ''}`} />
                    </div>
                </button>
                {foldersOpen && (
                    <div className="panel-card-body">
                        {rootFolders.length > 0 ? (
                            rootFolders.map((folder) => (
                                <div className="folder-item" key={folder}>
                                    <Folder size={13} className="folder-item-icon" />
                                    <span className="folder-item-path" title={folder}>{folderName(folder)}</span>
                                    <button className="folder-item-remove" onClick={() => onRemoveFolder(folder)} title="Remove folder"><X size={11} /></button>
                                </div>
                            ))
                        ) : (
                            <div className="panel-empty-hint"><Folder size={14} /><span>No folders added yet.</span></div>
                        )}
                    </div>
                )}
            </div>

            {/* ── View-specific context ── */}
            {renderViewContext()}

            {/* ── Activity log ── */}
            <div className="panel-card">
                <button className="panel-card-header" onClick={() => setActivityOpen(v => !v)}>
                    <span className="panel-card-title">Activity</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                        {activityLog.length > 0 && <span className="panel-card-count">{activityLog.length}</span>}
                        <ChevronDown size={13} className={`panel-card-chevron ${!activityOpen ? 'collapsed' : ''}`} />
                    </div>
                </button>
                {activityOpen && (
                    <div className="panel-card-body panel-activity-body">
                        {activityLog.length > 0 ? (
                            activityLog.slice(0, 20).map((entry) => (
                                <div className="activity-entry" key={entry.id}>
                                    <Activity size={12} className="activity-entry-icon" />
                                    <div className="activity-entry-content">
                                        <span className="activity-entry-action">{entry.action}</span>
                                        {entry.detail && <span className="activity-entry-detail">{entry.detail}</span>}
                                    </div>
                                    <span className="activity-entry-time">{timeAgo(entry.timestamp)}</span>
                                </div>
                            ))
                        ) : (
                            <div className="panel-empty-hint"><Clock size={14} /><span>Activity will appear as you use Wisp.</span></div>
                        )}
                    </div>
                )}
            </div>

            {/* ── Recent files – only when meaningful ── */}
            {recentFiles.length > 0 && (
                <div className="panel-card">
                    <button className="panel-card-header" onClick={() => setFilesOpen(v => !v)}>
                        <span className="panel-card-title">Recent files</span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                            <span className="panel-card-count">{Math.min(recentFiles.length, 10)}</span>
                            <ChevronDown size={13} className={`panel-card-chevron ${!filesOpen ? 'collapsed' : ''}`} />
                        </div>
                    </button>
                    {filesOpen && (
                        <div className="panel-card-body">
                            {recentFiles.slice(0, 10).map((file) => (
                                <button className="panel-row panel-row-clickable" key={file.path} onClick={() => onOpenFile(file.path)} title={file.path}>
                                    <File size={13} className="panel-row-icon" />
                                    <span className="panel-row-text">{file.name}</span>
                                    <ExternalLink size={11} className="panel-row-open-icon" />
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            )}

        </aside>
    );
}
