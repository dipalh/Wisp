import { useState, useRef } from 'react';
import {
    Wand2,
    FolderTree,
    CheckCircle2,
    XCircle,
    Loader2,
    ChevronDown,
    ChevronRight,
} from 'lucide-react';
import type { JobState } from '../components/AppShell';

type OrganizeViewProps = {
    rootFolders: string[];
    busy: string;
    onJobUpdate: (job: JobState) => void;
};

export default function OrganizeView({ rootFolders, busy, onJobUpdate }: OrganizeViewProps) {
    const [state, setState] = useState<'idle' | 'loading' | 'ready' | 'applying' | 'done' | 'error'>('idle');
    const [proposals, setProposals] = useState<DirectoryProposal[]>([]);
    const [recommendation, setRecommendation] = useState('');
    const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
    const [job, setJob] = useState<JobState>(null);
    const [resultMsg, setResultMsg] = useState('');
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const hasRoot = rootFolders.length > 0;

    const generatePlan = async () => {
        if (!hasRoot) return;
        setState('loading');
        setProposals([]);
        setRecommendation('');
        setJob(null);
        onJobUpdate(null);
        setResultMsg('');
        try {
            const result = await window.wispApi.organizeFolder(rootFolders[0]);
            setProposals(result.proposals ?? []);
            setRecommendation(result.recommendation ?? '');
            setState(result.proposals?.length ? 'ready' : 'error');
        } catch {
            setState('error');
        }
    };

    const applyProposal = async (proposal: DirectoryProposal) => {
        setState('applying');
        const initial: JobState = {
            job_id: '',
            status: 'queued',
            progress_current: 0,
            progress_total: proposal.mappings.length,
            progress_message: 'Starting\u2026',
        };
        setJob(initial);
        onJobUpdate(initial);

        try {
            const { job_id } = await window.wispApi.applyOrganize(rootFolders[0], proposal.mappings);
            const withId: JobState = { ...initial, job_id };
            setJob(withId);
            onJobUpdate(withId);

            timerRef.current = setInterval(async () => {
                try {
                    const data = await window.wispApi.pollJob(job_id);
                    const updated: JobState = {
                        job_id: data.job_id,
                        status: data.status,
                        progress_current: data.progress_current,
                        progress_total: data.progress_total,
                        progress_message: data.progress_message,
                    };
                    setJob(updated);
                    onJobUpdate(updated);

                    if (data.status === 'success' || data.status === 'failed') {
                        if (timerRef.current) clearInterval(timerRef.current);
                        timerRef.current = null;
                        setResultMsg(data.progress_message ?? '');
                        setState(data.status === 'success' ? 'done' : 'error');
                    }
                } catch {
                    // keep polling
                }
            }, 800);
        } catch {
            setState('error');
        }
    };

    const pct = job && job.progress_total > 0
        ? Math.round((job.progress_current / job.progress_total) * 100)
        : 0;
    const isTerminal = job?.status === 'success' || job?.status === 'failed';

    if (!hasRoot) {
        return (
            <div className="empty-state">
                <div className="empty-state-icon"><Wand2 size={24} strokeWidth={1.5} /></div>
                <h2 className="empty-state-title">No folder selected</h2>
                <p className="empty-state-desc">Go to Scan &amp; Index to add a folder first.</p>
            </div>
        );
    }

    return (
        <div className="doc-flow">
            {/* Action row */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <button
                    className="btn btn-primary"
                    onClick={generatePlan}
                    disabled={!!busy || state === 'loading' || state === 'applying'}
                >
                    <Wand2 size={14} />
                    {state === 'ready' || state === 'done' ? 'Regenerate plan' : 'Generate plan'}
                </button>
                {state === 'done' && resultMsg && (
                    <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{resultMsg}</span>
                )}
                {state === 'error' && state !== 'applying' && (
                    <span style={{ fontSize: 13, color: '#e53e3e' }}>Failed — try again</span>
                )}
            </div>

            {/* Loading */}
            {state === 'loading' && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '16px 0', color: 'var(--text-muted)' }}>
                    <Loader2 size={16} className="spin" />
                    <span style={{ fontSize: 13 }}>Asking AI for organization proposals\u2026</span>
                </div>
            )}

            {/* AI Recommendation banner */}
            {recommendation && state === 'ready' && (
                <div className="organize-recommendation">
                    <span className="organize-recommendation-label">AI Recommendation</span>
                    {recommendation}
                </div>
            )}

            {/* Proposal cards */}
            {state === 'ready' && proposals.map((proposal, idx) => (
                <div className="organize-proposal" key={proposal.name}>
                    <div className="organize-proposal-header">
                        <div style={{ flex: 1, minWidth: 0 }}>
                            <div className="organize-proposal-name">{proposal.name}</div>
                            <div className="organize-proposal-rationale">{proposal.rationale}</div>
                        </div>
                        <button
                            className="btn btn-primary"
                            style={{ flexShrink: 0 }}
                            onClick={() => applyProposal(proposal)}
                        >
                            Apply
                        </button>
                    </div>

                    {/* Toggle folder tree + mappings */}
                    <button
                        className="organize-tree-toggle"
                        onClick={() => setExpandedIdx(expandedIdx === idx ? null : idx)}
                    >
                        {expandedIdx === idx ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                        <FolderTree size={13} />
                        <span>{proposal.folder_tree.length} folders &middot; {proposal.mappings.length} file moves</span>
                    </button>

                    {expandedIdx === idx && (
                        <div className="organize-tree">
                            {proposal.folder_tree.map((folder) => (
                                <div className="organize-tree-item" key={folder}>
                                    <span className="organize-tree-folder">{folder}</span>
                                </div>
                            ))}
                            <div className="organize-tree-divider" />
                            {proposal.mappings.slice(0, 12).map((m) => (
                                <div className="organize-mapping" key={m.original_path}>
                                    <span className="organize-mapping-src" title={m.original_path}>
                                        {m.original_path.split(/[/\\]/).pop()}
                                    </span>
                                    <span className="organize-mapping-arrow">&rarr;</span>
                                    <span className="organize-mapping-dst" title={m.suggested_path}>
                                        {m.suggested_path}
                                    </span>
                                </div>
                            ))}
                            {proposal.mappings.length > 12 && (
                                <div style={{ fontSize: 11, color: 'var(--text-faint)', paddingTop: 4 }}>
                                    \u2026 and {proposal.mappings.length - 12} more files
                                </div>
                            )}
                        </div>
                    )}
                </div>
            ))}

            {/* Progress bar (reused from scan) */}
            {(state === 'applying' || (isTerminal && job)) && job && (
                <div className="job-progress-panel">
                    <div className="job-progress-header">
                        {(job.status === 'queued' || job.status === 'running') && <Loader2 size={16} className="spin" />}
                        {job.status === 'success' && <CheckCircle2 size={16} style={{ color: 'var(--accent)' }} />}
                        {job.status === 'failed' && <XCircle size={16} style={{ color: '#e53e3e' }} />}
                        <span className="job-progress-status">
                            {(job.status === 'queued' || job.status === 'running') && 'Applying plan\u2026'}
                            {job.status === 'success' && 'Organize complete'}
                            {job.status === 'failed' && 'Organize failed'}
                        </span>
                        {job.progress_total > 0 && (
                            <span className="job-progress-count">
                                {job.progress_current} / {job.progress_total}
                            </span>
                        )}
                    </div>
                    <div className="job-progress-track">
                        <div
                            className={`job-progress-fill ${isTerminal ? (job.status === 'success' ? 'done' : 'error') : ''}`}
                            style={{ width: `${pct}%` }}
                        />
                    </div>
                    <div className="job-progress-message">{job.progress_message || '\u2014'}</div>
                </div>
            )}
        </div>
    );
}
