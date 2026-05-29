import { contextBridge, ipcRenderer } from 'electron'

const FLASK_PORT = 5174

contextBridge.exposeInMainWorld('api', {
  flaskPort:       FLASK_PORT,
  flaskBase:       `http://127.0.0.1:${FLASK_PORT}`,
  pickFolders:     (): Promise<string[]>      => ipcRenderer.invoke('dialog:pickFolders'),
  pickDir:         (): Promise<string | null> => ipcRenderer.invoke('dialog:pickDir'),
  pickFile:        (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }): Promise<string | null> => ipcRenderer.invoke('dialog:pickFile', opts),
  openPath:        (path: string): Promise<string> => ipcRenderer.invoke('shell:openPath', path),
  saveFile:        (content: string, filename: string): Promise<boolean> => ipcRenderer.invoke('dialog:saveFile', content, filename),
  pickAndReadFile:  (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }): Promise<string | null> => ipcRenderer.invoke('dialog:pickAndReadFile', opts),
  pickAndReadFiles: (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }): Promise<{ path: string; content: string }[]> => ipcRenderer.invoke('dialog:pickAndReadFiles', opts),
})
