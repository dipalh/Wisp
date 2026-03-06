import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import MemoryView from '../MemoryView';


const fakeAssistantResponse = {
    answer: 'Your resume is in **resume.pdf**.',
    proposals: [],
    query: 'find my resume',
    sources: ['/Users/test/docs/resume.pdf', '/Users/test/docs/cover_letter.docx'],
    deepened_files: [],
};

function setVoicesResult() {
    window.wispApi.getVoices = vi.fn().mockResolvedValue({
        voices: [
            { voice_id: 'voice-1', name: 'Adam', category: 'premade' },
        ],
    });
}

async function renderMemoryView(overrides: Partial<Parameters<typeof MemoryView>[0]> = {}) {
    const props = {
        hasRoot: true,
        onError: vi.fn(),
        ...overrides,
    };

    const utils = render(<MemoryView {...props} />);

    await act(async () => {
        await Promise.resolve();
    });

    return { ...utils, props };
}

function getPromptInput(): HTMLTextAreaElement {
    return screen.getByPlaceholderText(/ask about your files/i) as HTMLTextAreaElement;
}

function getSendButton() {
    return screen.getByRole('button', { name: /send/i });
}

describe('MemoryView — no root folder', () => {
    beforeEach(() => {
        setVoicesResult();
    });

    afterEach(() => {
        vi.restoreAllMocks();
        localStorage.clear();
    });

    it('shows empty state when hasRoot is false', async () => {
        await renderMemoryView({ hasRoot: false });
        expect(screen.getByText(/no files in memory yet/i)).toBeInTheDocument();
        expect(screen.getByText(/scan & index/i)).toBeInTheDocument();
    });

    it('does not show the assistant input when hasRoot is false', async () => {
        await renderMemoryView({ hasRoot: false });
        expect(screen.queryByPlaceholderText(/ask about your files/i)).toBeNull();
    });
});

describe('MemoryView — assistant interaction', () => {
    beforeEach(() => {
        setVoicesResult();
        window.wispApi.askAssistant = vi.fn().mockResolvedValue(fakeAssistantResponse);
        window.wispApi.openFile = vi.fn().mockResolvedValue({ ok: true });
    });

    afterEach(() => {
        vi.restoreAllMocks();
        localStorage.clear();
    });

    it('renders the prompt input and send button', async () => {
        await renderMemoryView();
        expect(getPromptInput()).toBeInTheDocument();
        expect(getSendButton()).toBeInTheDocument();
    });

    it('calls askAssistant with the typed prompt when send is clicked', async () => {
        await renderMemoryView();

        fireEvent.change(getPromptInput(), { target: { value: 'find my resume' } });
        await act(async () => {
            fireEvent.click(getSendButton());
        });

        expect(window.wispApi.askAssistant).toHaveBeenCalledWith('find my resume');
    });

    it('calls askAssistant when Enter is pressed without Shift', async () => {
        await renderMemoryView();

        fireEvent.change(getPromptInput(), { target: { value: 'find my resume' } });
        await act(async () => {
            fireEvent.keyDown(getPromptInput(), { key: 'Enter', code: 'Enter' });
        });

        expect(window.wispApi.askAssistant).toHaveBeenCalledWith('find my resume');
    });

    it('does not call askAssistant when the prompt is empty', async () => {
        await renderMemoryView();

        await act(async () => {
            fireEvent.click(getSendButton());
        });

        expect(window.wispApi.askAssistant).not.toHaveBeenCalled();
    });

    it('shows the loading state while waiting for the assistant', async () => {
        let resolveAssistant!: (value: typeof fakeAssistantResponse) => void;
        window.wispApi.askAssistant = vi.fn().mockImplementation(
            () => new Promise((resolve) => {
                resolveAssistant = resolve;
            }),
        );

        await renderMemoryView();

        fireEvent.change(getPromptInput(), { target: { value: 'find my resume' } });
        await act(async () => {
            fireEvent.click(getSendButton());
        });

        expect(screen.getByText(/searching your files/i)).toBeInTheDocument();

        await act(async () => {
            resolveAssistant(fakeAssistantResponse);
        });

        await waitFor(() => {
            expect(screen.queryByText(/searching your files/i)).toBeNull();
        });
    });

    it('renders the assistant answer and source chips', async () => {
        await renderMemoryView();

        fireEvent.change(getPromptInput(), { target: { value: 'find my resume' } });
        await act(async () => {
            fireEvent.click(getSendButton());
        });

        expect(screen.getByText(/your resume is in/i)).toBeInTheDocument();
        expect(screen.getAllByText('resume.pdf').length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText('cover_letter.docx')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /resume\.pdf/i })).toBeInTheDocument();
    });

    it('opens the correct source file when a source chip is clicked', async () => {
        await renderMemoryView();

        fireEvent.change(getPromptInput(), { target: { value: 'find my resume' } });
        await act(async () => {
            fireEvent.click(getSendButton());
        });

        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: /resume\.pdf/i }));
        });

        expect(window.wispApi.openFile).toHaveBeenCalledWith('/Users/test/docs/resume.pdf');
    });

    it('surfaces open-file failures through onError', async () => {
        window.wispApi.openFile = vi.fn().mockRejectedValue(new Error('Finder failed'));
        const { props } = await renderMemoryView();

        fireEvent.change(getPromptInput(), { target: { value: 'find my resume' } });
        await act(async () => {
            fireEvent.click(getSendButton());
        });

        await act(async () => {
            fireEvent.click(screen.getByRole('button', { name: /resume\.pdf/i }));
        });

        expect(props.onError).toHaveBeenCalledWith(expect.stringContaining('Finder failed'));
    });

    it('renders a degraded assistant message when askAssistant rejects', async () => {
        window.wispApi.askAssistant = vi.fn().mockRejectedValue(new Error('Backend offline'));
        await renderMemoryView();

        fireEvent.change(getPromptInput(), { target: { value: 'find my resume' } });
        await act(async () => {
            fireEvent.click(getSendButton());
        });

        expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
        expect(screen.getByText(/backend offline/i)).toBeInTheDocument();
    });
});
