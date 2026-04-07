import { describe, expect, it } from 'vitest';

import { assertWispApiContract, REQUIRED_WISP_API_METHODS } from '../wispApiContract';

function buildApiStub(): Record<string, () => unknown> {
  const api: Record<string, () => unknown> = {};
  for (const method of REQUIRED_WISP_API_METHODS) {
    api[method] = () => undefined;
  }
  return api;
}

describe('wispApi contract', () => {
  it('includes propose-first organizer IPC methods', () => {
    expect(REQUIRED_WISP_API_METHODS).toContain('organizeGetProposals');
    expect(REQUIRED_WISP_API_METHODS).toContain('organizeAcceptProposal');
    expect(REQUIRED_WISP_API_METHODS).toContain('organizeApplyBatch');
    expect(REQUIRED_WISP_API_METHODS).toContain('organizeUndoBatch');
    expect(REQUIRED_WISP_API_METHODS).toContain('organizeRegisterUndoBatch');
    expect(REQUIRED_WISP_API_METHODS).toContain('organizeClearUndoBatch');
  });

  it('requires explicit root synchronization for backend-scoped flows', () => {
    expect(REQUIRED_WISP_API_METHODS).toContain('syncRoots');
  });

  it('deprecates deterministic organizeFolder from required IPC contract', () => {
    expect(REQUIRED_WISP_API_METHODS).not.toContain('organizeFolder');
  });

  it('deprecates legacy undoOrganize compatibility methods from the IPC contract', () => {
    expect(REQUIRED_WISP_API_METHODS).not.toContain('undoOrganize');
    expect(REQUIRED_WISP_API_METHODS).not.toContain('canUndoOrganize');
  });

  it('does not expose deprecated organizeFolder on the shared test stub', () => {
    expect('organizeFolder' in window.wispApi).toBe(false);
  });

  it('fails loudly and deterministically when a required method is missing', () => {
    const api = buildApiStub();
    delete api.askAssistant;

    const expectedMessage =
      `window.wispApi.askAssistant is missing. Required methods: ${REQUIRED_WISP_API_METHODS.join(', ')}`;

    expect(() => assertWispApiContract(api)).toThrowError(expectedMessage);
  });
});
