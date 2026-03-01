import {
    ChevronDown,
    Folder,
    X,
    FileText,
    Check,
    Globe,
    File,
    Activity,
    Clock,
    HardDrive,
    Shield,
    Tag,
    Trash2,
    ExternalLink,
} from 'lucide-react';
import { useState } from 'react';
import type { PipelineStatus, ActivityEntry, TaggedFile, DeleteSuggestion } from './AppShell';

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
    onOpenFile: (path: string) => void;
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
    while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit += 1;
    }
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
    onOpenFile,
}: ContextPanelProps) {
    const [progressOpen, setProgressOpen] = useState(true);
    const [contextOpen, setContextOpen] = useState(true);
    const [filesOpen, setFilesOpen] = useState(true);
    const [activityOpen, setActivityOpen] = useState(true);
    const [systemOpen, setSystemOpen] = useState(true);

    const folderName = (p: string) => {
        const parts = p.split(/[\\/]/);
        return parts[parts.length - 1] || p;
    };

    const hasRealContent = rootFolders.length > 0;

    return (
        <aside className="context-panel">
            {/* ── Progress ── */}
            <div className="panel-card">
                <button
                    className="panel-card-header"
                    onClick={() => setProgressOpen((v) => !v)}
                >
                    <span className="panel-card-title">Progress</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                        {busy && <span className="panel-card-badge-busy">Active</span>}
                        <ChevronDown
                            size={13}
                            className={`panel-card-chevron ${!progressOpen ? 'collapsed' : ''}`}
                        />
                    </div>
                </button>
                {progressOpen && (
                    <div className="panel-card-body">
                        {/* Horizontal step circles */}
                        <div className="progress-steps">
                            {PIPELINE_STAGES.map(({ key }, i) => {
                                const count = pipeline[key];
                                const isDone = count > 0 && count >= pipeline.total;
                                const isActive = count > 0 && count < pipeline.total;
                                return (
                                    <span key={key} style={{ display: 'contents' }}>
                                        {i > 0 && (
                                            <span className={`progress-step-line ${isDone ? 'done' : ''}`} />
                                        )}
                                        <span
                                            className={`progress-step-circle ${isDone ? 'done' : isActive ? 'active' : ''}`}
                                        >
                                            {isDone && <Check size={12} />}
                                        </span>
                                    </span>
                                );
                            })}
                        </div>
                        {/* Stage labels */}
                        <div className="progress-stage-labels">
                            {PIPELINE_STAGES.map(({ key, label }) => (
                                <span key={key} className="progress-stage-label">{label}</span>
                            ))}
                        </div>
                        <div className="progress-label">
                            {busy
                                ? busy
                                : pipeline.total > 0
                                    ? `${pipeline.indexed} indexed · ${pipeline.embedded} embedded`
                                    : 'No active pipeline. Run Scan & Index to begin.'}
                        </div>

                        {/* Stats summary */}
                        {hasRealContent && (
                            <div className="progress-stats-row">
                                <div className="progress-stat">
                                    <span className="progress-stat-value">{fileCount.toLocaleString()}</span>
                                    <span className="progress-stat-label">Files</span>
                                </div>
                                <div className="progress-stat">
                                    <span className="progress-stat-value">{formatBytes(totalSize)}</span>
                                    <span className="progress-stat-label">Total size</span>
                                </div>
                                <div className="progress-stat">
                                    <span className="progress-stat-value">{taggedFiles.length}</span>
                                    <span className="progress-stat-label">Tagged</span>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* ── Context ── */}
            <div className="panel-card">
                <button
                    className="panel-card-header"
                    onClick={() => setContextOpen((v) => !v)}
                >
                    <span className="panel-card-title">Context</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                        {rootFolders.length > 0 && (
                            <span className="panel-card-count">{rootFolders.length}</span>
                        )}
                        <ChevronDown
                            size={13}
                            className={`panel-card-chevron ${!contextOpen ? 'collapsed' : ''}`}
                        />
                    </div>
                </button>
                {contextOpen && (
                    <div className="panel-card-body">
                        {/* Selected folders sub-section */}
                        <div className="panel-section-label">
                            <span>Selected folders</span>
                        </div>
                        {rootFolders.length > 0 ? (
                            rootFolders.map((folder) => (
                                <div className="folder-item" key={folder}>
                                    <Folder size={13} className="folder-item-icon" />
                                    <span className="folder-item-path" title={folder}>
                                        {folderName(folder)}
                                    </span>
                                    <button
                                        className="folder-item-remove"
                                        onClick={() => onRemoveFolder(folder)}
                                        title="Remove folder"
                                    >
                                        <X size={11} />
                                    </button>
                                </div>
                            ))
                        ) : (
                            <div className="panel-row" style={{ opacity: 0.5 }}>
                                <Folder size={13} className="panel-row-icon" />
                                <span className="panel-row-text">No folders selected</span>
                            </div>
                        )}

                        {/* Connectors sub-section */}
                        <div className="panel-section-label">Connectors</div>
                        <div className="panel-row">
                            <Globe size={13} className="panel-row-icon" />
                            <span className="panel-row-text">Local file system</span>
                            <span className="panel-row-badge-live">Active</span>
                        </div>

                        {/* Cleanup suggestions mini-summary */}
                        {suggestions.length > 0 && (
                            <>
                                <div className="panel-section-label">Cleanup</div>
                                <div className="panel-row">
                                    <Trash2 size={13} className="panel-row-icon" />
                                    <span className="panel-row-text">{suggestions.length} suggestions</span>
                                    <span className="panel-row-badge">{formatBytes(suggestions.reduce((s, i) => s + (i.size || 0), 0))}</span>
                                </div>
                            </>
                        )}

                        {/* Tagged files mini-summary */}
                        {taggedFiles.length > 0 && (
                            <>
                                <div className="panel-section-label">Tags</div>
                                <div className="panel-row">
                                    <Tag size={13} className="panel-row-icon" />
                                    <span className="panel-row-text">{taggedFiles.length} files tagged</span>
                                    <span className="panel-row-badge">
                                        {[...new Set(taggedFiles.flatMap(f => f.tags))].length} unique
                                    </span>
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>

            {/* ── Working files ── */}
            <div className="panel-card">
                <button
                    className="panel-card-header"
                    onClick={() => setFilesOpen((v) => !v)}
                >
                    <span className="panel-card-title">Working files</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                        {recentFiles.length > 0 && (
                            <span className="panel-card-count">{recentFiles.length}</span>
                        )}
                        <ChevronDown
                            size={13}
                            className={`panel-card-chevron ${!filesOpen ? 'collapsed' : ''}`}
                        />
                    </div>
                </button>
                {filesOpen && (
                    <div className="panel-card-body">
                        {recentFiles.length > 0
                            ? recentFiles.slice(0, 12).map((file) => (
                                <button
                                    className="panel-row panel-row-clickable"
                                    key={file.path}
                                    onClick={() => onOpenFile(file.path)}
                                    title={`Open ${file.path}`}
                                >
                                    <File size={13} className="panel-row-icon" />
                                    <span className="panel-row-text">
                                        {file.name}
                                    </span>
                                    <ExternalLink size={11} className="panel-row-open-icon" />
                                </button>
                            ))
                            : (
                                <div className="panel-empty-hint">
                                    <FileText size={14} />
                                    <span>Add a folder to see working files.</span>
                                </div>
                            )}
                    </div>
                )}
            </div>

            {/* ── Activity Log ── */}
            <div className="panel-card">
                <button
                    className="panel-card-header"
                    onClick={() => setActivityOpen((v) => !v)}
                >
                    <span className="panel-card-title">Activity</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                        {activityLog.length > 0 && (
                            <span className="panel-card-count">{activityLog.length}</span>
                        )}
                        <ChevronDown
                            size={13}
                            className={`panel-card-chevron ${!activityOpen ? 'collapsed' : ''}`}
                        />
                    </div>
                </button>
                {activityOpen && (
                    <div className="panel-card-body panel-activity-body">
                        {activityLog.length > 0 ? (
                            activityLog.slice(0, 15).map((entry) => (
                                <div className="activity-entry" key={entry.id}>
                                    <Activity size={12} className="activity-entry-icon" />
                                    <div className="activity-entry-content">
                                        <span className="activity-entry-action">{entry.action}</span>
                                        {entry.detail && (
                                            <span className="activity-entry-detail">{entry.detail}</span>
                                        )}
                                    </div>
                                    <span className="activity-entry-time">{timeAgo(entry.timestamp)}</span>
                                </div>
                            ))
                        ) : (
                            <div className="panel-empty-hint">
                                <Clock size={14} />
                                <span>Activity will appear here as you use Wisp.</span>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* ── System Info ── */}
            <div className="panel-card">
                <button
                    className="panel-card-header"
                    onClick={() => setSystemOpen((v) => !v)}
                >
                    <span className="panel-card-title">System</span>
                    <ChevronDown
                        size={13}
                        className={`panel-card-chevron ${!systemOpen ? 'collapsed' : ''}`}
                    />
                </button>
                {systemOpen && (
                    <div className="panel-card-body">
                        <div className="panel-row">
                            <HardDrive size={13} className="panel-row-icon" />
                            <span className="panel-row-text">Storage</span>
                            <span className="panel-row-badge">{hasRealContent ? formatBytes(totalSize) : 'Local'}</span>
                        </div>
                        <div className="panel-row">
                            <Shield size={13} className="panel-row-icon" />
                            <span className="panel-row-text">Privacy mode</span>
                            <span className="panel-row-badge-live">On</span>
                        </div>
                        <div className="panel-row">
                            <Globe size={13} className="panel-row-icon" />
                            <span className="panel-row-text">Processing</span>
                            <span className={`panel-row-badge${busy ? '-live' : ''}`}>{busy ? 'Running' : 'Idle'}</span>
                        </div>
                        <div className="panel-row">
                            <Folder size={13} className="panel-row-icon" />
                            <span className="panel-row-text">Folders</span>
                            <span className="panel-row-badge">{rootFolders.length}</span>
                        </div>
                    </div>
                )}
            </div>
        </aside>
    );
}
