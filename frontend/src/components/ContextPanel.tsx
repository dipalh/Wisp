import {
    ChevronDown,
    Folder,
    X,
    FileText,
    Check,
    Globe,
    File,
    Loader2,
    CheckCircle2,
    XCircle,
} from 'lucide-react';
import { useState } from 'react';
import type { PipelineStatus, JobState } from './AppShell';

type ContextPanelProps = {
    pipeline: PipelineStatus;
    rootFolders: string[];
    recentFiles: { name: string; path: string }[];
    onRemoveFolder: (folder: string) => void;
    job?: JobState;
};

const PIPELINE_STAGES = [
    { key: 'indexed' as const, label: 'Indexed' },
    { key: 'previewed' as const, label: 'Previewed' },
    { key: 'embedded' as const, label: 'Embedded' },
    { key: 'scored' as const, label: 'Scored' },
];

/* Placeholder items when panels are empty — gives "content scaffolding" */
const PLACEHOLDER_FILES = [
    { name: 'project-notes.md', status: 'indexed' },
    { name: 'meeting-summary.pdf', status: 'pending' },
    { name: 'budget-2024.xlsx', status: 'tagged' },
];

export default function ContextPanel({
    pipeline,
    rootFolders,
    recentFiles,
    onRemoveFolder,
    job,
}: ContextPanelProps) {
    const [progressOpen, setProgressOpen] = useState(true);
    const [contextOpen, setContextOpen] = useState(true);
    const [filesOpen, setFilesOpen] = useState(true);

    const folderName = (p: string) => {
        const parts = p.split(/[\\/]/);
        return parts[parts.length - 1] || p;
    };

    const hasRealContent = rootFolders.length > 0;
    const displayFiles = recentFiles.length > 0 ? recentFiles : [];
    const showPlaceholders = !hasRealContent;

    return (
        <aside className="context-panel">
            {/* ── Progress ── */}
            <div className="panel-card">
                <button
                    className="panel-card-header"
                    onClick={() => setProgressOpen((v) => !v)}
                >
                    <span className="panel-card-title">Progress</span>
                    <ChevronDown
                        size={13}
                        className={`panel-card-chevron ${!progressOpen ? 'collapsed' : ''}`}
                    />
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

                        {/* Live job progress bar */}
                        {job ? (() => {
                            const pct = job.progress_total > 0
                                ? Math.round((job.progress_current / job.progress_total) * 100)
                                : 0;
                            const isRunning = job.status === 'queued' || job.status === 'running';
                            const isSuccess = job.status === 'success';
                            const isFailed = job.status === 'failed';
                            return (
                                <div className="panel-job-progress">
                                    <div className="panel-job-header">
                                        {isRunning && <Loader2 size={12} className="spin" />}
                                        {isSuccess && <CheckCircle2 size={12} style={{ color: 'var(--accent)' }} />}
                                        {isFailed && <XCircle size={12} style={{ color: '#e53e3e' }} />}
                                        <span className="panel-job-status">
                                            {isRunning && 'Indexing\u2026'}
                                            {isSuccess && 'Scan complete'}
                                            {isFailed && 'Scan failed'}
                                        </span>
                                        {job.progress_total > 0 && (
                                            <span className="panel-job-count">
                                                {job.progress_current}/{job.progress_total}
                                            </span>
                                        )}
                                    </div>
                                    <div className="job-progress-track">
                                        <div
                                            className={`job-progress-fill${isSuccess ? ' done' : isFailed ? ' error' : ''}`}
                                            style={{ width: `${pct}%` }}
                                        />
                                    </div>
                                    {job.progress_message && (
                                        <div className="panel-job-message">{job.progress_message}</div>
                                    )}
                                </div>
                            );
                        })() : (
                            <div className="progress-label">
                                {pipeline.total > 0
                                    ? `${pipeline.indexed} indexed · ${pipeline.embedded} embedded`
                                    : 'Steps will show as the task unfolds.'}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* ── Artifacts ── */}
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
                        </div>
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
                        {(displayFiles.length > 0 || showPlaceholders) && (
                            <span className="panel-card-count">
                                {displayFiles.length || PLACEHOLDER_FILES.length}
                            </span>
                        )}
                        <ChevronDown
                            size={13}
                            className={`panel-card-chevron ${!filesOpen ? 'collapsed' : ''}`}
                        />
                    </div>
                </button>
                {filesOpen && (
                    <div className="panel-card-body">
                        {displayFiles.length > 0
                            ? displayFiles.slice(0, 10).map((file) => (
                                <div className="panel-row" key={file.path}>
                                    <File size={13} className="panel-row-icon" />
                                    <span className="panel-row-text" title={file.path}>
                                        {file.name}
                                    </span>
                                </div>
                            ))
                            : PLACEHOLDER_FILES.map((f) => (
                                <div className="panel-row" key={f.name} style={{ opacity: 0.45 }}>
                                    <FileText size={13} className="panel-row-icon" />
                                    <span className="panel-row-text">{f.name}</span>
                                    <span className="chip">{f.status}</span>
                                </div>
                            ))}
                    </div>
                )}
            </div>
        </aside>
    );
}
