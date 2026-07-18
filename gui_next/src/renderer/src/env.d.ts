/// <reference types="vite/client" />

/** App version string injected at build time from gui_next/package.json. */
declare const __APP_VERSION__: string

interface Window {
  api: {
    flaskPort:       number
    flaskBase:       string
    platform:        NodeJS.Platform
    pickFolders:     () => Promise<string[]>
    pickDir:         () => Promise<string | null>
    pickFile:        (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<string | null>
    openPath:        (path: string) => Promise<string>
    saveFile:        (content: string, filename: string) => Promise<boolean>
    printDossierPdf: (url: string, filename: string) => Promise<boolean>
    pickAndReadFile:  (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<string | null>
    pickAndReadFiles: (opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => Promise<{ path: string; content: string }[]>
  }
}
