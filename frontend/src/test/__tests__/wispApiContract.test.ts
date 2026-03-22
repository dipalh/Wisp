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
  it('fails loudly and deterministically when a required method is missing', () => {
    const api = buildApiStub();
    delete api.askAssistant;

    const expectedMessage =
      `window.wispApi.askAssistant is missing. Required methods: ${REQUIRED_WISP_API_METHODS.join(', ')}`;

    expect(() => assertWispApiContract(api)).toThrowError(expectedMessage);
  });
});
