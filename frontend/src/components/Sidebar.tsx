import {
    FolderSearch,
    Sparkles,
    LayoutGrid,
    Brain,
    ScanText,
    Zap,
} from 'lucide-react';
import type { ViewId } from './AppShell';

type SidebarProps = {
    activeView: ViewId;
    onViewChange: (view: ViewId) => void;
};

const NAV_ITEMS: { id: ViewId; icon: typeof FolderSearch; label: string; section: string }[] = [
    { id: 'scan',      icon: FolderSearch, label: 'Scan & Index',  section: 'Files' },
    { id: 'clean',     icon: Sparkles,     label: 'Clean Up',      section: 'Files' },
    { id: 'visualize', icon: LayoutGrid,   label: 'Visualize',     section: 'Files' },
    { id: 'extract',   icon: ScanText,     label: 'Extract Text',  section: 'Files' },
    { id: 'debloat',   icon: Zap,          label: 'Debloat',       section: 'Files' },
    { id: 'memory',    icon: Brain,        label: 'Memory',        section: 'AI' },
];

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
    const sections = [...new Set(NAV_ITEMS.map(i => i.section))];

    return (
        <nav className="sidebar">
            <div className="sidebar-titlebar" />

            <div className="sidebar-brand">
                <span className="sidebar-brand-icon">✦</span>
                <span className="sidebar-brand-name">Wisp</span>
            </div>

            {sections.map(section => (
                <div key={section} className="sidebar-section">
                    <div className="sidebar-section-label">{section}</div>
                    <div className="sidebar-nav">
                        {NAV_ITEMS.filter(i => i.section === section).map(({ id, icon: Icon, label }) => (
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
                </div>
            ))}

            <div className="sidebar-footer">
                All processing runs locally on your machine.
            </div>
        </nav>
    );
}
