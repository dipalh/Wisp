import { useCallback, useRef, useState } from 'react';
import Sidebar from './Sidebar';
import ContextPanel from './ContextPanel';
import ErrorBanner from './ErrorBanner';
import ScanModal from './ScanModal';
import OrganizeModal from './OrganizeModal';
import ScanView from '../views/ScanView';
import CleanView from '../views/CleanView';
import VisualizeView from '../views/VisualizeView';
import MemoryView from '../views/MemoryView';
import ExtractView from '../views/ExtractView';
import DebloatView from '../views/DebloatView';
import OrganizeView from '../views/OrganizeView';
import PrivacyView from '../views/PrivacyView';
import LegalView from '../views/LegalView';

export type ViewId = 'scan' | 'clean' | 'visualize' | 'organize' | 'memory' | 'extract' | 'debloat' | 'privacy' | 'legal';

export type ActivityEntry = {
    id: string;
    action: string;
    detail?: string;
    timestamp: number;
};

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
    scan: 'Scan & Index',
    clean: 'Clean Up',
    visualize: 'Visualize',
    organize: 'Organize',
    memory: 'Memory',
    extract: 'Extract',
    debloat: 'Debloat',
    privacy: 'Privacy & Safety',
    legal: 'Legal',
};

const VIEW_SUBTITLES: Record<ViewId, string> = {
    scan: 'Index and analyze your files',
    clean: 'Review and clean up clutter',
    visualize: 'Explore storage usage',
    organize: 'Auto-sort files into folders',
    memory: 'AI-powered file memory',
    extract: 'Pull text from images and PDFs',
    debloat: 'Optimize and debloat',
    privacy: 'How we protect your data',
    legal: 'Terms, licenses, and policies',
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

    // Global error banner
    const [error, setError] = useState<string | null>(null);
    const onError = useCallback((msg: string) => setError(msg), []);
    const dismissError = useCallback(() => setError(null), []);

    // Organize result
    const [organizeResult, setOrganizeResult] = useState<{ moved: number; skipped: number; categories: Record<string, number> } | null>(null);
    const [organizeModalOpen, setOrganizeModalOpen] = useState(false);

    // Scan modal
    const [scanModalOpen, setScanModalOpen] = useState(false);
    const [lastCompletedJobId, setLastCompletedJobId] = useState<string | null>(null);

    // Activity log
    const [activityLog, setActivityLog] = useState<ActivityEntry[]>([]);
    const activityIdRef = useRef(0);
    const logActivity = useCallback((action: string, detail?: string) => {
        const entry: ActivityEntry = {
            id: String(++activityIdRef.current),
            action,
            detail,
            timestamp: Date.now(),
        };
        setActivityLog((prev) => [entry, ...prev].slice(0, 50));
    }, []);

    // File count from tree
    const fileCount = (() => {
        if (!tree) return 0;
        let count = 0;
        const walk = (n: TreeNode) => { if (n.type === 'file') count++; n.children?.forEach(walk); };
        walk(tree);
        return count;
    })();

    // Total size from tree
    const totalSize = (() => {
        if (!tree) return 0;
        let size = 0;
        const walk = (n: TreeNode) => { if (n.type === 'file') size += n.size || 0; n.children?.forEach(walk); };
        walk(tree);
        return size;
    })();

    const handleScanModalComplete = useCallback((jobId: string) => {
        setLastCompletedJobId(jobId);
        logActivity('Scan job completed', `Job ${jobId.slice(0, 8)}…`);
        // After scan completes, refresh tree if we have folders
        if (rootFolders[0]) {
            (async () => {
                try {
                    const scanned = await window.wispApi.scanFolder(rootFolders[0]);
                    setTree(scanned);
                    if (scanned && !focusPath) setFocusPath(scanned.path);
                    let count = 0;
                    const cnt = (node: TreeNode) => { if (node.type === 'file') count++; node.children?.forEach(cnt); };
                    if (scanned) cnt(scanned);
                    setStatusText(`Scan complete: ${count} files`);
                    setPipeline(prev => ({ ...prev, indexed: count, total: count }));
                } catch { /* ignore */ }
            })();
        }
    }, [rootFolders, focusPath, logActivity]);

    // --- Handlers ---
    const addFolder = async () => {
        try {
            const picked = await window.wispApi.pickFolder();
            if (!picked || rootFolders.includes(picked)) return;
            setRootFolders((prev) => [...prev, picked]);
            setBusy('Scanning...');
            setStatusText('Scanning folder...');

            const scanned = await window.wispApi.scanFolder(picked);
            setTree(scanned);
            setFocusPath(scanned?.path ?? '');

            let count = 0;
            const recent: { name: string; path: string }[] = [];
            const walk = (node: TreeNode) => {
                if (node.type === 'file') {
                    count++;
                    if (recent.length < 10) recent.push({ name: node.name, path: node.path });
                }
                node.children?.forEach(walk);
            };
            if (scanned) walk(scanned);
            setRecentFiles(recent);

            setBusy('');
            setStatusText(`Found ${count} files`);
            logActivity('Folder added', folderName(picked));
        } catch (e: any) {
            setBusy('');
            onError(`Add folder failed: ${e?.message ?? e}`);
        }
    };

    const folderName = (p: string) => {
        const parts = p.split(/[\\/]/);
        return parts[parts.length - 1] || p;
    };

    const removeFolder = (folder: string) => {
        logActivity('Folder removed', folderName(folder));
        setRootFolders((prev) => prev.filter((f) => f !== folder));
        if (rootFolders.length <= 1) {
            setTree(null);
            setFocusPath('');
            setPipeline({ indexed: 0, previewed: 0, embedded: 0, scored: 0, total: 0 });
            setRecentFiles([]);
        }
    };

    const handleScan = async (folder: string) => {
        try {
            setBusy('Scanning...');
            setStatusText('Rescanning...');
            const scanned = await window.wispApi.scanFolder(folder);
            setTree(scanned);
            if (scanned && !focusPath) setFocusPath(scanned.path);

            let count = 0;
            const cnt = (node: TreeNode) => { if (node.type === 'file') count++; node.children?.forEach(cnt); };
            if (scanned) cnt(scanned);

            setBusy('');
            setStatusText(`Found ${count} files`);
        } catch (e: any) {
            setBusy('');
            onError(`Rescan failed: ${e?.message ?? e}`);
        }
    };

    const handleSuggestDelete = async () => {
        if (rootFolders.length === 0) return;
        try {
            setBusy('Finding suggestions...');
            const result = await window.wispApi.suggestDelete(rootFolders[0]);
            setSuggestions(result);
            setSwipeIndex(0);
            setBusy('');
            setStatusText(`Found ${result.length} cleanup suggestions`);
            logActivity('Cleanup suggestions found', `${result.length} items`);
            setActiveView('clean');
        } catch (e: any) {
            setBusy('');
            onError(`Suggest delete failed: ${e?.message ?? e}`);
        }
    };

    const handleSwipe = async (decision: 'keep' | 'delete') => {
        const current = suggestions[swipeIndex];
        if (!current) return;
        try {
            if (decision === 'delete') {
                await window.wispApi.trashPath(current.path);
                logActivity('File trashed', current.name);
            } else {
                logActivity('File kept', current.name);
            }
            const next = swipeIndex + 1;
            setSwipeIndex(next);
            if (next >= suggestions.length) {
                setStatusText('Cleanup review complete');
                if (rootFolders[0]) handleScan(rootFolders[0]);
            }
        } catch (e: any) {
            onError(`Trash failed: ${e?.message ?? e}`);
        }
    };

    /** Called by OrganizeModal — runs the actual work and returns the result. */
    const runOrganize = async () => {
        if (rootFolders.length === 0) throw new Error('No folder selected');
        const result = await window.wispApi.organizeFolder(rootFolders[0]);
        if (result.error) throw new Error(result.error);
        const res = { moved: result.moved, skipped: result.skipped, categories: result.categories ?? {} };
        setOrganizeResult(res);
        // background post-processing
        setTimeout(async () => {
            try {
                if (rootFolders[0]) await handleScan(rootFolders[0]);
            } catch { /* ignore */ }
            const msg = res.moved > 0
                ? `Organized ${res.moved} files into category folders`
                : 'No files needed organizing';
            setStatusText(msg);
            logActivity('Folder organized', `${res.moved} moved, ${res.skipped} skipped`);
        }, 0);
        return res;
    };

    const handleTagFiles = async (provider: 'local' | 'api') => {
        if (rootFolders.length === 0) return;
        try {
            setBusy('Generating tags...');
            const result = await window.wispApi.tagFiles({
                rootPath: rootFolders[0],
                provider,
            });
            setTaggedFiles(result);
            setBusy('');
            setStatusText(`Tagged ${result.length} files`);
            logActivity('Files tagged', `${result.length} files via ${provider}`);
        } catch (e: any) {
            setBusy('');
            onError(`Tag generation failed: ${e?.message ?? e}`);
        }
    };

    // --- Render active view ---
    const renderView = () => {
        switch (activeView) {
            case 'scan':
                return (
                    <ScanView
                        rootFolders={rootFolders}
                        onAddFolder={addFolder}
                        onOrganize={() => setOrganizeModalOpen(true)}
                        onSuggestDelete={handleSuggestDelete}
                        onTagFiles={handleTagFiles}
                        taggedFiles={taggedFiles}
                        busy={busy}
                        onError={onError}
                        onOpenScanModal={() => setScanModalOpen(true)}
                        completedJobId={lastCompletedJobId}
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
                        hasRoot={rootFolders.length > 0}
                        onError={onError}
                    />
                );
            case 'extract':
                return <ExtractView />;
            case 'organize':
                return (
                    <OrganizeView
                        hasRoot={rootFolders.length > 0}
                        onOrganize={() => setOrganizeModalOpen(true)}
                        onAddFolder={addFolder}
                        busy={busy}
                        result={organizeResult}
                        onReset={() => setOrganizeResult(null)}
                    />
                );
            case 'debloat':
                return <DebloatView busy={busy} />;
            case 'privacy':
                return <PrivacyView />;
            case 'legal':
                return <LegalView />;
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

                <ErrorBanner message={error} onDismiss={dismissError} />

                <div className="main-content">
                    <div className="main-content-inner">
                        {renderView()}
                    </div>
                </div>

                <div className="main-status">
                    <span className={`status-dot ${busy ? 'busy' : rootFolders.length > 0 ? '' : 'idle'}`} />
                    <span>{busy || statusText}</span>
                </div>
            </div>

            <ContextPanel
                pipeline={pipeline}
                rootFolders={rootFolders}
                recentFiles={recentFiles}
                onRemoveFolder={removeFolder}
                activityLog={activityLog}
                fileCount={fileCount}
                totalSize={totalSize}
                busy={busy}
                taggedFiles={taggedFiles}
                suggestions={suggestions}
                activeView={activeView}
                organizeResult={organizeResult}
                onOpenFile={(path) => {
                    window.wispApi.openFile(path);
                    logActivity('File opened', path.split(/[\\/]/).pop() || path);
                }}
            />

            <ScanModal
                open={scanModalOpen}
                rootFolders={rootFolders}
                onClose={() => setScanModalOpen(false)}
                onError={onError}
                onComplete={handleScanModalComplete}
            />
            <OrganizeModal
                open={organizeModalOpen}
                folder={rootFolders[0] ?? ''}
                onClose={() => setOrganizeModalOpen(false)}
                onError={onError}
                onOrganize={runOrganize}
            />
        </div>
    );
}
