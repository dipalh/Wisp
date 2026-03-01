const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('wispApi', {
  pickFolder: () => ipcRenderer.invoke('folder:pick'),
  scanFolder: (folderPath) => ipcRenderer.invoke('folder:scan', folderPath),
  organizeFolder: (folderPath) => ipcRenderer.invoke('folder:organize', folderPath),
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
});
