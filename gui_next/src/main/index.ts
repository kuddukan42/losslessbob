import { app, BrowserWindow, shell, ipcMain, dialog, clipboard } from 'electron'
import { join } from 'path'
import { tmpdir, homedir } from 'os'
import { spawn, ChildProcess, execSync } from 'child_process'
import { createConnection } from 'net'
import { watch } from 'fs'
import { writeFile, readFile, unlink, mkdir, readdir } from 'fs/promises'

const FLASK_PORT = 5174
const PID_FILE = join(tmpdir(), 'losslessbob_backend.pid')
let backendProc: ChildProcess | null = null

// ── Pipeline inbox (file-manager "Send to LosslessBob pipeline" hand-off) ─────
//
// tools/nemo/lb-send-to-pipeline.sh drops one newline-separated path list per
// invocation into PIPELINE_INBOX, then launches the app if GUI_PID_FILE names no
// live process. A drop file — not argv or a single-instance lock — is the transport
// because in dev the app is started via `npm run dev`, whose argv the launcher owns;
// the inbox is identical for dev and packaged builds and survives a cold start (the
// drop is written before the app exists and drained once the renderer mounts).
const LB_STATE_DIR   = join(homedir(), '.local', 'share', 'losslessbob')
const PIPELINE_INBOX = join(LB_STATE_DIR, 'pipeline-inbox')
const GUI_PID_FILE   = join(LB_STATE_DIR, 'gui.pid')

let mainWindow: BrowserWindow | null = null
let rendererReady = false
let pendingFolders: string[] = []

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
      // The backend is spawned detached (its own process group, pgid === pid),
      // so a negative-pid kill signals the whole group. Fall back to a plain
      // kill for PIDs that aren't group leaders (e.g. a manually started backend).
      try {
        process.kill(-pid, 'SIGTERM')
      } catch {
        process.kill(pid, 'SIGTERM')
      }
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
          if (n) killProcessTree(n)
        })
        await new Promise(r => setTimeout(r, 400))
      }
    }
  } catch { /* nothing on port — nothing to do */ }
}

async function ensureBackend(): Promise<void> {
  // Dev-only escape hatch for the verification drivers: they attach to a backend
  // started by hand, so the kill-and-respawn below would murder it mid-session.
  // Packaged builds ignore the var — a shipped app must always own its backend.
  if (process.env.LB_NO_BACKEND_SPAWN === '1' && !app.isPackaged) {
    console.log(`[main] LB_NO_BACKEND_SPAWN=1 — assuming backend already on :${FLASK_PORT}`)
    return
  }

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

  // detached on POSIX puts the backend in its own process group so
  // killProcessTree can reap its ffmpeg/sox/shntool children via group kill.
  backendProc = spawn(cmd, args, { cwd, stdio: 'pipe', detached: process.platform !== 'win32' })
  backendProc.stdout?.on('data', (d: Buffer) => process.stdout.write(`[flask] ${d}`))
  backendProc.stderr?.on('data', (d: Buffer) => process.stderr.write(`[flask] ${d}`))

  if (backendProc.pid) {
    writeFile(PID_FILE, String(backendProc.pid), 'utf8').catch(() => {})
  }
}

/**
 * Hand a batch of folder paths to the renderer's pipeline queue.
 *
 * Buffers until the renderer has called `pipeline:consumePending`, so a batch
 * dropped before (or during) app start is not lost.
 */
function deliverFolders(paths: string[]): void {
  if (!paths.length) return
  if (mainWindow && rendererReady) {
    mainWindow.webContents.send('pipeline:folders', paths)
  } else {
    pendingFolders = [...new Set([...pendingFolders, ...paths])]
  }
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  }
}

/** Read every drop file in the inbox, delete each one, and deliver its paths. */
async function drainPipelineInbox(): Promise<void> {
  let names: string[]
  try {
    names = (await readdir(PIPELINE_INBOX)).filter(n => n.endsWith('.txt')).sort()
  } catch {
    return // inbox not created yet
  }
  const paths: string[] = []
  for (const name of names) {
    const file = join(PIPELINE_INBOX, name)
    try {
      const raw = await readFile(file, 'utf8')
      paths.push(...raw.split('\n').map(l => l.trim()).filter(Boolean))
    } catch { /* unreadable — still unlink below so it can't wedge the inbox */ }
    await unlink(file).catch(() => {})
  }
  deliverFolders([...new Set(paths)])
}

/** Create the inbox dir, drain anything already waiting, and watch for new drops. */
async function startPipelineInbox(): Promise<void> {
  await mkdir(PIPELINE_INBOX, { recursive: true }).catch(() => {})
  await drainPipelineInbox()
  let timer: NodeJS.Timeout | null = null
  try {
    watch(PIPELINE_INBOX, () => {
      // Debounced: one drop can fire several rename/change events, and the
      // sender writes the file before we should read it.
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => { void drainPipelineInbox() }, 150)
    })
  } catch (err) {
    console.error('[main] pipeline inbox watch failed:', err)
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

  mainWindow = win
  win.on('closed', () => { if (mainWindow === win) mainWindow = null })
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

// Clipboard writes go through the main process rather than the renderer's
// navigator.clipboard: in a packaged build the renderer is a file:// document,
// where the async Clipboard API rejects unless the document holds focus — which
// it does not while a native menu or dialog is closing. Electron's clipboard
// module has no such precondition, so a "copy the forum links" action cannot
// silently no-op.
ipcMain.handle('clipboard:write', (_event, text: string) => {
  clipboard.writeText(String(text ?? ''))
  return true
})

// Called once by the renderer on mount: marks it ready for pushed batches and
// returns anything that arrived before it could listen.
ipcMain.handle('pipeline:consumePending', () => {
  rendererReady = true
  const paths = pendingFolders
  pendingFolders = []
  return paths
})

ipcMain.handle('dialog:saveFile', async (_event, content: string, defaultFilename: string) => {
  const { canceled, filePath } = await dialog.showSaveDialog({
    title: 'Save file',
    defaultPath: defaultFilename,
  })
  if (canceled || !filePath) return false
  await writeFile(filePath, content, 'utf8')
  return true
})

// Show dossier PDF export (FABLE_SHOW_DOSSIER.md D4): a hidden BrowserWindow
// loads the backend's own /api/dossier/html render and prints it — no Python
// PDF dependency, and the PDF can never drift from the HTML twin since it's
// the exact same served document.
ipcMain.handle('dossier:printPdf', async (_event, url: string, defaultFilename: string) => {
  const { canceled, filePath } = await dialog.showSaveDialog({
    title: 'Save dossier PDF',
    defaultPath: defaultFilename,
    filters: [{ name: 'PDF', extensions: ['pdf'] }],
  })
  if (canceled || !filePath) return false

  const printWin = new BrowserWindow({ show: false, webPreferences: { sandbox: false } })
  try {
    await printWin.loadURL(url)
    const pdfBuffer = await printWin.webContents.printToPDF({})
    await writeFile(filePath, pdfBuffer)
    return true
  } finally {
    printWin.destroy()
  }
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
  await mkdir(LB_STATE_DIR, { recursive: true }).catch(() => {})
  // The sender script checks this PID to decide whether to launch the app.
  await writeFile(GUI_PID_FILE, String(process.pid), 'utf8').catch(() => {})
  await startPipelineInbox()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('before-quit', () => {
  if (backendProc?.pid) killProcessTree(backendProc.pid)
  backendProc = null
  unlink(PID_FILE).catch(() => {})
  unlink(GUI_PID_FILE).catch(() => {})
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
