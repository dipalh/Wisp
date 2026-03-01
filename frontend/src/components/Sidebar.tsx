import {
    FolderSearch,
    Sparkles,
    LayoutGrid,
    Brain,
    MessageSquare,
    PlusCircle,
    FileText,
    ScanText,
} from 'lucide-react';
import type { ViewId } from './AppShell';

type SidebarProps = {
    activeView: ViewId;
    onViewChange: (view: ViewId) => void;
};

type TabId = 'files' | 'search' | 'assistant';

const NAV_ITEMS: { id: ViewId; icon: typeof FolderSearch; label: string }[] = [
    { id: 'scan', icon: FolderSearch, label: 'Scan & Index' },
    { id: 'clean', icon: Sparkles, label: 'Clean Up' },
    { id: 'visualize', icon: LayoutGrid, label: 'Visualize' },
    { id: 'extract', icon: ScanText, label: 'Extract Text' },
    { id: 'memory', icon: Brain, label: 'Memory' },
    { id: 'assistant', icon: MessageSquare, label: 'Assistant' },
];

const viewToTab = (view: ViewId): TabId => {
    if (view === 'assistant') return 'assistant';
    if (view === 'memory') return 'search';
    return 'files';
};

const tabViews: Record<TabId, ViewId[]> = {
    files: ['scan', 'clean', 'visualize', 'extract'],
    search: ['memory'],
    assistant: ['assistant'],
};

/* Dummy session tasks — purposeful scaffolding */
const SESSION_TASKS = [
    { label: 'Scan Documents', active: true },
    { label: 'Analyze Downloads', active: false },
    { label: 'Review Suggestions', active: false },
];

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
    const activeTab = viewToTab(activeView);

    const handleTabClick = (tab: TabId) => {
        if (tabViews[tab][0]) onViewChange(tabViews[tab][0]);
    };

    const visibleItems = NAV_ITEMS.filter((item) =>
        tabViews[activeTab].includes(item.id)
    );

    return (
        <nav className="sidebar">
            {/* Segmented tabs */}
            <div className="sidebar-header">
                <div className="sidebar-tabs">
                    <button
                        className={`sidebar-tab ${activeTab === 'files' ? 'active' : ''}`}
                        onClick={() => handleTabClick('files')}
                    >
                        Files
                    </button>
                    <button
                        className={`sidebar-tab ${activeTab === 'search' ? 'active' : ''}`}
                        onClick={() => handleTabClick('search')}
                    >
                        Search
                    </button>
                    <button
                        className={`sidebar-tab ${activeTab === 'assistant' ? 'active' : ''}`}
                        onClick={() => handleTabClick('assistant')}
                    >
                        Assistant
                    </button>
                </div>
            </div>

            {/* "New task" action */}
            <button className="sidebar-new-task" onClick={() => onViewChange('scan')}>
                <PlusCircle size={16} className="sidebar-new-task-icon" />
                <span>New task</span>
            </button>

            {/* Current session tasks */}
            <div className="sidebar-section-label">Session</div>
            {SESSION_TASKS.map((task) => (
                <div
                    key={task.label}
                    className={`sidebar-task-item ${task.active ? 'active' : ''}`}
                >
                    <FileText size={14} className="sidebar-task-icon" />
                    <span className="sidebar-task-label">{task.label}</span>
                </div>
            ))}

            <div className="sidebar-divider" />

            {/* Navigation items for current tab */}
            <div className="sidebar-section-label">Views</div>
            <div className="sidebar-nav">
                {visibleItems.map(({ id, icon: Icon, label }) => (
                    <button
                        key={id}
                        className={`sidebar-item ${activeView === id ? 'active' : ''}`}
                        onClick={() => onViewChange(id)}
                    >
                        <Icon size={15} className="sidebar-item-icon" />
                        <span className="sidebar-item-label">{label}</span>
                    </button>
                ))}
            </div>

            <div className="sidebar-footer">
                These tasks run locally and aren't synced across devices
            </div>
        </nav>
    );
}
