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
    { id: 'scan', icon: FolderSearch, label: 'Scan & Index' },
    { id: 'clean', icon: Sparkles, label: 'Clean Up' },
    { id: 'visualize', icon: LayoutGrid, label: 'Visualize' },
    { id: 'memory', icon: Brain, label: 'Memory' },
    { id: 'assistant', icon: MessageSquare, label: 'Assistant' },
];

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
    return (
        <nav className="sidebar">
            <div className="sidebar-nav">
                {NAV_ITEMS.map(({ id, icon: Icon, label }) => (
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
        </nav>
    );
}
