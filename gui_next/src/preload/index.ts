import { contextBridge, ipcRenderer } from 'electron'

const FLASK_PORT = 5174

contextBridge.exposeInMainWorld('api', {
  flaskPort:       FLASK_PORT,
  flaskBase:       `http://127.0.0.1:${FLASK_PORT}`,
  platform:        process.platform,
  pickFolders:     (): Promise<string[]>      => ipcRenderer.invoke('dialog:pickFolders'),
  pickDir:         (): Promise<string | null> => ipcRenderer.invoke('dialog:pickDir'),
  pickFile:        (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }): Promise<string | null> => ipcRenderer.invoke('dialog:pickFile', opts),
  openPath:        (path: string): Promise<string> => ipcRenderer.invoke('shell:openPath', path),
  saveFile:        (content: string, filename: string): Promise<boolean> => ipcRenderer.invoke('dialog:saveFile', content, filename),
  printDossierPdf: (url: string, filename: string): Promise<boolean> => ipcRenderer.invoke('dossier:printPdf', url, filename),
  pickAndReadFile:  (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }): Promise<string | null> => ipcRenderer.invoke('dialog:pickAndReadFile', opts),
  pickAndReadFiles: (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }): Promise<{ path: string; content: string }[]> => ipcRenderer.invoke('dialog:pickAndReadFiles', opts),

  // Folders sent in from the file manager (tools/nemo). consumePipelineFolders()
  // returns the batches that landed before the renderer mounted; onPipelineFolders()
  // receives every later one. Returns an unsubscribe fn.
  consumePipelineFolders: (): Promise<string[]> => ipcRenderer.invoke('pipeline:consumePending'),
  onPipelineFolders: (cb: (paths: string[]) => void): (() => void) => {
    const listener = (_e: unknown, paths: string[]): void => cb(paths)
    ipcRenderer.on('pipeline:folders', listener)
    return () => { ipcRenderer.removeListener('pipeline:folders', listener) }
  },
})
