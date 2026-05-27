/// <reference types="vite/client" />

interface Window {
  api: {
    flaskPort:   number
    flaskBase:   string
    pickFolders: () => Promise<string[]>
    pickDir:     () => Promise<string | null>
    openPath:    (path: string) => Promise<string>
  }
}
