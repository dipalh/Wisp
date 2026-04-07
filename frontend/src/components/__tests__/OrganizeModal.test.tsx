import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import OrganizeModal from '../OrganizeModal';


const baseProposals = {
    recommendation: 'Use Project Buckets for the clearest organization.',
    degraded: false,
    strategies: [
        {
            proposal_id: 'strategy-1',
            name: 'Project Buckets',
            rationale: 'Groups related files by project.',
            reasons: ['Shared project context', 'Keeps reviewable batches'],
            citations: ['/Users/test/root/spec.md', '/Users/test/root/mockup.png'],
            folder_tree: ['Projects/Alpha/', 'Projects/Beta/'],
            mappings: [
                {
                    original_path: '/Users/test/root/spec.md',
                    suggested_path: '/Users/test/root/Projects/Alpha/spec.md',
                },
            ],
        },
        {
            proposal_id: 'strategy-2',
            name: 'Media First',
            rationale: 'Separates assets from documents.',
            reasons: ['Fast to browse', 'Good for mixed folders'],
            citations: ['/Users/test/root/mockup.png'],
            folder_tree: ['Media/Images/', 'Docs/'],
            mappings: [
                {
                    original_path: '/Users/test/root/mockup.png',
                    suggested_path: '/Users/test/root/Media/Images/mockup.png',
                },
            ],
        },
    ],
};

describe('OrganizeModal', () => {
    it('loads and renders truthful organization strategies when opened', async () => {
        const onLoadProposals = vi.fn().mockResolvedValue(baseProposals);

        render(
            <OrganizeModal
                open
                folder="/Users/test/root"
                onClose={() => {}}
                onError={() => {}}
                onLoadProposals={onLoadProposals}
                onApplyStrategy={vi.fn()}
            />,
        );

        expect(screen.getByRole('heading', { name: /loading organization strategies/i })).toBeInTheDocument();

        await waitFor(() => {
            expect(screen.getByText('Project Buckets')).toBeInTheDocument();
        });

        expect(onLoadProposals).toHaveBeenCalledOnce();
        expect(screen.getByText(/use project buckets for the clearest organization/i)).toBeInTheDocument();
        expect(screen.getByText(/shared project context/i)).toBeInTheDocument();
        expect(screen.getAllByText(/mockup\.png/i).length).toBeGreaterThan(0);
        expect(screen.getByRole('button', { name: /apply selected plan/i })).toBeInTheDocument();
    });

    it('applies the selected strategy and renders a truthful success summary', async () => {
        const onApplyStrategy = vi.fn().mockResolvedValue({
            moved: 1,
            skipped: 0,
            failed: 0,
            partial: false,
            categories: { Projects: 1 },
            warnings: [],
        });

        render(
            <OrganizeModal
                open
                folder="/Users/test/root"
                onClose={() => {}}
                onError={() => {}}
                onLoadProposals={vi.fn().mockResolvedValue(baseProposals)}
                onApplyStrategy={onApplyStrategy}
            />,
        );

        await waitFor(() => {
            expect(screen.getByText('Project Buckets')).toBeInTheDocument();
        });

        const user = userEvent.setup();
        await user.click(screen.getByRole('radio', { name: /media first/i }));
        await user.click(screen.getByRole('button', { name: /apply selected plan/i }));

        expect(onApplyStrategy).toHaveBeenCalledWith(
            expect.objectContaining({ proposal_id: 'strategy-2', name: 'Media First' }),
        );

        await waitFor(() => {
            expect(screen.getByText(/organization applied successfully/i)).toBeInTheDocument();
        });

        expect(screen.getByText(/1 file moved/i)).toBeInTheDocument();
        expect(screen.getByText(/Projects/i)).toBeInTheDocument();
    });

    it('surfaces partial apply results with warnings instead of claiming full success', async () => {
        const onApplyStrategy = vi.fn().mockResolvedValue({
            moved: 1,
            skipped: 0,
            failed: 1,
            partial: true,
            categories: { Projects: 1 },
            warnings: ['collision.txt: destination already exists'],
        });

        render(
            <OrganizeModal
                open
                folder="/Users/test/root"
                onClose={() => {}}
                onError={() => {}}
                onLoadProposals={vi.fn().mockResolvedValue(baseProposals)}
                onApplyStrategy={onApplyStrategy}
            />,
        );

        await waitFor(() => {
            expect(screen.getByText('Project Buckets')).toBeInTheDocument();
        });

        const user = userEvent.setup();
        await user.click(screen.getByRole('button', { name: /apply selected plan/i }));

        await waitFor(() => {
            expect(screen.getByText(/organization applied with warnings/i)).toBeInTheDocument();
        });

        expect(screen.getByText(/1 file moved/i)).toBeInTheDocument();
        expect(screen.getByText(/1 failed/i)).toBeInTheDocument();
        expect(screen.getByText(/destination already exists/i)).toBeInTheDocument();
    });
});
