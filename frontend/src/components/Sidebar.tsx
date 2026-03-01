import {
    FolderSearch,
    Sparkles,
    LayoutGrid,
    Brain,
    MessageSquare,
} from 'lucide-react';
import type { ViewId } from './AppShell';

type SidebarProps = {
    activeView: ViewId;
    onViewChange: (view: ViewId) => void;
};

const NAV_ITEMS: { id: ViewId; icon: typeof FolderSearch; label: string }[] = [
    { id: 'scan', icon: FolderSearch, label: 'Scan' },
    { id: 'clean', icon: Sparkles, label: 'Clean' },
    { id: 'visualize', icon: LayoutGrid, label: 'Visualize' },
    { id: 'memory', icon: Brain, label: 'Memory' },
];

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
    return (
        <nav className="sidebar">
            <div className="sidebar-nav">
                {NAV_ITEMS.map(({ id, icon: Icon, label }) => (
                    <button
                        key={id}
                        className={`sidebar-btn ${activeView === id ? 'active' : ''}`}
                        onClick={() => onViewChange(id)}
                        title={label}
                    >
                        <Icon size={20} />
                    </button>
                ))}
            </div>

            <div className="sidebar-divider" />

            <div className="sidebar-nav-bottom">
                <button
                    className={`sidebar-btn ${activeView === 'assistant' ? 'active' : ''}`}
                    onClick={() => onViewChange('assistant')}
                    title="Assistant"
                >
                    <MessageSquare size={20} />
                </button>
            </div>
        </nav>
    );
}
