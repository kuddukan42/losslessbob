import { app, BrowserWindow, shell, ipcMain, dialog } from 'electron'
import { join } from 'path'
import { tmpdir } from 'os'
import { spawn, ChildProcess, execSync } from 'child_process'
import { createConnection } from 'net'
import { writeFile, readFile, unlink } from 'fs/promises'

const FLASK_PORT = 5174
const PID_FILE = join(tmpdir(), 'losslessbob_backend.pid')
let backendProc: ChildProcess | null = null

// On native Wayland (GNOME) the taskbar/dock icon is resolved ONLY by matching the
// window's Wayland app_id to an installed .desktop file whose basename equals that
// app_id — the BrowserWindow `icon` option and .desktop StartupWMClass are ignored
// there. In dev the app_id is "losslessbob-next" (Electron derives it from the
// package.json "name"), so the dev-helper resources/losslessbob-next.desktop is named
// to match. The packaged app uses its electron-builder-generated .desktop instead.

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

// Kills pid and its whole descendant tree (e.g. ffmpeg/sox/shntool subprocesses the
// backend spawns for checksum/verify operations) — a plain kill()/TerminateProcess on
// Windows only kills the named pid and leaves those children running as orphans.
function killProcessTree(pid: number): void {
  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' })
    } else {
      process.kill(pid, 'SIGTERM')
    }
  } catch { /* already dead */ }
}

async function killStalePid(): Promise<void> {
  try {
    const raw = await readFile(PID_FILE, 'utf8')
    const pid = parseInt(raw.trim(), 10)
    if (pid) {
      killProcessTree(pid)
      await new Promise(r => setTimeout(r, 400))
    }
    await unlink(PID_FILE).catch(() => {})
  } catch { /* no PID file — nothing to kill */ }
}

async function killPortProcess(port: number): Promise<void> {
  try {
    if (process.platform === 'win32') {
      const out = execSync(`netstat -ano | findstr LISTENING | findstr :${port}`, { encoding: 'utf8' })
      const pids = [...new Set(out.trim().split('\n')
        .map(l => l.trim().split(/\s+/).pop())
        .filter((p): p is string => !!p && /^\d+$/.test(p)))]
      pids.forEach(pid => { try { execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' }) } catch {} })
    } else {
      const out = execSync(`lsof -ti :${port}`, { encoding: 'utf8' }).trim()
      if (out) {
        out.split('\n').forEach(pid => {
          const n = parseInt(pid.trim(), 10)
          if (n) { try { process.kill(n, 'SIGTERM') } catch {} }
        })
        await new Promise(r => setTimeout(r, 400))
      }
    }
  } catch { /* nothing on port — nothing to do */ }
}

async function ensureBackend(): Promise<void> {
  // Kill any backend left over from a previous session or a hot-reload restart.
  // Two-pass kill: PID file first (fast path), then port scan (catches manually
  // started backends or cases where the PID file was never written).
  await killStalePid()
  await killPortProcess(FLASK_PORT)

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
    cmd = process.platform === 'win32'
      ? join(root, '.venv', 'Scripts', 'python.exe')
      : join(root, '.venv', 'bin', 'python3')
    args = [join(root, 'run_backend.py')]
    cwd = root
  }

  backendProc = spawn(cmd, args, { cwd, stdio: 'pipe' })
  backendProc.stdout?.on('data', (d: Buffer) => process.stdout.write(`[flask] ${d}`))
  backendProc.stderr?.on('data', (d: Buffer) => process.stderr.write(`[flask] ${d}`))

  if (backendProc.pid) {
    writeFile(PID_FILE, String(backendProc.pid), 'utf8').catch(() => {})
  }
}

function createWindow(): void {
  const iconPath = app.isPackaged
    ? join(process.resourcesPath, 'icon.png')
    : join(app.getAppPath(), 'resources/icon.png')

  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1280,
    minHeight: 768,
    show: false,
    title: 'LosslessBob',
    backgroundColor: '#faf8f3',
    icon: iconPath,
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
  if (backendProc?.pid) killProcessTree(backendProc.pid)
  backendProc = null
  unlink(PID_FILE).catch(() => {})
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
