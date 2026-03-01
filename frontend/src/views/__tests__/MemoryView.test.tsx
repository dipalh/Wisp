import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

import MemoryView from '../MemoryView';

function renderMemoryView(overrides: Partial<Parameters<typeof MemoryView>[0]> = {}) {
    const props = {
        hasRoot: true,
        onError: vi.fn(),
        ...overrides,
    };
    const utils = render(<MemoryView {...props} />);
    return { ...utils, props };
}

function getSearchInput(): HTMLInputElement {
    return screen.getByPlaceholderText(/search.*meaning/i) as HTMLInputElement;
}

function getSearchButton() {
    return screen.getByRole('button', { name: /search/i });
}

const fakeResults: SearchResult[] = [
    {
        file_id: 'f-1',
        file_path: '/Users/test/docs/resume.pdf',
        ext: '.pdf',
        score: 0.92,
        snippet: 'Experienced software engineer with 5 years of full-stack development...',
        depth: 'deep',
    },
    {
        file_id: 'f-2',
        file_path: '/Users/test/docs/cover_letter.docx',
        ext: '.docx',
        score: 0.87,
        snippet: 'I am writing to express my interest in the position...',
        depth: 'deep',
    },
    {
        file_id: 'f-3',
        file_path: '/Users/test/images/photo.png',
        ext: '.png',
        score: 0.45,
        snippet: 'A scenic landscape photograph taken in Iceland...',
        depth: 'card',
    },
];

describe('MemoryView — no root folder', () => {
    it('shows empty state when hasRoot is false', () => {
        renderMemoryView({ hasRoot: false });
        expect(screen.getByText(/add and scan a folder/i)).toBeInTheDocument();
    });

    it('does NOT show the search input when hasRoot is false', () => {
        renderMemoryView({ hasRoot: false });
        expect(screen.queryByPlaceholderText(/search.*meaning/i)).toBeNull();
    });
});

describe('MemoryView — search interaction', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    it('renders a search input and search button', () => {
        renderMemoryView();
        expect(getSearchInput()).toBeInTheDocument();
        expect(getSearchButton()).toBeInTheDocument();
    });

    it('calls searchMemory with the query when form is submitted', async () => {
        window.wispApi.searchMemory = vi.fn().mockResolvedValue({
            results: fakeResults, query: 'resume', total: 3,
        });

        renderMemoryView();

        fireEvent.change(getSearchInput(), { target: { value: 'resume' } });
        await act(async () => { fireEvent.click(getSearchButton()); });

        expect(window.wispApi.searchMemory).toHaveBeenCalledWith('resume', { k: 10 });
    });

    it('calls searchMemory when Enter is pressed in the input', async () => {
        window.wispApi.searchMemory = vi.fn().mockResolvedValue({
            results: fakeResults, query: 'resume', total: 3,
        });

        renderMemoryView();

        fireEvent.change(getSearchInput(), { target: { value: 'resume' } });
        await act(async () => { fireEvent.submit(getSearchInput().closest('form')!); });

        expect(window.wispApi.searchMemory).toHaveBeenCalledWith('resume', { k: 10 });
    });

    it('does NOT call searchMemory when query is empty', async () => {
        window.wispApi.searchMemory = vi.fn().mockResolvedValue({
            results: [], query: '', total: 0,
        });

        renderMemoryView();

        await act(async () => { fireEvent.click(getSearchButton()); });

        expect(window.wispApi.searchMemory).not.toHaveBeenCalled();
    });

    it('shows a loading indicator while searching', async () => {
        let resolveSearch!: (v: any) => void;
        window.wispApi.searchMemory = vi.fn().mockImplementation(
            () => new Promise((r) => { resolveSearch = r; }),
        );

        renderMemoryView();

        fireEvent.change(getSearchInput(), { target: { value: 'resume' } });
        await act(async () => { fireEvent.click(getSearchButton()); });

        expect(screen.getByText(/searching/i)).toBeInTheDocument();

        await act(async () => {
            resolveSearch({ results: fakeResults, query: 'resume', total: 3 });
        });

        expect(screen.queryByText(/searching/i)).toBeNull();
    });

    it('disables the search button while searching', async () => {
        let resolveSearch!: (v: any) => void;
        window.wispApi.searchMemory = vi.fn().mockImplementation(
            () => new Promise((r) => { resolveSearch = r; }),
        );

        renderMemoryView();

        fireEvent.change(getSearchInput(), { target: { value: 'resume' } });
        await act(async () => { fireEvent.click(getSearchButton()); });

        expect(getSearchButton()).toBeDisabled();

        await act(async () => {
            resolveSearch({ results: fakeResults, query: 'resume', total: 3 });
        });

        expect(getSearchButton()).not.toBeDisabled();
    });
});

describe('MemoryView — results rendering', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    async function searchAndGetResults() {
        window.wispApi.searchMemory = vi.fn().mockResolvedValue({
            results: fakeResults, query: 'resume', total: 3,
        });
        window.wispApi.openFile = vi.fn().mockResolvedValue({ ok: true });

        const rendered = renderMemoryView();

        fireEvent.change(getSearchInput(), { target: { value: 'resume' } });
        await act(async () => { fireEvent.click(getSearchButton()); });

        return rendered;
    }

    it('renders result cards for each search hit', async () => {
        await searchAndGetResults();

        expect(screen.getByText('resume.pdf')).toBeInTheDocument();
        expect(screen.getByText('cover_letter.docx')).toBeInTheDocument();
        expect(screen.getByText('photo.png')).toBeInTheDocument();
    });

    it('shows the results count and query echo', async () => {
        await searchAndGetResults();

        expect(screen.getByText(/3 results for/i)).toBeInTheDocument();
    });

    it('displays the relevance score for each result', async () => {
        await searchAndGetResults();

        expect(screen.getByText(/0\.92/)).toBeInTheDocument();
        expect(screen.getByText(/0\.87/)).toBeInTheDocument();
        expect(screen.getByText(/0\.45/)).toBeInTheDocument();
    });

    it('displays the snippet text for each result', async () => {
        await searchAndGetResults();

        expect(screen.getByText(/experienced software engineer/i)).toBeInTheDocument();
        expect(screen.getByText(/express my interest/i)).toBeInTheDocument();
    });

    it('displays the depth badge for each result', async () => {
        await searchAndGetResults();

        const deepBadges = screen.getAllByText(/full/i);
        expect(deepBadges.length).toBeGreaterThanOrEqual(2);

        expect(screen.getByText(/card/i)).toBeInTheDocument();
    });

    it('displays the file path for each result', async () => {
        await searchAndGetResults();

        expect(screen.getByText('/Users/test/docs/resume.pdf')).toBeInTheDocument();
        expect(screen.getByText('/Users/test/docs/cover_letter.docx')).toBeInTheDocument();
    });

    it('renders an Open button for each result', async () => {
        await searchAndGetResults();

        const openButtons = screen.getAllByRole('button', { name: /open/i });
        expect(openButtons.length).toBe(3);
    });

    it('calls openFile with the correct path when Open is clicked', async () => {
        await searchAndGetResults();

        const openButtons = screen.getAllByRole('button', { name: /open/i });
        await act(async () => { fireEvent.click(openButtons[0]); });

        expect(window.wispApi.openFile).toHaveBeenCalledWith('/Users/test/docs/resume.pdf');
    });

    it('shows "no results" message when search returns empty', async () => {
        window.wispApi.searchMemory = vi.fn().mockResolvedValue({
            results: [], query: 'xyzzy', total: 0,
        });

        renderMemoryView();

        fireEvent.change(getSearchInput(), { target: { value: 'xyzzy' } });
        await act(async () => { fireEvent.click(getSearchButton()); });

        expect(screen.getByText(/no results/i)).toBeInTheDocument();
    });
});

describe('MemoryView — error handling', () => {
    beforeEach(() => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
    });

    it('calls onError when searchMemory rejects', async () => {
        window.wispApi.searchMemory = vi.fn().mockRejectedValue(
            new Error('Search failed (HTTP 500): internal server error'),
        );

        const { props } = renderMemoryView();

        fireEvent.change(getSearchInput(), { target: { value: 'resume' } });
        await act(async () => { fireEvent.click(getSearchButton()); });

        expect(props.onError).toHaveBeenCalledWith(
            expect.stringContaining('Search failed'),
        );
    });

    it('calls onError when openFile rejects in a search result', async () => {
        window.wispApi.searchMemory = vi.fn().mockResolvedValue({
            results: [fakeResults[0]], query: 'resume', total: 1,
        });
        window.wispApi.openFile = vi.fn().mockRejectedValue(
            new Error('File not found'),
        );

        const { props } = renderMemoryView();

        fireEvent.change(getSearchInput(), { target: { value: 'resume' } });
        await act(async () => { fireEvent.click(getSearchButton()); });

        const openBtn = screen.getByRole('button', { name: /open/i });
        await act(async () => { fireEvent.click(openBtn); });

        expect(props.onError).toHaveBeenCalledWith(
            expect.stringContaining('File not found'),
        );
    });

    it('clears loading state when search fails', async () => {
        window.wispApi.searchMemory = vi.fn().mockRejectedValue(
            new Error('Network error'),
        );

        renderMemoryView();

        fireEvent.change(getSearchInput(), { target: { value: 'resume' } });
        await act(async () => { fireEvent.click(getSearchButton()); });

        expect(screen.queryByText(/searching/i)).toBeNull();
        expect(getSearchButton()).not.toBeDisabled();
    });
});
