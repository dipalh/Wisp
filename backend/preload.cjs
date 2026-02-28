const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('wispApi', {
  pickFolder: () => ipcRenderer.invoke('folder:pick'),
  scanFolder: (folderPath) => ipcRenderer.invoke('folder:scan', folderPath),
  organizeFolder: (folderPath) => ipcRenderer.invoke('folder:organize', folderPath),
  tagFiles: (payload) => ipcRenderer.invoke('files:tag', payload),
  suggestDelete: (folderPath) => ipcRenderer.invoke('files:suggestDelete', folderPath),
  trashPath: (targetPath) => ipcRenderer.invoke('files:trash', targetPath)
});
