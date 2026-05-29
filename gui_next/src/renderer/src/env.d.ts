/// <reference types="vite/client" />

interface Window {
  api: {
    flaskPort:       number
    flaskBase:       string
    pickFolders:     () => Promise<string[]>
    pickDir:         () => Promise<string | null>
    pickFile:        (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<string | null>
    openPath:        (path: string) => Promise<string>
    saveFile:        (content: string, filename: string) => Promise<boolean>
    pickAndReadFile:  (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<string | null>
    pickAndReadFiles: (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<{ path: string; content: string }[]>
  }
}
