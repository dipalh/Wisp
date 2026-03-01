import { ChevronDown, Folder, X, FileText, Check } from 'lucide-react';
import { useState } from 'react';
import type { PipelineStatus } from './AppShell';

type ContextPanelProps = {
    pipeline: PipelineStatus;
    rootFolders: string[];
    recentFiles: { name: string; path: string }[];
    onRemoveFolder: (folder: string) => void;
};

const PIPELINE_STAGES = [
    { key: 'indexed' as const, label: 'Indexed' },
    { key: 'previewed' as const, label: 'Previewed' },
    { key: 'embedded' as const, label: 'Embedded' },
    { key: 'scored' as const, label: 'Scored' },
];

export default function ContextPanel({
    pipeline,
    rootFolders,
    recentFiles,
    onRemoveFolder,
}: ContextPanelProps) {
    const [progressOpen, setProgressOpen] = useState(true);
    const [contextOpen, setContextOpen] = useState(true);
    const [filesOpen, setFilesOpen] = useState(true);

    const folderName = (p: string) => {
        const parts = p.split(/[\\/]/);
        return parts[parts.length - 1] || p;
    };

    return (
        <aside className="context-panel">
            {/* Progress — Cowork-style circles */}
            <div className="panel-card">
                <button
                    className="panel-card-header"
                    onClick={() => setProgressOpen((v) => !v)}
                >
                    <span className="panel-card-title">Progress</span>
                    <ChevronDown
                        size={14}
                        style={{
                            color: 'var(--text-tertiary)',
                            transform: progressOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                            transition: 'transform var(--ease-fast)',
                        }}
                    />
                </button>
                {progressOpen && (
                    <div className="panel-card-body">
                        {/* Horizontal circles (like Cowork's progress circles) */}
                        <div className="progress-steps">
                            {PIPELINE_STAGES.map(({ key, label }, i) => {
                                const count = pipeline[key];
                                const isDone = count > 0 && count >= pipeline.total;
                                const isActive = count > 0 && count < pipeline.total;

                                return (
                                    <span key={key} style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                                        {i > 0 && (
                                            <span className={`progress-step-line ${isDone ? 'done' : ''}`} />
                                        )}
                                        <span
                                            className={`progress-step-circle ${isDone ? 'done' : isActive ? 'active' : ''}`}
                                            title={`${label}: ${count > 0 ? count : '—'}`}
                                        >
                                            {isDone && <Check size={14} />}
                                        </span>
                                    </span>
                                );
                            })}
                        </div>
                        <div className="progress-label">
                            {pipeline.total > 0
                                ? `${pipeline.indexed} indexed · ${pipeline.embedded} embedded`
                                : 'Steps will show as the task unfolds.'}
                        </div>
                    </div>
                )}
            </div>

            {/* Context — selected folders */}
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
                            size={14}
                            style={{
                                color: 'var(--text-tertiary)',
                                transform: contextOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                                transition: 'transform var(--ease-fast)',
                            }}
                        />
                    </div>
                </button>
                {contextOpen && (
                    <div className="panel-card-body">
                        {rootFolders.length === 0 ? (
                            <div style={{ fontSize: 'var(--text-muted)', color: 'var(--text-tertiary)', padding: 'var(--sp-1) 0' }}>
                                No folders selected
                            </div>
                        ) : (
                            <>
                                <div style={{ fontSize: 'var(--text-muted)', color: 'var(--text-tertiary)', marginBottom: 'var(--sp-2)' }}>
                                    Selected folders
                                </div>
                                {rootFolders.map((folder) => (
                                    <div className="folder-item" key={folder}>
                                        <Folder size={14} className="folder-item-icon" />
                                        <span className="folder-item-path" title={folder}>
                                            {folderName(folder)}
                                        </span>
                                        <button
                                            className="folder-item-remove"
                                            onClick={() => onRemoveFolder(folder)}
                                            title="Remove folder"
                                        >
                                            <X size={12} />
                                        </button>
                                    </div>
                                ))}
                            </>
                        )}
                    </div>
                )}
            </div>

            {/* Working Files */}
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
                            size={14}
                            style={{
                                color: 'var(--text-tertiary)',
                                transform: filesOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                                transition: 'transform var(--ease-fast)',
                            }}
                        />
                    </div>
                </button>
                {filesOpen && (
                    <div className="panel-card-body">
                        {recentFiles.length === 0 ? (
                            <div style={{ fontSize: 'var(--text-muted)', color: 'var(--text-tertiary)', padding: 'var(--sp-1) 0' }}>
                                No files yet
                            </div>
                        ) : (
                            recentFiles.map((file) => (
                                <div className="file-item" key={file.path} style={{ padding: 'var(--sp-1) 0' }}>
                                    <FileText size={14} className="file-item-icon" />
                                    <div className="file-item-info">
                                        <div className="file-item-name" title={file.path}>
                                            {file.name}
                                        </div>
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                )}
            </div>
        </aside>
    );
}
