export const REQUIRED_WISP_API_METHODS = [
    'getUsername',
    'pickFolder',
    'syncRoots',
    'scanFolder',
    'organizeGetProposals',
    'organizeAcceptProposal',
    'organizeApplyBatch',
    'organizeUndoBatch',
    'organizeRegisterUndoBatch',
    'organizeClearUndoBatch',
    'tagFiles',
    'suggestDelete',
    'trashPath',
    'readFileBase64',
    'pickFileForOcr',
    'extractText',
    'extractTextFromBuffer',
    'transcribeFile',
    'speakText',
    'getVoices',
    'showInFolder',
    'openPath',
    'askAssistant',
    'startScanJob',
    'pollJob',
    'getIndexedFiles',
    'openFile',
    'searchMemory',
    'onUndoTriggered',
    'onUndoAvailable',
] as const;

export function assertWispApiContract(api: unknown): asserts api is Window['wispApi'] {
    if (!api || typeof api !== 'object') {
        throw new Error(
            `window.wispApi is missing. Required methods: ${REQUIRED_WISP_API_METHODS.join(', ')}`,
        );
    }

    for (const method of REQUIRED_WISP_API_METHODS) {
        if (typeof (api as Record<string, unknown>)[method] !== 'function') {
            throw new Error(
                `window.wispApi.${method} is missing. Required methods: ${REQUIRED_WISP_API_METHODS.join(', ')}`,
            );
        }
    }
}
