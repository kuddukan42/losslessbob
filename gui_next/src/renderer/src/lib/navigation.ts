// Shared navigation registry — the single source of truth for app screens.
//
// Both the sidebar (components/AppShell.tsx) and the command palette
// (components/CommandPalette.tsx) derive their screen lists from NAV_GROUPS.
// Add or remove a screen here and it changes in both places (spec DoD #3).
// Curator-gated groups (gatedGroup) render/appear only when curatorMode is on.

export type NavId =
  | 'home' | 'pipeline' | 'scanner' | 'quicklookup'
  | 'library' | 'collection' | 'trading' | 'sharing' | 'search' | 'bootlegs' | 'tapematch' | 'songs' | 'timeline'
  | 'attachments' | 'spectrograms' | 'map'
  | 'scraper' | 'fingerprint' | 'setup' | 'mounts' | 'fileintegrity' | 'themes' | 'dbeditor'

export type NavGroupLabel = 'Ingest' | 'Library' | 'Assets' | 'Curator' | 'Settings'

export const NAV_GROUP_KEYS: Record<NavGroupLabel, `appShell.nav.${Lowercase<NavGroupLabel>}`> = {
  Ingest:   'appShell.nav.ingest',
  Library:  'appShell.nav.library',
  Assets:   'appShell.nav.assets',
  Curator:  'appShell.nav.curator',
  Settings: 'appShell.nav.settings',
}

export interface NavItem {
  id: NavId
  label: string
  icon: string
  featured?: boolean
  count?: number
}

// Pipeline refresh Phase 4: which nav item wears which human-review-queue
// count (backend/queues.py). Only `gate` queues appear here — the TapeMatch
// date backlog is open-ended by nature and a badge that never reaches zero
// teaches the user to ignore every badge (spec §2 decision 2). `xref_filesets`
// is excluded for the opposite reason: it is the one queue this install cannot
// resolve, so its count could sit non-zero forever (decision 7).
export const NAV_QUEUE_BADGES: Record<string, NavId> = {
  taper_conflicts: 'library',
  fingerprint_suggestions: 'fingerprint',
}

export interface NavGroup {
  label: NavGroupLabel | null
  gatedGroup?: boolean
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: null,
    items: [{ id: 'home', label: 'Home', icon: 'home' }],
  },
  {
    label: 'Ingest',
    items: [
      { id: 'pipeline', label: 'Pipeline', icon: 'pipeline' },
      { id: 'scanner',  label: 'Disk Scanner', icon: 'folderPlus' },
    ],
  },
  {
    label: 'Library',
    items: [
      { id: 'library',    label: 'Library',       icon: 'library', featured: true },
      { id: 'collection', label: 'My Collection', icon: 'collection' },
      { id: 'trading',    label: 'Trading',       icon: 'trading' },
      { id: 'sharing',    label: 'Sharing',       icon: 'share' },
      { id: 'search',     label: 'Search',        icon: 'search' },
      { id: 'bootlegs',   label: 'Bootlegs',      icon: 'bootlegs' },
      { id: 'tapematch',  label: 'TapeMatch',     icon: 'tapematch' },
      { id: 'songs',      label: 'Songs',         icon: 'songs' },
      { id: 'timeline',   label: 'Timeline',      icon: 'timeline' },
    ],
  },
  {
    label: 'Assets',
    items: [
      { id: 'attachments',  label: 'Attachments',  icon: 'attachments' },
      { id: 'spectrograms', label: 'Spectrograms', icon: 'spectro' },
      { id: 'map',          label: 'Map',          icon: 'map' },
    ],
  },
  {
    label: 'Curator',
    gatedGroup: true,
    items: [
      { id: 'scraper',     label: 'Scraper',     icon: 'scraper' },
      { id: 'fingerprint', label: 'Fingerprint', icon: 'fingerprint' },
    ],
  },
  {
    label: 'Settings',
    items: [
      { id: 'setup',    label: 'Setup',     icon: 'setup' },
      { id: 'mounts',   label: 'Mounts',    icon: 'mounts' },
      { id: 'fileintegrity', label: 'File Integrity', icon: 'shield' },
      { id: 'themes',   label: 'Themes',    icon: 'themes' },
      { id: 'dbeditor', label: 'DB Editor', icon: 'dbeditor' },
    ],
  },
]

/** Resolve a nav id to its HashRouter pathname (home → '/', else '/<id>'). */
export function navPathForId(id: NavId | string): string {
  return id === 'home' ? '/' : `/${id}`
}
