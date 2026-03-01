const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('wispApi', {
  pickFolder: () => ipcRenderer.invoke('folder:pick'),
  scanFolder: (folderPath) => ipcRenderer.invoke('folder:scan', folderPath),
  organizeFolder: (folderPath) => ipcRenderer.invoke('folder:organize', folderPath),
  tagFiles: (payload) => ipcRenderer.invoke('files:tag', payload),
  suggestDelete: (folderPath) => ipcRenderer.invoke('files:suggestDelete', folderPath),
  trashPath:      (targetPath) => ipcRenderer.invoke('files:trash', targetPath),
  readFileBase64:       (filePath)           => ipcRenderer.invoke('file:readBase64', filePath),
  pickFileForOcr:       ()                   => ipcRenderer.invoke('file:pickForOcr'),
  extractText:          (filePath)           => ipcRenderer.invoke('ocr:extract', filePath),
  extractTextFromBuffer:(base64, filename)   => ipcRenderer.invoke('ocr:extractBuffer', base64, filename),
  transcribeFile:       (filePath)           => ipcRenderer.invoke('transcribe:file', filePath),
  speakText:            (text)               => ipcRenderer.invoke('tts:speak', text),
});
