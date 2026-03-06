import { describe, expect, it } from 'vitest';

import { assertWispApiContract, REQUIRED_WISP_API_METHODS } from '../test/wispApiContract';


describe('window.wispApi contract', () => {
    it('shared test setup satisfies the full IPC contract', () => {
        expect(() => assertWispApiContract(window.wispApi)).not.toThrow();
    });

    it('fails loudly when a required method is missing', () => {
        const brokenApi = { ...window.wispApi } as Record<string, unknown>;
        delete brokenApi[REQUIRED_WISP_API_METHODS[0]];

        expect(() => assertWispApiContract(brokenApi)).toThrow(
            /window\.wispApi\..+ is missing/i,
        );
    });
});
