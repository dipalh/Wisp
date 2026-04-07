import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import UndoToast from '../UndoToast';


describe('UndoToast', () => {
    it('surfaces partial undo result details when provided', () => {
        render(
            <UndoToast
                visible
                label="Undo organize (2 files)"
                state="done"
                resultMessage="Restored 1 file to its original location (1 failed)"
                onUndo={vi.fn()}
                onDismiss={vi.fn()}
            />,
        );

        expect(screen.getByText(/restored 1 file to its original location \(1 failed\)/i)).toBeInTheDocument();
    });
});
