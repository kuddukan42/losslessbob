import { contextBridge, ipcRenderer } from 'electron'

const FLASK_PORT = 5174

contextBridge.exposeInMainWorld('api', {
  flaskPort:   FLASK_PORT,
  flaskBase:   `http://127.0.0.1:${FLASK_PORT}`,
  pickFolders: (): Promise<string[]>      => ipcRenderer.invoke('dialog:pickFolders'),
  pickDir:     (): Promise<string | null> => ipcRenderer.invoke('dialog:pickDir'),
  openPath:    (path: string): Promise<string> => ipcRenderer.invoke('shell:openPath', path),
})
