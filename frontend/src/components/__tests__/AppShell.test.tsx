import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import AppShell from '../AppShell';

vi.mock('../Sidebar', () => ({
  default: () => <div data-testid="sidebar" />,
}));

vi.mock('../ContextPanel', () => ({
  default: () => <div data-testid="context-panel" />,
}));

vi.mock('../ErrorBanner', () => ({
  default: () => null,
}));

vi.mock('../ScanModal', () => ({
  default: () => null,
}));

vi.mock('../OrganizeModal', () => ({
  default: () => null,
}));

vi.mock('../UndoToast', () => ({
  default: () => null,
}));

vi.mock('../../views/ScanView', () => ({
  default: ({ onAddFolder }: { onAddFolder: () => void }) => (
    <button onClick={onAddFolder}>Add Folder</button>
  ),
}));

vi.mock('../../views/CleanView', () => ({ default: () => null }));
vi.mock('../../views/VisualizeView', () => ({ default: () => null }));
vi.mock('../../views/MemoryView', () => ({ default: () => null }));
vi.mock('../../views/ExtractView', () => ({ default: () => null }));
vi.mock('../../views/DebloatView', () => ({ default: () => null }));
vi.mock('../../views/OrganizeView', () => ({ default: () => null }));
vi.mock('../../views/PrivacyView', () => ({ default: () => null }));
vi.mock('../../views/LegalView', () => ({ default: () => null }));

describe('AppShell root synchronization', () => {
  it('syncs selected roots to the backend when a folder is added', async () => {
    const syncRoots = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, roots: [] })
      .mockResolvedValueOnce({ ok: true, roots: ['/Users/test/root'] });
    const pickFolder = vi.fn().mockResolvedValue('/Users/test/root');
    const scanFolder = vi.fn().mockResolvedValue({
      name: 'root',
      path: '/Users/test/root',
      type: 'folder',
      size: 0,
      children: [],
    });

    window.wispApi.syncRoots = syncRoots;
    window.wispApi.pickFolder = pickFolder;
    window.wispApi.scanFolder = scanFolder;

    render(<AppShell />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Add Folder' }));

    await waitFor(() => {
      expect(syncRoots).toHaveBeenLastCalledWith(['/Users/test/root']);
    });
    expect(pickFolder).toHaveBeenCalledOnce();
    expect(scanFolder).toHaveBeenCalledWith('/Users/test/root');
  });
});
