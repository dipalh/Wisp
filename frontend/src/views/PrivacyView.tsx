import {
    ShieldCheck,
    HardDrive,
    Lock,
    Eye,
    Server,
    Fingerprint,
    Wifi,
    Trash2,
    CheckCircle2,
} from 'lucide-react';

const PRINCIPLES = [
    {
        icon: HardDrive,
        title: 'Local-First Processing',
        desc: 'All file scanning, indexing, and analysis happens directly on your machine. Your files never leave your computer unless you explicitly choose to use an external AI provider.',
        color: 'var(--accent)',
    },
    {
        icon: Lock,
        title: 'End-to-End Encryption',
        desc: 'When optional cloud features are used, all data is encrypted in transit using TLS 1.3. Embeddings are generated locally and never stored on external servers.',
        color: '#7c3aed',
    },
    {
        icon: Eye,
        title: 'No Telemetry or Tracking',
        desc: 'Wisp does not collect usage analytics, crash reports, or behavioral data. There are no tracking pixels, no cookies, and no hidden data collection. Period.',
        color: '#059669',
    },
    {
        icon: Server,
        title: 'No Cloud Storage',
        desc: 'Your file index, tags, embeddings, and metadata are stored in a local SQLite database on your machine. We never upload or sync this data to any remote server.',
        color: '#d97706',
    },
    {
        icon: Fingerprint,
        title: 'Zero Personal Data Collection',
        desc: 'Wisp does not require an account, email, or any personal information to use. We do not fingerprint your device or collect hardware identifiers.',
        color: '#dc2626',
    },
    {
        icon: Wifi,
        title: 'Offline Capable',
        desc: 'Core features (scanning, indexing, cleaning, organizing) work entirely offline. Network access is only needed for optional AI-powered tagging via external API.',
        color: '#0891b2',
    },
];

const SAFETY_ITEMS = [
    {
        title: 'Non-Destructive by Default',
        desc: 'Wisp moves files to the system Trash rather than permanently deleting them. You can always recover accidentally removed files.',
    },
    {
        title: 'Confirmation Before Action',
        desc: 'Destructive actions like file deletion or organization always require explicit user confirmation with clear previews of what will change.',
    },
    {
        title: 'Read-Only Scanning',
        desc: 'The scan and index pipeline operates in read-only mode. It reads file contents for embedding but never modifies your original files.',
    },
    {
        title: 'Transparent AI Pipeline',
        desc: 'When AI processes your files, you can see exactly what is being analyzed through the debug panel. Every step of the pipeline is visible and auditable.',
    },
    {
        title: 'Open Source',
        desc: 'Wisp\'s entire codebase is open source and auditable. You can verify exactly how your data is handled by inspecting the source code.',
    },
];

export default function PrivacyView() {
    return (
        <div className="privacy-container">
            {/* Hero */}
            <div className="privacy-hero">
                <div className="privacy-hero-icon">
                    <ShieldCheck size={32} strokeWidth={1.5} />
                </div>
                <h1 className="privacy-hero-title">Privacy & Safety</h1>
                <p className="privacy-hero-desc">
                    Wisp is built with a privacy-first architecture. Your files, your data, your machine.
                    Here's exactly how we protect your information.
                </p>
            </div>

            {/* Trust Badge */}
            <div className="privacy-trust-banner">
                <Lock size={16} />
                <span>All processing runs <strong>locally on your machine</strong>. No data is ever sent to external servers without your explicit consent.</span>
            </div>

            {/* Principles Grid */}
            <div className="privacy-section-heading">
                <h2>Core Principles</h2>
                <p>The foundational commitments that guide how Wisp handles your data.</p>
            </div>
            <div className="privacy-grid">
                {PRINCIPLES.map(({ icon: Icon, title, desc, color }) => (
                    <div className="privacy-card" key={title}>
                        <div className="privacy-card-icon" style={{ background: `${color}12`, color }}>
                            <Icon size={20} strokeWidth={1.5} />
                        </div>
                        <h3 className="privacy-card-title">{title}</h3>
                        <p className="privacy-card-desc">{desc}</p>
                    </div>
                ))}
            </div>

            {/* Safety Section */}
            <div className="privacy-section-heading" style={{ marginTop: 40 }}>
                <h2>Safety Guardrails</h2>
                <p>Built-in protections to ensure Wisp never causes unintended damage to your files.</p>
            </div>
            <div className="privacy-safety-list">
                {SAFETY_ITEMS.map(({ title, desc }) => (
                    <div className="privacy-safety-item" key={title}>
                        <CheckCircle2 size={18} className="privacy-safety-check" />
                        <div>
                            <h4 className="privacy-safety-title">{title}</h4>
                            <p className="privacy-safety-desc">{desc}</p>
                        </div>
                    </div>
                ))}
            </div>

            {/* Data Handling Table */}
            <div className="privacy-section-heading" style={{ marginTop: 40 }}>
                <h2>Data Handling Summary</h2>
                <p>A transparent overview of what data Wisp accesses and how it's handled.</p>
            </div>
            <div className="privacy-table-wrap">
                <table className="privacy-table">
                    <thead>
                        <tr>
                            <th>Data Type</th>
                            <th>Stored Locally</th>
                            <th>Sent to Cloud</th>
                            <th>Encrypted</th>
                        </tr>
                    </thead>
                    <tbody>
                        {[
                            ['File contents', 'Read only', 'Never', 'N/A'],
                            ['File metadata (name, size, date)', 'Yes (SQLite)', 'Never', 'At rest'],
                            ['AI embeddings', 'Yes (SQLite)', 'Never*', 'At rest'],
                            ['Tags & categories', 'Yes (SQLite)', 'Never', 'At rest'],
                            ['Search queries', 'Session only', 'Never', 'N/A'],
                            ['Chat history', 'Session only', 'Never', 'N/A'],
                        ].map(([type, local, cloud, encrypted]) => (
                            <tr key={type}>
                                <td className="privacy-table-type">{type}</td>
                                <td>{local}</td>
                                <td className="privacy-table-never">{cloud}</td>
                                <td>{encrypted}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                <p className="privacy-table-footnote">
                    * When using the optional "AI Tags" feature with an external provider, minimal file metadata may be sent to generate richer tags. File contents are never sent.
                </p>
            </div>

            {/* Delete Data */}
            <div className="privacy-delete-section">
                <Trash2 size={20} />
                <div>
                    <h3>Delete All Data</h3>
                    <p>
                        To completely remove all Wisp data, simply delete the application. All indexed data,
                        embeddings, and metadata are stored in the app's local database and will be removed with it.
                    </p>
                </div>
                <button className="btn btn-secondary privacy-delete-btn">
                    Clear Local Database
                </button>
            </div>
        </div>
    );
}
