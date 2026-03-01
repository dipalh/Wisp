import { useState, useMemo } from 'react';
import { Search, FileText, Tag } from 'lucide-react';
import type { TaggedFile } from '../components/AppShell';

type MemoryViewProps = {
    taggedFiles: TaggedFile[];
    hasRoot: boolean;
    onTagFiles: () => void;
    busy: string;
};

export default function MemoryView({
    taggedFiles,
    hasRoot,
    onTagFiles,
    busy,
}: MemoryViewProps) {
    const [query, setQuery] = useState('');

    const results = useMemo(() => {
        if (!query.trim()) return taggedFiles.slice(0, 30);
        const q = query.toLowerCase();
        return taggedFiles
            .filter(
                (f) =>
                    f.name.toLowerCase().includes(q) ||
                    f.tags.some((t) => t.includes(q))
            )
            .slice(0, 60);
    }, [taggedFiles, query]);

    if (!hasRoot) {
        return (
            <div className="empty-state">
                <Search size={40} className="empty-state-icon" />
                <h3 className="empty-state-title">No files indexed</h3>
                <p className="empty-state-desc">
                    Add and scan a folder first to search your files.
                </p>
            </div>
        );
    }

    return (
        <div className="memory-container">
            <div className="memory-search-bar">
                <Search size={18} className="memory-search-icon" />
                <input
                    type="text"
                    className="memory-search-input"
                    placeholder="Search files by name or tag..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                />
            </div>

            {taggedFiles.length === 0 && (
                <div className="empty-state">
                    <Tag size={36} className="empty-state-icon" />
                    <h3 className="empty-state-title">No tags generated yet</h3>
                    <p className="empty-state-desc">
                        Generate tags to search your files by meaning, not just filenames.
                    </p>
                    <button className="btn btn-primary" onClick={onTagFiles} disabled={!!busy} style={{ marginTop: 'var(--sp-4)' }}>
                        <Tag size={16} />
                        Generate tags
                    </button>
                </div>
            )}

            {taggedFiles.length > 0 && (
                <div className="memory-results">
                    {results.length === 0 && query.trim() && (
                        <div className="empty-state">
                            <p className="empty-state-desc">No files match "{query}"</p>
                        </div>
                    )}
                    {results.map((file) => (
                        <div className="memory-result-card" key={file.path} title={file.path}>
                            <FileText size={20} className="memory-result-icon" />
                            <div className="memory-result-body">
                                <div className="memory-result-name">{file.name}</div>
                                <div className="memory-result-tags">
                                    {file.tags.slice(0, 6).map((tag) => (
                                        <span className="tag" key={tag}>{tag}</span>
                                    ))}
                                    {file.tags.length > 6 && (
                                        <span className="tag" style={{ color: 'var(--text-disabled)' }}>
                                            +{file.tags.length - 6}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                    {results.length > 0 && (
                        <div style={{ fontSize: 'var(--text-muted)', color: 'var(--text-tertiary)', textAlign: 'center', padding: 'var(--sp-3)' }}>
                            Showing {results.length} of {taggedFiles.length} files
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
