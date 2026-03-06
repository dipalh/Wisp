export const REQUIRED_WISP_API_METHODS = [
    'getUsername',
    'pickFolder',
    'scanFolder',
    'organizeFolder',
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
    'undoOrganize',
    'canUndoOrganize',
    'onUndoTriggered',
    'onUndoAvailable',
] as const;

export function assertWispApiContract(api: unknown): asserts api is Window['wispApi'] {
    if (!api || typeof api !== 'object') {
        throw new Error('window.wispApi is missing');
    }

    for (const method of REQUIRED_WISP_API_METHODS) {
        if (typeof (api as Record<string, unknown>)[method] !== 'function') {
            throw new Error(`window.wispApi.${method} is missing`);
        }
    }
}
