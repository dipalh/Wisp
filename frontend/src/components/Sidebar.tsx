import {
    FolderSearch,
    Sparkles,
    LayoutGrid,
    Brain,
    ScanText,
    Zap,
    FolderSync,
    ShieldCheck,
    Scale,
    LogOut,
    Settings,
} from 'lucide-react';
import { useEffect, useState } from 'react';
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
    { id: 'organize',  icon: FolderSync,   label: 'Organize',      section: 'Files' },
    { id: 'debloat',   icon: Zap,          label: 'Debloat',       section: 'Files' },
    { id: 'memory',    icon: Brain,        label: 'Memory',        section: 'AI' },
];

const BOTTOM_NAV_ITEMS: { id: ViewId; icon: typeof ShieldCheck; label: string }[] = [
    { id: 'privacy', icon: ShieldCheck, label: 'Privacy & Safety' },
    { id: 'legal',   icon: Scale,       label: 'Legal' },
];

function WispLogo() {
    return (
        <img
            src="/Generated_Image_February_28_2026_-_9_34PM.jpg"
            alt="Wisp"
            className="sidebar-brand-logo"
        />
    );
}

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
    const sections = [...new Set(NAV_ITEMS.map(i => i.section))];
    const [username, setUsername] = useState('User');

    useEffect(() => {
        if (window.wispApi?.getUsername) {
            Promise.resolve(window.wispApi.getUsername()).then((name) => {
                if (name) setUsername(name);
            });
        }
    }, []);

    const initial = username.charAt(0).toUpperCase();

    return (
        <nav className="sidebar">
            <div className="sidebar-titlebar" />

            <div className="sidebar-brand">
                <WispLogo />
                {/* <span className="lolXD sidebar-brand-wordmark">isp</span> */}
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

            <div className="sidebar-bottom">
                <div className="sidebar-nav sidebar-bottom-nav">
                    {BOTTOM_NAV_ITEMS.map(({ id, icon: Icon, label }) => (
                        <button
                            key={id}
                            className={`sidebar-item sidebar-item-subtle ${activeView === id ? 'active' : ''}`}
                            onClick={() => onViewChange(id)}
                        >
                            <Icon size={15} className="sidebar-item-icon" />
                            <span className="sidebar-item-label">{label}</span>
                        </button>
                    ))}
                    <button className="sidebar-item sidebar-item-subtle sidebar-settings-btn" onClick={() => onViewChange('privacy')}>
                        <Settings size={15} className="sidebar-item-icon" />
                        <span className="sidebar-item-label">Settings</span>
                    </button>
                </div>
                <div className="sidebar-divider" />
                <div className="sidebar-user">
                    <div className="sidebar-user-avatar">{initial}</div>
                    <div className="sidebar-user-info">
                        <span className="sidebar-user-name">{username}</span>
                        <span className="sidebar-user-plan">Free Plan</span>
                    </div>
                    <button className="sidebar-logout-btn" title="Sign out">
                        <LogOut size={14} />
                    </button>
                </div>
                <div className="sidebar-footer">
                    <span className="sidebar-footer-version">Wisp v1.0.0</span>
                    <span className="sidebar-footer-dot">·</span>
                    <span>All processing runs locally</span>
                </div>
            </div>
        </nav>
    );
}
