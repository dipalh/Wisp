import {
    Scale,
    FileText,
    Code2,
    BookOpen,
    ExternalLink,
    ChevronDown,
} from 'lucide-react';
import { useState } from 'react';

type AccordionProps = {
    title: string;
    icon: typeof FileText;
    children: React.ReactNode;
    defaultOpen?: boolean;
};

function Accordion({ title, icon: Icon, children, defaultOpen = false }: AccordionProps) {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div className={`legal-accordion ${open ? 'open' : ''}`}>
            <button className="legal-accordion-header" onClick={() => setOpen(v => !v)}>
                <Icon size={16} className="legal-accordion-icon" />
                <span className="legal-accordion-title">{title}</span>
                <ChevronDown size={14} className={`legal-accordion-chevron ${open ? '' : 'collapsed'}`} />
            </button>
            {open && <div className="legal-accordion-body">{children}</div>}
        </div>
    );
}

const LICENSES = [
    { name: 'React', version: '19.x', license: 'MIT', url: 'https://github.com/facebook/react' },
    { name: 'Vite', version: '7.x', license: 'MIT', url: 'https://github.com/vitejs/vite' },
    { name: 'Lucide Icons', version: '0.575', license: 'ISC', url: 'https://github.com/lucide-icons/lucide' },
    { name: 'Recharts', version: '3.x', license: 'MIT', url: 'https://github.com/recharts/recharts' },
    { name: 'pdf.js', version: '5.x', license: 'Apache-2.0', url: 'https://github.com/nicolo-ribaudo/pdfjs-dist' },
    { name: 'Electron', version: '33.x', license: 'MIT', url: 'https://github.com/electron/electron' },
    { name: 'Celery', version: '5.x', license: 'BSD-3', url: 'https://github.com/celery/celery' },
    { name: 'FastAPI', version: '0.x', license: 'MIT', url: 'https://github.com/tiangolo/fastapi' },
    { name: 'SQLite', version: '3.x', license: 'Public Domain', url: 'https://www.sqlite.org/' },
    { name: 'Sentence Transformers', version: '3.x', license: 'Apache-2.0', url: 'https://github.com/UKPLab/sentence-transformers' },
];

export default function LegalView() {
    return (
        <div className="legal-container">
            {/* Hero */}
            <div className="legal-hero">
                <div className="legal-hero-icon">
                    <Scale size={32} strokeWidth={1.5} />
                </div>
                <h1 className="legal-hero-title">Legal</h1>
                <p className="legal-hero-desc">
                    License information, terms of use, and open-source attributions for Wisp.
                </p>
            </div>

            <div className="legal-sections">
                <Accordion title="Terms of Use" icon={FileText} defaultOpen>
                    <div className="legal-text">
                        <p><strong>Last updated:</strong> March 1, 2026</p>
                        <p>
                            Wisp is provided "as is" without warranty of any kind, express or implied, including but not
                            limited to the warranties of merchantability, fitness for a particular purpose, and noninfringement.
                        </p>
                        <p>
                            By using Wisp, you acknowledge that the software processes files on your local machine and that
                            you are solely responsible for the files you choose to scan, index, organize, or delete.
                        </p>
                        <h4>Acceptable Use</h4>
                        <ul>
                            <li>Use Wisp only on files you own or have permission to access</li>
                            <li>Do not use Wisp to process files containing malware with the intent to distribute</li>
                            <li>Do not reverse-engineer the AI models used in the pipeline</li>
                        </ul>
                        <h4>Limitation of Liability</h4>
                        <p>
                            In no event shall the authors or copyright holders be liable for any claim, damages, or other
                            liability arising from the use of the software. File deletion suggestions are algorithmic
                            recommendations. Always review before confirming.
                        </p>
                    </div>
                </Accordion>

                <Accordion title="Privacy Policy" icon={BookOpen}>
                    <div className="legal-text">
                        <p><strong>Last updated:</strong> March 1, 2026</p>
                        <p>
                            Wisp is a local-first application. We do not operate servers that receive, store, or process
                            your personal data. This privacy policy describes our data practices.
                        </p>
                        <h4>Data We Collect</h4>
                        <p><strong>None.</strong> Wisp does not collect, transmit, or store any personal data on external servers.</p>
                        <h4>Local Data</h4>
                        <p>
                            Wisp maintains a local SQLite database on your machine containing file metadata, AI embeddings,
                            and organizational tags. This data never leaves your device.
                        </p>
                        <h4>Third-Party Services</h4>
                        <p>
                            When you explicitly opt in to "AI Tags" via external API, minimal file metadata (file names and
                            types) may be sent to the configured AI provider. File contents are never transmitted.
                        </p>
                        <h4>Data Retention</h4>
                        <p>
                            All local data persists until you clear the database or uninstall the application. No data is
                            retained on external servers because none is ever sent.
                        </p>
                    </div>
                </Accordion>

                <Accordion title="Open-Source Licenses" icon={Code2}>
                    <div className="legal-text">
                        <p>
                            Wisp is built on the shoulders of incredible open-source projects. Below are the key
                            dependencies and their respective licenses.
                        </p>
                    </div>
                    <div className="legal-licenses-table">
                        <table>
                            <thead>
                                <tr>
                                    <th>Package</th>
                                    <th>Version</th>
                                    <th>License</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {LICENSES.map(({ name, version, license, url }) => (
                                    <tr key={name}>
                                        <td className="legal-pkg-name">{name}</td>
                                        <td className="legal-pkg-version">{version}</td>
                                        <td>
                                            <span className="legal-license-badge">{license}</span>
                                        </td>
                                        <td>
                                            <a
                                                className="legal-pkg-link"
                                                href={url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                            >
                                                <ExternalLink size={12} />
                                            </a>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </Accordion>

                <Accordion title="DMCA & Copyright" icon={FileText}>
                    <div className="legal-text">
                        <p>
                            Wisp processes files locally and does not host or distribute any copyrighted content. If you
                            believe that Wisp is being used in a manner that infringes your copyright, please contact us.
                        </p>
                        <p>
                            <strong>Contact:</strong> legal@wisp.app (placeholder)
                        </p>
                    </div>
                </Accordion>
            </div>

            {/* Footer */}
            <div className="legal-footer">
                <p>© 2026 Wisp. All rights reserved.</p>
                <p>Wisp is open-source software distributed under the MIT License.</p>
            </div>
        </div>
    );
}
