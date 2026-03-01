import { useState, useCallback, FormEvent } from 'react';
import { Search, FileText, FolderOpen, Loader2 } from 'lucide-react';

const DEPTH_LABELS: Record<string, string> = {
    deep: 'Full',
    preview: 'Preview',
    card: 'Card',
};

const DEPTH_COLORS: Record<string, string> = {
    deep: 'var(--accent)',
    preview: '#d69e2e',
    card: 'var(--text-faint)',
};

type MemoryViewProps = {
    hasRoot: boolean;
    onError: (message: string) => void;
};

export default function MemoryView({ hasRoot, onError }: MemoryViewProps) {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<SearchResult[]>([]);
    const [searching, setSearching] = useState(false);
    const [searchedQuery, setSearchedQuery] = useState<string | null>(null);

    const handleSearch = useCallback(async () => {
        const trimmed = query.trim();
        if (!trimmed) return;

        setSearching(true);
        setResults([]);
        setSearchedQuery(null);
        try {
            const data = await window.wispApi.searchMemory(trimmed, { k: 10 });
            setResults(data.results);
            setSearchedQuery(trimmed);
        } catch (e: any) {
            onError(`Search failed: ${e?.message ?? e}`);
        } finally {
            setSearching(false);
        }
    }, [query, onError]);

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        handleSearch();
    };

    const handleOpenFile = async (filePath: string) => {
        try {
            await window.wispApi.openFile(filePath);
        } catch (e: any) {
            onError(`Open failed: ${e?.message ?? e}`);
        }
    };

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
            <form className="memory-search-bar" onSubmit={handleSubmit}>
                <Search size={18} className="memory-search-icon" />
                <input
                    type="text"
                    className="memory-search-input"
                    placeholder="Search your files by meaning..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                />
                <button
                    type="submit"
                    className="btn btn-primary memory-search-btn"
                    disabled={searching}
                    aria-label="Search"
                >
                    {searching ? <Loader2 size={14} className="spin" /> : <Search size={14} />}
                    Search
                </button>
            </form>

            {searching && (
                <div className="memory-loading">
                    <Loader2 size={18} className="spin" />
                    Searching...
                </div>
            )}

            {searchedQuery !== null && !searching && results.length > 0 && (
                <div className="memory-results-header">
                    {results.length} result{results.length !== 1 ? 's' : ''} for &ldquo;{searchedQuery}&rdquo;
                </div>
            )}

            {searchedQuery !== null && !searching && results.length === 0 && (
                <div className="memory-no-results">
                    No results found for &ldquo;{searchedQuery}&rdquo;
                </div>
            )}

            {results.length > 0 && (
                <div className="memory-results">
                    {results.map((hit) => {
                        const fileName = hit.file_path.split('/').pop() || hit.file_id;
                        return (
                            <div className="memory-result-card" key={`${hit.file_id}-${hit.score}`}>
                                <FileText size={20} className="memory-result-icon" />
                                <div className="memory-result-body">
                                    <div className="memory-result-name">
                                        {fileName}
                                        <span
                                            className="tag"
                                            style={{
                                                fontSize: 10,
                                                marginLeft: 6,
                                                color: DEPTH_COLORS[hit.depth] || 'var(--text-faint)',
                                                borderColor: DEPTH_COLORS[hit.depth] || 'var(--border)',
                                            }}
                                        >
                                            {DEPTH_LABELS[hit.depth] || hit.depth}
                                        </span>
                                    </div>
                                    <div className="memory-result-score">
                                        Score: {hit.score.toFixed(2)}
                                    </div>
                                    <div className="memory-result-snippet">
                                        &ldquo;{hit.snippet}&rdquo;
                                    </div>
                                    <div className="memory-result-path">
                                        {hit.file_path}
                                    </div>
                                </div>
                                <button
                                    className="file-item-open"
                                    aria-label={`Open ${fileName}`}
                                    onClick={() => handleOpenFile(hit.file_path)}
                                >
                                    <FolderOpen size={13} />
                                    Open
                                </button>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
