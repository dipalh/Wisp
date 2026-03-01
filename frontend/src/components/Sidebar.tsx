import {
    FolderSearch,
    Sparkles,
    LayoutGrid,
    Brain,
    MessageSquare,
    PlusCircle,
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
    { id: 'memory', icon: Brain, label: 'Memory' },
    { id: 'assistant', icon: MessageSquare, label: 'Assistant' },
];

/** Map each view to its "tab" category */
const viewToTab = (view: ViewId): TabId => {
    if (view === 'assistant') return 'assistant';
    if (view === 'memory') return 'search';
    return 'files';
};

const tabViews: Record<TabId, ViewId[]> = {
    files: ['scan', 'clean', 'visualize'],
    search: ['memory'],
    assistant: ['assistant'],
};

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
    const activeTab = viewToTab(activeView);

    const handleTabClick = (tab: TabId) => {
        // Switch to first view in that tab category
        if (tabViews[tab][0]) {
            onViewChange(tabViews[tab][0]);
        }
    };

    const visibleItems = NAV_ITEMS.filter((item) =>
        tabViews[activeTab].includes(item.id)
    );

    return (
        <nav className="sidebar">
            {/* Segmented tabs (Claude-style Chat/Code/Cowork) */}
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

            {/* Navigation items for current tab */}
            <div className="sidebar-nav">
                {visibleItems.map(({ id, icon: Icon, label }) => (
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

            <div className="sidebar-footer">
                Wisp runs locally on your machine
            </div>
        </nav>
    );
}
