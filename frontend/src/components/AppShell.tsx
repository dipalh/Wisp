import { useState } from 'react';
import Sidebar from './Sidebar';
import ContextPanel from './ContextPanel';
import ScanView from '../views/ScanView';
import CleanView from '../views/CleanView';
import VisualizeView from '../views/VisualizeView';
import MemoryView from '../views/MemoryView';
import AssistantView from '../views/AssistantView';

export type ViewId = 'scan' | 'clean' | 'visualize' | 'memory' | 'assistant';

export type TreeNode = {
    name: string;
    path: string;
    type: 'file' | 'folder';
    size: number;
    lastModified?: number;
    children?: TreeNode[];
};

export type TaggedFile = {
    path: string;
    name: string;
    tags: string[];
};

export type DeleteSuggestion = {
    type: string;
    path: string;
    name: string;
    size: number;
    ageDays: number;
    reason: string;
    score: number;
};

export type PipelineStatus = {
    indexed: number;
    previewed: number;
    embedded: number;
    scored: number;
    total: number;
};

const VIEW_TITLES: Record<ViewId, string> = {
    scan: 'Scan',
    clean: 'Clean',
    visualize: 'Visualize',
    memory: 'Memory',
    assistant: 'Assistant',
};

const VIEW_SUBTITLES: Record<ViewId, string> = {
    scan: 'Index and analyze your files',
    clean: 'Review and clean up clutter',
    visualize: 'Explore storage usage',
    memory: 'Search files by meaning',
    assistant: 'AI-powered file assistant',
};

export default function AppShell() {
    const [activeView, setActiveView] = useState<ViewId>('scan');

    // Shared state
    const [rootFolders, setRootFolders] = useState<string[]>([]);
    const [tree, setTree] = useState<TreeNode | null>(null);
    const [focusPath, setFocusPath] = useState('');
    const [busy, setBusy] = useState('');
    const [statusText, setStatusText] = useState('Ready');

    // Pipeline
    const [pipeline, setPipeline] = useState<PipelineStatus>({
        indexed: 0, previewed: 0, embedded: 0, scored: 0, total: 0,
    });

    // Tags and suggestions
    const [taggedFiles, setTaggedFiles] = useState<TaggedFile[]>([]);
    const [suggestions, setSuggestions] = useState<DeleteSuggestion[]>([]);
    const [swipeIndex, setSwipeIndex] = useState(0);

    // Recent files for context panel
    const [recentFiles, setRecentFiles] = useState<{ name: string; path: string }[]>([]);

    // --- Handlers ---
    const addFolder = async () => {
        const picked = await window.wispApi.pickFolder();
        if (!picked || rootFolders.includes(picked)) return;
        setRootFolders((prev) => [...prev, picked]);
        setBusy('Scanning...');
        setStatusText('Scanning folder...');

        const scanned = await window.wispApi.scanFolder(picked);
        setTree(scanned);
        setFocusPath(scanned?.path ?? '');

        // Count files for pipeline
        let count = 0;
        const countFiles = (node: TreeNode) => {
            if (node.type === 'file') count++;
            node.children?.forEach(countFiles);
        };
        if (scanned) countFiles(scanned);

        setPipeline((prev) => ({ ...prev, indexed: count, total: count }));

        // Track recent files
        const recent: { name: string; path: string }[] = [];
        const collect = (node: TreeNode) => {
            if (node.type === 'file' && recent.length < 10) {
                recent.push({ name: node.name, path: node.path });
            }
            node.children?.forEach(collect);
        };
        if (scanned) collect(scanned);
        setRecentFiles(recent);

        setBusy('');
        setStatusText(`Indexed ${count} files`);
    };

    const removeFolder = (folder: string) => {
        setRootFolders((prev) => prev.filter((f) => f !== folder));
        if (rootFolders.length <= 1) {
            setTree(null);
            setFocusPath('');
            setPipeline({ indexed: 0, previewed: 0, embedded: 0, scored: 0, total: 0 });
            setRecentFiles([]);
        }
    };

    const handleScan = async (folder: string) => {
        setBusy('Scanning...');
        setStatusText('Rescanning...');
        const scanned = await window.wispApi.scanFolder(folder);
        setTree(scanned);
        if (scanned && !focusPath) setFocusPath(scanned.path);

        let count = 0;
        const cnt = (node: TreeNode) => { if (node.type === 'file') count++; node.children?.forEach(cnt); };
        if (scanned) cnt(scanned);
        setPipeline((prev) => ({ ...prev, indexed: count, total: count }));

        setBusy('');
        setStatusText(`Indexed ${count} files`);
    };

    const handleSuggestDelete = async () => {
        if (rootFolders.length === 0) return;
        setBusy('Finding suggestions...');
        const result = await window.wispApi.suggestDelete(rootFolders[0]);
        setSuggestions(result);
        setSwipeIndex(0);
        setBusy('');
        setStatusText(`Found ${result.length} cleanup suggestions`);
        setActiveView('clean');
    };

    const handleSwipe = async (decision: 'keep' | 'delete') => {
        const current = suggestions[swipeIndex];
        if (!current) return;
        if (decision === 'delete') {
            await window.wispApi.trashPath(current.path);
        }
        const next = swipeIndex + 1;
        setSwipeIndex(next);
        if (next >= suggestions.length) {
            setStatusText('Cleanup review complete');
            if (rootFolders[0]) handleScan(rootFolders[0]);
        }
    };

    const handleOrganize = async () => {
        if (rootFolders.length === 0) return;
        setBusy('Organizing...');
        const result = await window.wispApi.organizeFolder(rootFolders[0]);
        if (rootFolders[0]) await handleScan(rootFolders[0]);
        setBusy('');
        setStatusText(`Moved ${result.moved} files`);
    };

    const handleTagFiles = async (provider: 'local' | 'api') => {
        if (rootFolders.length === 0) return;
        setBusy('Generating tags...');
        const result = await window.wispApi.tagFiles({
            rootPath: rootFolders[0],
            provider,
        });
        setTaggedFiles(result);
        setBusy('');
        setStatusText(`Tagged ${result.length} files`);
    };

    // --- Render active view ---
    const renderView = () => {
        switch (activeView) {
            case 'scan':
                return (
                    <ScanView
                        rootFolders={rootFolders}
                        onAddFolder={addFolder}
                        onScan={handleScan}
                        onOrganize={handleOrganize}
                        onSuggestDelete={handleSuggestDelete}
                        onTagFiles={handleTagFiles}
                        pipeline={pipeline}
                        taggedFiles={taggedFiles}
                        busy={busy}
                    />
                );
            case 'clean':
                return (
                    <CleanView
                        suggestions={suggestions}
                        swipeIndex={swipeIndex}
                        onSwipe={handleSwipe}
                        onFindSuggestions={handleSuggestDelete}
                        hasRoot={rootFolders.length > 0}
                        busy={busy}
                    />
                );
            case 'visualize':
                return (
                    <VisualizeView
                        tree={tree}
                        focusPath={focusPath}
                        onNavigate={setFocusPath}
                        rootFolders={rootFolders}
                        onAddFolder={addFolder}
                    />
                );
            case 'memory':
                return (
                    <MemoryView
                        taggedFiles={taggedFiles}
                        hasRoot={rootFolders.length > 0}
                        onTagFiles={() => handleTagFiles('local')}
                        busy={busy}
                    />
                );
            case 'assistant':
                return <AssistantView />;
            default:
                return null;
        }
    };

    return (
        <div className="app-shell">
            <Sidebar activeView={activeView} onViewChange={setActiveView} />

            <div className="main-area">
                <div className="main-header">
                    <span className="main-header-title">{VIEW_TITLES[activeView]}</span>
                    <span className="main-header-subtitle">{VIEW_SUBTITLES[activeView]}</span>
                </div>

                <div className="main-content">
                    <div className="main-content-inner">
                        {renderView()}
                    </div>
                </div>

                <div className="main-status">
                    <span className={`status-dot ${busy ? 'busy' : pipeline.indexed > 0 ? '' : 'idle'}`} />
                    <span>{busy || statusText}</span>
                </div>
            </div>

            <ContextPanel
                pipeline={pipeline}
                rootFolders={rootFolders}
                recentFiles={recentFiles}
                onRemoveFolder={removeFolder}
            />
        </div>
    );
}
