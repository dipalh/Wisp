import { useState } from 'react';
import {
    FolderSearch,
    Sparkles,
    LayoutGrid,
    Brain,
    MessageSquare,
    ScanText,
    Zap,
    PlusCircle,
    FileText,
} from 'lucide-react';
import type { ViewId } from './AppShell';

type SidebarProps = {
    activeView: ViewId;
    onViewChange: (view: ViewId) => void;
};

type TabId = 'files' | 'search' | 'assistant';

const TAB_VIEWS: Record<TabId, { id: ViewId; icon: typeof FolderSearch; label: string }[]> = {
    files: [
        { id: 'scan', icon: FolderSearch, label: 'Scan & Index' },
        { id: 'clean', icon: Sparkles, label: 'Clean Up' },
        { id: 'visualize', icon: LayoutGrid, label: 'Visualize' },
        { id: 'extract', icon: ScanText, label: 'Extract Text' },
        { id: 'debloat', icon: Zap, label: 'Debloat' },
    ],
    search: [
        { id: 'memory', icon: Brain, label: 'Memory' },
    ],
    assistant: [
        { id: 'assistant', icon: MessageSquare, label: 'Assistant' },
    ],
};

const TAB_LABELS: Record<TabId, string> = {
    files: 'Files',
    search: 'Search',
    assistant: 'Assistant',
};

function viewToTab(view: ViewId): TabId {
    if (view === 'memory') return 'search';
    if (view === 'assistant') return 'assistant';
    return 'files';
}

/* Session tasks — purposeful scaffolding */
const SESSION_TASKS = [
    { label: 'Scan Documents', active: true },
    { label: 'Analyze Downloads', active: false },
    { label: 'Review Suggestions', active: false },
];

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
    const activeTab = viewToTab(activeView);
    const [currentTab, setCurrentTab] = useState<TabId>(activeTab);

    const handleTabChange = (tab: TabId) => {
        setCurrentTab(tab);
        const first = TAB_VIEWS[tab][0];
        if (first) onViewChange(first.id);
    };

    // Keep tab in sync when view changes externally
    const effectiveTab = viewToTab(activeView);
    if (effectiveTab !== currentTab) {
        // let render catch up
    }

    return (
        <nav className="sidebar">
            {/* Pill tabs — matching Claude Cowork */}
            <div className="sidebar-header">
                <div className="sidebar-tabs">
                    {(['files', 'search', 'assistant'] as TabId[]).map((tab) => (
                        <button
                            key={tab}
                            className={`sidebar-tab ${effectiveTab === tab ? 'active' : ''}`}
                            onClick={() => handleTabChange(tab)}
                        >
                            {TAB_LABELS[tab]}
                        </button>
                    ))}
                </div>
            </div>

            {/* New task */}
            <button className="sidebar-new-task" onClick={() => onViewChange('scan')}>
                <PlusCircle size={18} className="sidebar-new-task-icon" />
                <span>New task</span>
            </button>

            {/* Session tasks */}
            <div className="sidebar-section-label">Session</div>
            {SESSION_TASKS.map((task) => (
                <button
                    key={task.label}
                    className={`sidebar-task-item ${task.active ? 'active' : ''}`}
                >
                    <FileText size={14} className="sidebar-task-icon" />
                    <span className="sidebar-task-label">{task.label}</span>
                </button>
            ))}

            {/* Nav items for current tab */}
            <div className="sidebar-section-label">Views</div>
            <div className="sidebar-nav">
                {TAB_VIEWS[effectiveTab].map(({ id, icon: Icon, label }) => (
                    <button
                        key={id}
                        className={`sidebar-item ${activeView === id ? 'active' : ''}`}
                        onClick={() => onViewChange(id)}
                    >
                        <Icon size={16} className="sidebar-item-icon" />
                        <span className="sidebar-item-label">{label}</span>
                    </button>
                ))}
            </div>

            {/* Footer */}
            <div className="sidebar-footer">
                These tasks run locally and aren't synced across devices.
            </div>
        </nav>
    );
}
