// Shared navigation registry — the single source of truth for app screens.
//
// Both the sidebar (components/AppShell.tsx) and the command palette
// (components/CommandPalette.tsx) derive their screen lists from NAV_GROUPS.
// Add or remove a screen here and it changes in both places (spec DoD #3).
// Curator-gated groups (gatedGroup) render/appear only when curatorMode is on.

export type NavId =
  | 'home' | 'pipeline' | 'quicklookup'
  | 'library' | 'collection' | 'trading' | 'sharing' | 'search' | 'bootlegs' | 'tapematch' | 'songs' | 'gaps'
  | 'attachments' | 'spectrograms' | 'map'
  | 'scraper' | 'fingerprint' | 'setup' | 'mounts' | 'themes' | 'dbeditor'

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
      { id: 'gaps',       label: 'Gaps',          icon: 'gaps' },
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
      { id: 'themes',   label: 'Themes',    icon: 'themes' },
      { id: 'dbeditor', label: 'DB Editor', icon: 'dbeditor' },
    ],
  },
]

/** Resolve a nav id to its HashRouter pathname (home → '/', else '/<id>'). */
export function navPathForId(id: NavId | string): string {
  return id === 'home' ? '/' : `/${id}`
}
