import { FolderSync, FolderPlus, ArrowRight, Loader2, Info } from 'lucide-react';

type OrganizeViewProps = {
    hasRoot: boolean;
    onOrganize: () => Promise<void>;
    onAddFolder: () => void;
    busy: string;
};

const EXAMPLES = [
    { from: 'report.pdf', to: 'Documents/' },
    { from: 'photo.jpg', to: 'Images/' },
    { from: 'song.mp3', to: 'Audio/' },
    { from: 'clip.mp4', to: 'Videos/' },
    { from: 'backup.zip', to: 'Archives/' },
    { from: 'app.tsx', to: 'Code/' },
    { from: 'readme.txt', to: 'Documents/' },
    { from: 'misc.bin', to: 'Others/' },
];

export default function OrganizeView({ hasRoot, onOrganize, onAddFolder, busy }: OrganizeViewProps) {
    const isOrganizing = busy.toLowerCase().includes('organiz');

    if (!hasRoot) {
        return (
            <div className="empty-state">
                <div className="empty-state-icon">
                    <FolderPlus size={24} strokeWidth={1.5} />
                </div>
                <h2 className="empty-state-title">Add a folder first</h2>
                <p className="empty-state-desc">
                    Pick a folder so Wisp can analyze and auto-sort its contents.
                </p>
                <button className="btn btn-primary" onClick={onAddFolder}>
                    <FolderPlus size={15} />
                    Choose folder
                </button>
            </div>
        );
    }

    return (
        <div className="organize-view">
            <div className="organize-hero">
                <div className="organize-hero-icon">
                    <FolderSync size={32} strokeWidth={1.5} />
                </div>
                <h2 className="organize-hero-title">Smart Organize</h2>
                <p className="organize-hero-desc">
                    Moves top-level files in your selected folder into category
                    subfolders based on file type.
                </p>

                <div className="organize-categories">
                    {['Documents', 'Images', 'Videos', 'Audio', 'Archives', 'Code', 'Others'].map(cat => (
                        <span key={cat} className="organize-category-chip">{cat}</span>
                    ))}
                </div>

                <div className="organize-preview">
                    {EXAMPLES.slice(0, 5).map(({ from, to }) => (
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
                        Only top-level files are moved. Existing subfolders are left untouched.
                        Hidden files (starting with a dot) are skipped. You can always move
                        files back manually to undo.
                    </p>
                </div>
            </div>
        </div>
    );
}
