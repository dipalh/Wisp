import { FolderSync, FolderPlus, ArrowRight, Loader2, Info, CheckCircle2, RotateCcw, FileText, Image, Music, Video, Archive, Code2, Package } from 'lucide-react';

type OrganizeResult = {
    moved: number;
    skipped: number;
    categories: Record<string, number>;
};

type OrganizeViewProps = {
    hasRoot: boolean;
    onOrganize: () => void;
    onAddFolder: () => void;
    busy: string;
    result: OrganizeResult | null;
    onReset: () => void;
};

const CATEGORY_ICONS: Record<string, typeof FileText> = {
    Documents: FileText,
    Images: Image,
    Audio: Music,
    Videos: Video,
    Archives: Archive,
    Code: Code2,
    Others: Package,
};

const EXAMPLES = [
    { from: 'report.pdf', to: 'Documents/' },
    { from: 'photo.jpg', to: 'Images/' },
    { from: 'song.mp3', to: 'Audio/' },
    { from: 'clip.mp4', to: 'Videos/' },
    { from: 'backup.zip', to: 'Archives/' },
];

export default function OrganizeView({ hasRoot, onOrganize, onAddFolder, busy, result, onReset }: OrganizeViewProps) {
    const isOrganizing = busy.toLowerCase().includes('organiz');

    if (!hasRoot) {
        return (
            <div className="empty-state">
                <div className="empty-state-icon">
                    <FolderPlus size={24} strokeWidth={1.5} />
                </div>
                <h2 className="empty-state-title">Add a folder first</h2>
                <p className="empty-state-desc">
                    Pick a folder so Wisp can analyze it and build an organization plan.
                </p>
                <button className="btn btn-primary" onClick={onAddFolder}>
                    <FolderPlus size={15} />
                    Choose folder
                </button>
            </div>
        );
    }

    // Results screen
    if (result && !isOrganizing) {
        const cats = Object.entries(result.categories).sort((a, b) => b[1] - a[1]);
        const nothingToDo = result.moved === 0;

        return (
            <div className="organize-view">
                <div className="organize-result">
                    <div className={`organize-result-icon ${nothingToDo ? 'organize-result-icon--neutral' : ''}`}>
                        <CheckCircle2 size={32} strokeWidth={1.5} />
                    </div>

                    <h2 className="organize-result-title">
                        {nothingToDo ? 'Already organized' : `${result.moved} files organized`}
                    </h2>
                    <p className="organize-result-subtitle">
                        {nothingToDo
                            ? 'All top-level files are already in category folders.'
                            : `${result.skipped > 0 ? `${result.skipped} skipped (already sorted). ` : ''}Files moved into:`}
                    </p>

                    {cats.length > 0 && (
                        <div className="organize-cats-grid">
                            {cats.map(([cat, count]) => {
                                const Icon = CATEGORY_ICONS[cat] ?? Package;
                                return (
                                    <div key={cat} className="organize-cat-card">
                                        <div className="organize-cat-card-icon">
                                            <Icon size={18} strokeWidth={1.5} />
                                        </div>
                                        <div className="organize-cat-card-info">
                                            <span className="organize-cat-card-name">{cat}/</span>
                                            <span className="organize-cat-card-count">{count} file{count !== 1 ? 's' : ''}</span>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}

                    <div className="organize-result-actions">
                        <button className="btn btn-secondary" onClick={onReset}>
                            <RotateCcw size={14} />
                            Organize again
                        </button>
                    </div>

                    <div className="organize-info-box" style={{ marginTop: 0 }}>
                        <Info size={14} />
                        <p>Files were moved into subfolders inside your selected folder. Move them back manually to undo.</p>
                    </div>
                </div>
            </div>
        );
    }

    // Default: setup screen
    return (
        <div className="organize-view">
            <div className="organize-hero">
                <div className="organize-hero-icon">
                    <FolderSync size={32} strokeWidth={1.5} />
                </div>
                <h2 className="organize-hero-title">Smart Organize</h2>
                <p className="organize-hero-desc">
                    Builds a recommended organization strategy from indexed file context,
                    then applies the current best plan.
                </p>

                <div className="organize-categories">
                    {['Documents', 'Images', 'Videos', 'Audio', 'Archives', 'Code', 'Others'].map(cat => (
                        <span key={cat} className="organize-category-chip">{cat}</span>
                    ))}
                </div>

                <div className="organize-preview">
                    {EXAMPLES.map(({ from, to }) => (
                        <div className="organize-preview-row" key={from}>
                            <span className="organize-preview-from">{from}</span>
                            <ArrowRight size={14} className="organize-preview-arrow" />
                            <span className="organize-preview-to">{to}</span>
                        </div>
                    ))}
                </div>

                <button
                    className="btn btn-primary btn-lg"
                    onClick={onOrganize}
                    disabled={!!busy}
                >
                    {isOrganizing ? (
                        <>
                            <Loader2 size={16} className="spin" />
                            Organizing...
                        </>
                    ) : (
                        <>
                            <FolderSync size={16} />
                            Organize Now
                        </>
                    )}
                </button>

                <div className="organize-info-box">
                    <Info size={14} />
                    <p>
                        Organization is generated from the backend proposal flow. Existing
                        subfolders are preserved and hidden files are skipped.
                    </p>
                </div>
            </div>
        </div>
    );
}
