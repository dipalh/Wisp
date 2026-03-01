import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ErrorBanner from '../ErrorBanner';

describe('ErrorBanner', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    it('renders nothing when message is null', () => {
        const { container } = render(
            <ErrorBanner message={null} onDismiss={() => {}} />,
        );
        expect(container.firstChild).toBeNull();
    });

    it('renders the error message when provided', () => {
        render(
            <ErrorBanner message="Connection refused" onDismiss={() => {}} />,
        );
        expect(screen.getByText('Connection refused')).toBeInTheDocument();
    });

    it('renders a dismiss button', () => {
        render(
            <ErrorBanner message="Something broke" onDismiss={() => {}} />,
        );
        expect(screen.getByRole('button', { name: /dismiss/i })).toBeInTheDocument();
    });

    it('calls onDismiss when dismiss button is clicked', async () => {
        vi.useRealTimers();
        const onDismiss = vi.fn();
        render(<ErrorBanner message="Error" onDismiss={onDismiss} />);

        const user = userEvent.setup();
        await user.click(screen.getByRole('button', { name: /dismiss/i }));
        expect(onDismiss).toHaveBeenCalledOnce();
    });

    it('auto-dismisses after 10 seconds', () => {
        const onDismiss = vi.fn();
        render(<ErrorBanner message="Temporary error" onDismiss={onDismiss} />);

        expect(onDismiss).not.toHaveBeenCalled();
        act(() => { vi.advanceTimersByTime(10_000); });
        expect(onDismiss).toHaveBeenCalledOnce();
    });

    it('resets auto-dismiss timer when message changes', () => {
        const onDismiss = vi.fn();
        const { rerender } = render(
            <ErrorBanner message="Error 1" onDismiss={onDismiss} />,
        );

        act(() => { vi.advanceTimersByTime(8_000); });
        expect(onDismiss).not.toHaveBeenCalled();

        rerender(<ErrorBanner message="Error 2" onDismiss={onDismiss} />);
        act(() => { vi.advanceTimersByTime(8_000); });
        expect(onDismiss).not.toHaveBeenCalled();

        act(() => { vi.advanceTimersByTime(2_000); });
        expect(onDismiss).toHaveBeenCalledOnce();
    });

    it('has an error/warning visual role for accessibility', () => {
        render(<ErrorBanner message="Alert!" onDismiss={() => {}} />);
        expect(screen.getByRole('alert')).toBeInTheDocument();
    });
});
