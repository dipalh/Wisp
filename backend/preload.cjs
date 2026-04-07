const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('wispApi', {
  getUsername: () => ipcRenderer.sendSync('app:getUsername'),
  pickFolder: () => ipcRenderer.invoke('folder:pick'),
  syncRoots: (roots) => ipcRenderer.invoke('roots:sync', roots),
  scanFolder: (folderPath) => ipcRenderer.invoke('folder:scan', folderPath),
  organizeGetProposals: (payload) => ipcRenderer.invoke('organize:getProposals', payload),
  organizeAcceptProposal: (proposalId, mappings) => ipcRenderer.invoke('organize:acceptProposal', proposalId, mappings),
  organizeApplyBatch: (batchId) => ipcRenderer.invoke('organize:applyBatch', batchId),
  organizeUndoBatch: (batchId) => ipcRenderer.invoke('organize:undoBatch', batchId),
  organizeRegisterUndoBatch: (payload) => ipcRenderer.invoke('organize:registerUndoBatch', payload),
  organizeClearUndoBatch: () => ipcRenderer.invoke('organize:clearUndoBatch'),
  tagFiles: (payload) => ipcRenderer.invoke('files:tag', payload),
  suggestDelete: (folderPath) => ipcRenderer.invoke('files:suggestDelete', folderPath),
  trashPath: (targetPath) => ipcRenderer.invoke('files:trash', targetPath),
  readFileBase64: (filePath) => ipcRenderer.invoke('file:readBase64', filePath),
  pickFileForOcr: () => ipcRenderer.invoke('file:pickForOcr'),
  extractText: (filePath) => ipcRenderer.invoke('ocr:extract', filePath),
  extractTextFromBuffer: (base64, filename) => ipcRenderer.invoke('ocr:extractBuffer', base64, filename),
  transcribeFile:        (filePath)           => ipcRenderer.invoke('transcribe:file', filePath),
  speakText:             (text, voiceId)      => ipcRenderer.invoke('tts:speak', text, voiceId),
  getVoices:             ()                   => ipcRenderer.invoke('tts:getVoices'),
  showInFolder:  (filePath)             => ipcRenderer.invoke('shell:showInFolder', filePath),
  openPath:      (filePath)             => ipcRenderer.invoke('shell:openPath', filePath),
  askAssistant:  (query, k, autoDeepen) => ipcRenderer.invoke('assistant:ask', query, k, autoDeepen),
  startScanJob: (folders) => ipcRenderer.invoke('jobs:startScan', folders),
  pollJob: (jobId) => ipcRenderer.invoke('jobs:poll', jobId),
  getIndexedFiles: (jobId) => ipcRenderer.invoke('jobs:indexedFiles', jobId),
  openFile: (filePath) => ipcRenderer.invoke('file:open', filePath),
  searchMemory: (query, opts) => ipcRenderer.invoke('memory:search', query, opts),

  // ── Undo support ──────────────────────────────────────────────────────
  /** Register a callback for when Cmd+Z / Edit > Undo is pressed and our undo stack has entries */
  onUndoTriggered: (callback) => {
    const handler = () => callback();
    ipcRenderer.on('undo:trigger', handler);
    return () => ipcRenderer.removeListener('undo:trigger', handler);
  },
  /** Register a callback for when undo availability changes (after organize or undo) */
  onUndoAvailable: (callback) => {
    const handler = (_, data) => callback(data);
    ipcRenderer.on('undo:available', handler);
    return () => ipcRenderer.removeListener('undo:available', handler);
  },
});
