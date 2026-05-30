import { app, BrowserWindow, shell, ipcMain, dialog } from 'electron'
import { join } from 'path'
import { spawn, ChildProcess } from 'child_process'
import { createConnection } from 'net'
import { writeFile, readFile } from 'fs/promises'

const FLASK_PORT = 5174
let backendProc: ChildProcess | null = null

function portOpen(port: number): Promise<boolean> {
  return new Promise(resolve => {
    const s = createConnection({ host: '127.0.0.1', port }, () => { s.destroy(); resolve(true) })
    s.on('error', () => resolve(false))
    s.setTimeout(300, () => { s.destroy(); resolve(false) })
  })
}

async function waitForPort(port: number, tries = 40, intervalMs = 250): Promise<boolean> {
  for (let i = 0; i < tries; i++) {
    if (await portOpen(port)) return true
    await new Promise(r => setTimeout(r, intervalMs))
  }
  return false
}

async function ensureBackend(): Promise<void> {
  if (await portOpen(FLASK_PORT)) return

  let cmd: string
  let args: string[]
  let cwd: string

  if (app.isPackaged) {
    const backendBin = process.platform === 'win32' ? 'LosslessBobBackend.exe' : 'LosslessBobBackend'
    cmd = join(process.resourcesPath, 'backend', backendBin)
    args = []
    cwd = app.getPath('home')
  } else {
    // Dev: project root is one level above gui_next/
    const root = join(app.getAppPath(), '..')
    cmd = join(root, '.venv', 'bin', 'python3')
    args = [join(root, 'run_backend.py')]
    cwd = root
  }

  backendProc = spawn(cmd, args, { cwd, stdio: 'pipe' })
  backendProc.stdout?.on('data', (d: Buffer) => process.stdout.write(`[flask] ${d}`))
  backendProc.stderr?.on('data', (d: Buffer) => process.stderr.write(`[flask] ${d}`))
}

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1280,
    minHeight: 768,
    show: false,
    title: 'LosslessBob',
    backgroundColor: '#faf8f3',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
    }
  })

  win.on('ready-to-show', () => win.show())

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  if (process.env.ELECTRON_RENDERER_URL) {
    win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

ipcMain.handle('dialog:pickFolders', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: 'Select recording folders',
    properties: ['openDirectory', 'multiSelections'],
  })
  return canceled ? [] : filePaths
})

ipcMain.handle('dialog:pickDir', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: 'Select root directory to scan',
    properties: ['openDirectory'],
  })
  return canceled ? null : filePaths[0]
})

ipcMain.handle('shell:openPath', (_event, path: string) => shell.openPath(path))

ipcMain.handle('dialog:saveFile', async (_event, content: string, defaultFilename: string) => {
  const { canceled, filePath } = await dialog.showSaveDialog({
    title: 'Save file',
    defaultPath: defaultFilename,
  })
  if (canceled || !filePath) return false
  await writeFile(filePath, content, 'utf8')
  return true
})

ipcMain.handle('dialog:pickAndReadFile', async (_event, opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: opts?.title ?? 'Select file',
    properties: ['openFile'],
    filters: opts?.filters,
  })
  if (canceled || !filePaths[0]) return null
  return readFile(filePaths[0], 'utf8')
})

ipcMain.handle('dialog:pickFile', async (_event, opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: opts?.title ?? 'Select file',
    properties: ['openFile'],
    filters: opts?.filters,
  })
  return canceled ? null : filePaths[0]
})

ipcMain.handle('dialog:pickAndReadFiles', async (_event, opts?: { title?: string; filters?: { name: string; extensions: string[] }[] }) => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: opts?.title ?? 'Select files',
    properties: ['openFile', 'multiSelections'],
    filters: opts?.filters,
  })
  if (canceled || !filePaths.length) return []
  const results: { path: string; content: string }[] = []
  for (const fp of filePaths) {
    try {
      const content = await readFile(fp, 'utf8')
      results.push({ path: fp, content })
    } catch { /* skip unreadable */ }
  }
  return results
})

app.whenReady().then(async () => {
  await ensureBackend()
  await waitForPort(FLASK_PORT)
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('before-quit', () => {
  backendProc?.kill()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
