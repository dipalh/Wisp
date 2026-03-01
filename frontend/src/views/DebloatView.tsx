import { useEffect, useState } from 'react';
import { Zap, Check, AlertCircle, Loader, Settings2, Copy, Download, ChevronDown, Apple } from 'lucide-react';

type DebloatOption = {
    id: string;
    name: string;
    description: string;
    category: string;
    default_enabled: boolean;
    sub_options?: DebloatSubOption[];
};

type DebloatSubOption = {
    id: string;
    name: string;
    description: string;
    default_enabled: boolean;
};

type DebloatTask = {
    id: string;
    environment: string;
    options: string[];
    status: 'pending' | 'running' | 'completed' | 'failed';
    output: string;
    error: string;
    progress: number;
};

type DebloatViewProps = {
    busy: string;
};

const isMac = typeof navigator !== 'undefined' &&
    (navigator.userAgent.includes('Mac') || navigator.platform?.toLowerCase().startsWith('mac'));

const MAC_OPTIMIZATIONS = [
    { icon: '🧹', title: 'Cache Cleaner', desc: 'Remove system & app caches to free up disk space' },
    { icon: '🔒', title: 'Privacy Hardening', desc: 'Disable telemetry, analytics & crash reporters' },
    { icon: '⚡', title: 'Startup Items', desc: 'Disable unnecessary login items and launch agents' },
    { icon: '🌐', title: 'DNS & Network', desc: 'Flush DNS cache and reset network settings' },
    { icon: '💾', title: 'Memory Pressure', desc: 'Purge inactive RAM and optimize swap usage' },
    { icon: '🎨', title: 'UI Animations', desc: 'Reduce motion and visual effects for snappier UI' },
];

export default function DebloatView({ busy }: DebloatViewProps) {
    const [options, setOptions] = useState<Record<string, DebloatOption[]>>({});
    const [selectedOptions, setSelectedOptions] = useState<Set<string>>(new Set());
    const [expandedOptions, setExpandedOptions] = useState<Set<string>>(new Set());
    const [environment, setEnvironment] = useState<'auto' | 'wsl' | 'powershell' | 'cmd'>('auto');
    const [currentTask, setCurrentTask] = useState<DebloatTask | null>(null);
    const [loading, setLoading] = useState(!isMac);

    // Load available options on mount — Windows only
    useEffect(() => {
        if (isMac) return;
        const loadOptions = async () => {
            try {
                const res = await fetch('http://localhost:8000/api/v1/debloat/options');
                const data = await res.json();
                setOptions(data.options);

                // No preselected options - user must choose
                setSelectedOptions(new Set());
            } catch (err) {
                console.error('Failed to load debloat options:', err);
            } finally {
                setLoading(false);
            }
        };

        loadOptions();
    }, []);

    const toggleOption = (id: string, parentId?: string, subOptions?: DebloatSubOption[]) => {
        setSelectedOptions((prev) => {
            const next = new Set(prev);
            const isSelected = next.has(id);

            // If toggling a parent with sub-options, select/deselect all children
            if (subOptions && subOptions.length > 0) {
                if (isSelected) {
                    // Deselect parent and all children
                    next.delete(id);
                    subOptions.forEach((sub) => next.delete(sub.id));
                } else {
                    // Select parent and all children
                    next.add(id);
                    subOptions.forEach((sub) => next.add(sub.id));
                }
            } else {
                // Simple toggle for items without children
                if (isSelected) {
                    next.delete(id);
                } else {
                    next.add(id);
                }
            }
            return next;
        });
    };

    const toggleExpanded = (id: string) => {
        setExpandedOptions((prev) => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const handleExecute = async () => {
        if (selectedOptions.size === 0) {
            alert('Please select at least one debloat option');
            return;
        }

        setCurrentTask({
            id: 'pending',
            environment,
            options: Array.from(selectedOptions),
            status: 'running',
            output: '',
            error: '',
            progress: 0,
        });

        try {
            const res = await fetch('http://localhost:8000/api/v1/debloat/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    option_ids: Array.from(selectedOptions),
                    environment,
                }),
            });

            if (!res.ok) throw new Error('Failed to start debloat task');

            const task = await res.json();
            setCurrentTask(task);

            // Poll for status
            const checkStatus = async () => {
                const statusRes = await fetch(`http://localhost:8000/api/v1/debloat/status/${task.id}`);
                const updatedTask = await statusRes.json();
                setCurrentTask(updatedTask);

                if (updatedTask.status === 'running') {
                    setTimeout(checkStatus, 1000);
                }
            };

            setTimeout(checkStatus, 1000);
        } catch (err) {
            console.error('Failed to execute debloat:', err);
            alert('Failed to start debloat task');
        }
    };

    if (isMac) {
        return (
            <div className="debloat-container">
                <div className="debloat-mac-placeholder">
                    <div className="debloat-mac-hero">
                        <Apple size={52} className="debloat-mac-icon" />
                        <h2 className="debloat-mac-title">macOS Debloat</h2>
                        <p className="debloat-mac-subtitle">
                            Coming soon — full macOS optimizations are in development.
                        </p>
                    </div>
                    <div className="debloat-mac-grid">
                        {MAC_OPTIMIZATIONS.map((item) => (
                            <div className="debloat-mac-card" key={item.title}>
                                <span className="debloat-mac-card-icon">{item.icon}</span>
                                <div>
                                    <div className="debloat-mac-card-title">{item.title}</div>
                                    <div className="debloat-mac-card-desc">{item.desc}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="debloat-mac-footer">
                        <span className="debloat-mac-badge">Windows Debloat available now</span>
                        <p>Run Wisp on Windows to access full optimization features including privacy hardening, telemetry removal, and bloatware cleanup.</p>
                    </div>
                </div>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="debloat-container">
                <div className="debloat-empty">
                    <Loader size={40} className="debloat-empty-icon" />
                    <h3 className="debloat-empty-title">Loading options...</h3>
                </div>
            </div>
        );
    }

    if (currentTask && currentTask.status !== 'pending') {
        return (
            <div className="debloat-container">
                <div className="debloat-result">
                    {currentTask.status === 'running' && (
                        <>
                            <div className="debloat-result-icon running">
                                <Loader size={48} className="spin" />
                            </div>
                            <h3 className="debloat-result-title">Debloating Windows...</h3>
                            <p className="debloat-result-desc">
                                Please do not interrupt. This may take several minutes.
                            </p>
                            <div className="debloat-progress">
                                <div
                                    className="debloat-progress-fill"
                                    style={{ width: `${currentTask.progress}%` }}
                                />
                            </div>
                            <p className="debloat-result-env">
                                Environment: <code>{currentTask.environment}</code>
                            </p>
                        </>
                    )}

                    {currentTask.status === 'completed' && (
                        <>
                            <div className="debloat-result-icon success">
                                <Check size={48} />
                            </div>
                            <h3 className="debloat-result-title">Debloat Complete!</h3>
                            <p className="debloat-result-desc">
                                {currentTask.options.length} optimization{currentTask.options.length !== 1 ? 's' : ''} applied successfully.
                            </p>

                            {currentTask.output && (
                                <div className="debloat-output">
                                    <div className="debloat-output-header">
                                        <h4>Execution Log</h4>
                                        <button
                                            className="btn-icon"
                                            onClick={() => navigator.clipboard.writeText(currentTask.output)}
                                            title="Copy to clipboard"
                                        >
                                            <Copy size={16} />
                                        </button>
                                    </div>
                                    <pre className="debloat-output-text">{currentTask.output}</pre>
                                </div>
                            )}

                            <button
                                className="btn btn-primary"
                                onClick={() => setCurrentTask(null)}
                            >
                                Run More Optimizations
                            </button>
                        </>
                    )}

                    {currentTask.status === 'failed' && (
                        <>
                            <div className="debloat-result-icon error">
                                <AlertCircle size={48} />
                            </div>
                            <h3 className="debloat-result-title">Debloat Failed</h3>
                            <p className="debloat-result-desc">
                                {currentTask.error || 'An error occurred during debloating.'}
                            </p>

                            {currentTask.output && (
                                <div className="debloat-output">
                                    <div className="debloat-output-header">
                                        <h4>Debug Output</h4>
                                        <button
                                            className="btn-icon"
                                            onClick={() => navigator.clipboard.writeText(currentTask.output)}
                                            title="Copy to clipboard"
                                        >
                                            <Copy size={16} />
                                        </button>
                                    </div>
                                    <pre className="debloat-output-text">{currentTask.output}</pre>
                                </div>
                            )}

                            <button
                                className="btn btn-secondary"
                                onClick={() => setCurrentTask(null)}
                            >
                                Try Again
                            </button>
                        </>
                    )}
                </div>
            </div>
        );
    }

    return (
        <div className="debloat-container">
            <div className="debloat-selector">
                {/* Options by Category */}
                {Object.entries(options).map(([category, categoryOptions]) => (
                    <div key={category} className="debloat-section">
                        <div className="debloat-section-header">
                            <div className="debloat-category-icon">
                                {category === 'apps' && <Download size={20} />}
                                {category === 'privacy' && <AlertCircle size={20} />}
                                {category === 'system' && <Settings2 size={20} />}
                                {category === 'ai' && <Zap size={20} />}
                                {category === 'appearance' && <Settings2 size={20} />}
                            </div>
                            <h3>{category.charAt(0).toUpperCase() + category.slice(1)}</h3>
                        </div>
                        <div className="debloat-options">
                            {(categoryOptions as DebloatOption[]).map((opt) => {
                                const isExpanded = expandedOptions.has(opt.id);
                                const hasSubOptions = opt.sub_options && opt.sub_options.length > 0;
                                return (
                                    <div key={opt.id} className="debloat-option-group">
                                        <div className="debloat-option-header">
                                            <label className="debloat-option">
                                                <input
                                                    type="checkbox"
                                                    checked={selectedOptions.has(opt.id)}
                                                    onChange={() => toggleOption(opt.id, undefined, opt.sub_options)}
                                                />
                                                <div className="debloat-option-content">
                                                    <span className="debloat-option-name">{opt.name}</span>
                                                    <span className="debloat-option-desc">{opt.description}</span>
                                                </div>
                                            </label>
                                            {hasSubOptions && (
                                                <button
                                                    className="debloat-expand-btn"
                                                    onClick={() => toggleExpanded(opt.id)}
                                                    title={isExpanded ? 'Collapse' : 'Expand'}
                                                >
                                                    <ChevronDown
                                                        size={18}
                                                        style={{
                                                            transform: isExpanded ? 'rotate(0deg)' : 'rotate(-90deg)',
                                                            transition: 'transform 200ms ease',
                                                        }}
                                                    />
                                                </button>
                                            )}
                                        </div>
                                        
                                        {/* Sub-options (nested items) - collapsible */}
                                        {hasSubOptions && isExpanded && (
                                            <div className="debloat-sub-options">
                                                {opt.sub_options!.map((sub) => (
                                                    <label key={sub.id} className="debloat-sub-option">
                                                        <input
                                                            type="checkbox"
                                                            checked={selectedOptions.has(sub.id)}
                                                            onChange={() => toggleOption(sub.id)}
                                                        />
                                                        <div className="debloat-option-content">
                                                            <span className="debloat-option-name">{sub.name}</span>
                                                            <span className="debloat-option-desc">{sub.description}</span>
                                                        </div>
                                                    </label>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                ))}

                {/* Action Button */}
                <div className="debloat-action">
                    <button
                        className="btn btn-primary"
                        onClick={handleExecute}
                        disabled={selectedOptions.size === 0 || !!busy}
                    >
                        <Zap size={18} />
                        Start Optimization ({selectedOptions.size})
                    </button>
                </div>
            </div>
        </div>
    );
}
