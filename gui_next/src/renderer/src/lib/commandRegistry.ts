// Command palette registry — the extension point for the Ctrl+K palette.
//
// The palette (components/CommandPalette.tsx) renders whatever is registered
// here plus the two synthetic result kinds it computes on its own (Go-to-LB
// hits and live entry-search rows). This module is deliberately framework-free
// so any feature module can contribute commands without importing React.
//
// EXTENSION CONTRACT — how a future spec adds a palette action:
//   import { registerCommands } from '../lib/commandRegistry'
//   registerCommands([{
//     id: 'action.myThing', labelKey: 'palette.action.myThing',
//     section: 'actions', keywords: ['do', 'thing'],
//     run: ({ navigate, t }) => { ... },   // void → closes; Promise<string> → footer
//   }])
// Call it once at module load (top level of your feature module) and add the
// i18n keys to locales/en.json. No CommandPalette.tsx edit is required.
//
// Intended near-term consumers (SSE-backed actions land once each ships a home
// for their progress UI — see FABLE_ACTIVITY_CENTER.md D4):
//   • activity center  — pause/clear jobs, jump to the tray
//   • show dossier     — "export dossier for LB-N"
//   • gaps view        — "open gaps for <year>"

import type { NavigateFunction } from 'react-router-dom'
import { NAV_GROUPS, navPathForId } from './navigation'

/** Context handed to a command's run(). */
export interface CommandRunContext {
  navigate: NavigateFunction
  /** i18next translator, so run() can compose localized footer strings. */
  t: (key: string, opts?: Record<string, unknown>) => string
}

export interface PaletteCommand {
  /** Stable id, e.g. 'nav.library', 'action.checkUpdate'. */
  id: string
  /** i18n key for the visible label. */
  labelKey: string
  /** Extra english match terms (not translated). */
  keywords?: string[]
  section: 'screens' | 'actions' | 'entries'
  /** Only surfaced when curatorMode is on (sidebar parity). */
  curatorOnly?: boolean
  /**
   * Execute the command. Return nothing to just close the palette, or a
   * Promise<string> to keep the palette open and show the resolved string in
   * the footer (e.g. an update-check outcome).
   */
  run: (ctx: CommandRunContext) => void | Promise<string>
}

const registry: PaletteCommand[] = []
const seen = new Set<string>()

/** Register commands (idempotent per id — later duplicates are ignored). */
export function registerCommands(cmds: PaletteCommand[]): void {
  for (const cmd of cmds) {
    if (seen.has(cmd.id)) continue
    seen.add(cmd.id)
    registry.push(cmd)
  }
}

/** All registered commands, in registration order. */
export function getCommands(): PaletteCommand[] {
  return registry
}

// ── Built-in commands ────────────────────────────────────────────────────────

/** One navigation command per NAV_GROUPS screen (shares the sidebar registry). */
function navCommands(): PaletteCommand[] {
  const cmds: PaletteCommand[] = []
  for (const group of NAV_GROUPS) {
    for (const item of group.items) {
      cmds.push({
        id: `nav.${item.id}`,
        labelKey: `appShell.nav.${item.id}`,
        keywords: [item.label],
        section: 'screens',
        curatorOnly: group.gatedGroup === true,
        run: ({ navigate }) => navigate(navPathForId(item.id)),
      })
    }
  }
  return cmds
}

/** Live "check for update" — synchronous discover endpoint, footer outcome. */
const checkUpdateCommand: PaletteCommand = {
  id: 'action.checkUpdate',
  labelKey: 'palette.action.checkUpdate',
  keywords: ['update', 'release', 'flat file', 'version'],
  section: 'actions',
  run: async ({ t }) => {
    try {
      const res = await fetch(`${window.api.flaskBase}/api/flat_file/discover`)
      const data = await res.json()
      if (data.error || data.available === null) {
        return t('palette.update.error', { error: data.error ?? 'unknown' })
      }
      if (data.available) {
        const name = data.current_release?.zip_filename
        return name
          ? t('palette.update.available', { name })
          : t('palette.update.availableGeneric')
      }
      return t('palette.update.upToDate')
    } catch (err) {
      return t('palette.update.error', { error: String(err) })
    }
  },
}

registerCommands([...navCommands(), checkUpdateCommand])
