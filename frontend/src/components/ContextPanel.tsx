import { ChevronDown, Folder, X, FileText } from 'lucide-react';
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
            {/* Progress section */}
            <div className="context-section">
                <button
                    className="context-section-header"
                    onClick={() => setProgressOpen((v) => !v)}
                >
                    <span className="context-section-title">Progress</span>
                    <ChevronDown
                        size={14}
                        style={{
                            color: 'var(--text-tertiary)',
                            transform: progressOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                            transition: 'transform 150ms ease',
                        }}
                    />
                </button>
                {progressOpen && (
                    <div className="context-section-body">
                        <div className="progress-steps">
                            {PIPELINE_STAGES.map(({ key, label }) => {
                                const count = pipeline[key];
                                const isDone = count > 0 && count >= pipeline.total;
                                const isActive = count > 0 && count < pipeline.total;

                                return (
                                    <div className="progress-step" key={key}>
                                        <div
                                            className={`progress-step-dot ${isDone ? 'done' : isActive ? 'active' : ''
                                                }`}
                                        />
                                        <span className="progress-step-label">{label}</span>
                                        <span className="progress-step-count">
                                            {count > 0 ? count.toLocaleString() : '—'}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}
            </div>

            {/* Context section */}
            <div className="context-section">
                <button
                    className="context-section-header"
                    onClick={() => setContextOpen((v) => !v)}
                >
                    <span className="context-section-title">Context</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {rootFolders.length > 0 && (
                            <span className="context-section-count">{rootFolders.length}</span>
                        )}
                        <ChevronDown
                            size={14}
                            style={{
                                color: 'var(--text-tertiary)',
                                transform: contextOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                                transition: 'transform 150ms ease',
                            }}
                        />
                    </div>
                </button>
                {contextOpen && (
                    <div className="context-section-body">
                        {rootFolders.length === 0 ? (
                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)', padding: 'var(--sp-1) 0' }}>
                                No folders selected
                            </div>
                        ) : (
                            rootFolders.map((folder) => (
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
                            ))
                        )}
                    </div>
                )}
            </div>

            {/* Working Files section */}
            <div className="context-section">
                <button
                    className="context-section-header"
                    onClick={() => setFilesOpen((v) => !v)}
                >
                    <span className="context-section-title">Working Files</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {recentFiles.length > 0 && (
                            <span className="context-section-count">{recentFiles.length}</span>
                        )}
                        <ChevronDown
                            size={14}
                            style={{
                                color: 'var(--text-tertiary)',
                                transform: filesOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                                transition: 'transform 150ms ease',
                            }}
                        />
                    </div>
                </button>
                {filesOpen && (
                    <div className="context-section-body">
                        {recentFiles.length === 0 ? (
                            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)', padding: 'var(--sp-1) 0' }}>
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
