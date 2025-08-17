const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  getDrives: () => ipcRenderer.invoke('get-drives'),
  readFolder: (path) => ipcRenderer.invoke('read-folder', path),
  sendFilePath: (path) => ipcRenderer.send('file-selected', path),
  selectFolder: () => ipcRenderer.invoke('dialog:openDirectory'),
  openDirectory: () => ipcRenderer.invoke('dialog:openDirectory'),
  openE01File: () => ipcRenderer.invoke('dialog:openE01File'),
  startRecovery: (e01Path) => ipcRenderer.invoke('start-recovery', e01Path),
  clearCache: () => ipcRenderer.invoke('clear-cache'),

  onDrivesUpdated: (callback) => {
    const listener = (_event, data) => callback(data);
    ipcRenderer.on('drives-updated', listener);
    return () => ipcRenderer.removeListener('drives-updated', listener);
  },

  // 진행률 이벤트 핸들러 등록
  onProgress: (callback) => {
    const listener = (_event, data) => callback(data);
    ipcRenderer.on('recovery-progress', listener);
    return () => ipcRenderer.removeListener('recovery-progress', listener);
  },

  // 완료 이벤트 핸들러 등록
  onDone: (callback) => {
    const listener = () => callback();
    ipcRenderer.on('recovery-done', listener);
    return () => ipcRenderer.removeListener('recovery-done', listener);
  },

  // 분석 완료 후 받은 temp 폴더 경로 구독
  onAnalysisPath: (callback) => {
    const listener = (_event, path) => callback(path);
    ipcRenderer.on('analysis-path', listener);
    return () => ipcRenderer.removeListener('analysis-path', listener);
  },

  onResults: (callback) => {
    const listener = (_e, data) => callback(data);
    ipcRenderer.on('recovery-results', listener);
    return () => ipcRenderer.removeListener('results', listener);
  },

  // 다운로드 기능 추가
  runDownload: (args) => ipcRenderer.invoke('run-download', args),
  onDownloadLog: (cb) => {
    const l = (_e, line) => cb(line);
    ipcRenderer.on('download-log', l);
    return () => ipcRenderer.removeListener('download-log', l);
  },
  onDownloadError: (cb) => {
    const l = (_e, err) => cb(err);
    ipcRenderer.on('download-error', l);
    return () => ipcRenderer.removeListener('download-error', l);
  },
});