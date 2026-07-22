// Ctrl+K command palette — one fuzzy box that jumps to a screen, an LB number,
// a date/venue entry, or runs a registered action. Mounted once in AppShell.
//
// Query interpretation is ranked top-down on each keystroke (spec D3):
//   1. LB pattern    → synthetic "Go to LB-N" top hit
//   2. command fuzzy → screens + actions from the shared registry
//   3. entry search  → debounced /api/search, silently degrades on error
//
// Adds NO commands of its own — everything comes from lib/commandRegistry.ts,
// which is the extension point future specs hook into.

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useSettingsStore } from '../store'
import { getCommands, type PaletteCommand } from '../lib/commandRegistry'
import { fuzzyScore } from '../lib/fuzzyMatch'

const BASE = window.api.flaskBase
const LB_PATTERN = /^(?:lb[-\s]?)?0*(\d{1,5})$/i
const ENTRY_LIMIT = 8
const SEARCH_DEBOUNCE_MS = 200

interface EntryRow {
  lb: number
  dateStr: string
  location: string
}

type ResultRow =
  | { kind: 'lb'; n: number }
  | { kind: 'command'; command: PaletteCommand; label: string }
  | { kind: 'entry'; entry: EntryRow }

interface Section {
  key: 'top' | 'screens' | 'actions' | 'entries'
  rows: ResultRow[]
}

export function CommandPalette(): React.ReactElement | null {
  const navigate = useNavigate()
  const { t } = useTranslation()
  // Loose view of t() for runtime-computed keys (nav labels come from the shared
  // registry as plain strings; the typed t() only accepts literal key unions).
  const tDyn = t as unknown as (key: string, opts?: Record<string, unknown>) => string
  const curatorMode = useSettingsStore((s) => s.curatorMode)

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const [entries, setEntries] = useState<EntryRow[]>([])
  const [footer, setFooter] = useState<string | null>(null)

  const inputRef = useRef<HTMLInputElement>(null)
  const restoreFocusRef = useRef<HTMLElement | null>(null)
  const searchReqRef = useRef(0)

  // ── Global Ctrl/Cmd+K toggle (capture, works regardless of focus) ──────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [])

  // ── Open/close side effects: focus capture/restore + scroll lock ───────────
  useEffect(() => {
    if (open) {
      restoreFocusRef.current = document.activeElement as HTMLElement | null
      setQuery('')
      setHighlight(0)
      setEntries([])
      setFooter(null)
      const prevOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      // Focus the input after mount.
      requestAnimationFrame(() => inputRef.current?.focus())
      return () => {
        document.body.style.overflow = prevOverflow
      }
    }
    return undefined
  }, [open])

  // ── Reset highlight + footer whenever the query changes ────────────────────
  useEffect(() => {
    setHighlight(0)
    setFooter(null)
  }, [query])

  // ── Section 3: debounced entry search with stale-response guard ────────────
  useEffect(() => {
    if (!open) return
    const q = query.trim()
    if (q.length < 2) {
      setEntries([])
      return
    }
    const reqId = ++searchReqRef.current
    const handle = setTimeout(() => {
      fetch(`${BASE}/api/search?q=${encodeURIComponent(q)}&field=all`)
        .then((r) => r.json())
        .then((data: any[]) => {
          if (reqId !== searchReqRef.current) return // stale
          if (!Array.isArray(data)) {
            setEntries([])
            return
          }
          setEntries(
            data.slice(0, ENTRY_LIMIT).map((d) => ({
              lb: d.lb_number as number,
              dateStr: (d.date_str ?? '') as string,
              location: (d.location ?? '') as string,
            })),
          )
        })
        .catch(() => {
          if (reqId === searchReqRef.current) setEntries([]) // degrade silently
        })
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(handle)
  }, [open, query])

  // ── Build ranked, grouped results (sections 1–3) ───────────────────────────
  const sections = useMemo<Section[]>(() => {
    const q = query.trim()
    const out: Section[] = []

    // 1. LB pattern → top hit.
    const m = q.match(LB_PATTERN)
    if (m) {
      const n = parseInt(m[1], 10)
      out.push({ key: 'top', rows: [{ kind: 'lb', n }] })
    }

    // 2. Command fuzzy match (screens + actions), gated by curatorMode.
    const commands = getCommands().filter((c) => !c.curatorOnly || curatorMode)
    const scoreCommand = (c: PaletteCommand): number | null => {
      const label = tDyn(c.labelKey)
      const candidates = [label, ...(c.keywords ?? [])]
      let best: number | null = null
      for (const cand of candidates) {
        const s = fuzzyScore(q, cand)
        if (s !== null && (best === null || s > best)) best = s
      }
      return best
    }

    const scored = commands
      .map((c) => ({ c, label: tDyn(c.labelKey), score: q ? scoreCommand(c) : 0 }))
      .filter((x) => x.score !== null) as { c: PaletteCommand; label: string; score: number }[]
    // Sort by score desc; stable order otherwise preserves registration order.
    if (q) scored.sort((a, b) => b.score - a.score)

    const screens = scored.filter((x) => x.c.section === 'screens')
    const actions = scored.filter((x) => x.c.section === 'actions')
    if (screens.length) {
      out.push({
        key: 'screens',
        rows: screens.map((x) => ({ kind: 'command', command: x.c, label: x.label })),
      })
    }
    if (actions.length) {
      out.push({
        key: 'actions',
        rows: actions.map((x) => ({ kind: 'command', command: x.c, label: x.label })),
      })
    }

    // 3. Entry search rows.
    if (entries.length) {
      out.push({
        key: 'entries',
        rows: entries.map((e) => ({ kind: 'entry', entry: e })),
      })
    }

    return out
  }, [query, curatorMode, entries, t])

  // Flatten for keyboard navigation.
  const flatRows = useMemo(() => sections.flatMap((s) => s.rows), [sections])

  // Keep highlight in range as results shrink.
  useEffect(() => {
    if (highlight >= flatRows.length && flatRows.length > 0) {
      setHighlight(flatRows.length - 1)
    }
  }, [flatRows.length, highlight])

  function close(): void {
    setOpen(false)
    const el = restoreFocusRef.current
    if (el && typeof el.focus === 'function') requestAnimationFrame(() => el.focus())
  }

  function runRow(row: ResultRow): void {
    if (row.kind === 'lb') {
      navigate(`/library?lb=${row.n}`)
      close()
      return
    }
    if (row.kind === 'entry') {
      navigate(`/library?lb=${row.entry.lb}`)
      close()
      return
    }
    // Command.
    const result = row.command.run({ navigate, t: tDyn })
    if (result instanceof Promise) {
      setFooter(t('palette.update.checking'))
      result
        .then((msg) => setFooter(msg))
        .catch((err) => setFooter(String(err)))
      // Stay open so the footer outcome is visible.
    } else {
      close()
    }
  }

  function onKeyDown(e: React.KeyboardEvent): void {
    if (e.key === 'Escape') {
      e.preventDefault()
      close()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (flatRows.length) setHighlight((h) => (h + 1) % flatRows.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (flatRows.length) setHighlight((h) => (h - 1 + flatRows.length) % flatRows.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const row = flatRows[highlight]
      if (row) runRow(row)
    }
  }

  if (!open) return null

  let flatIndex = -1

  return (
    <div
      role="dialog"
      aria-modal="true"
      onKeyDown={onKeyDown}
      onClick={(e) => {
        if (e.target === e.currentTarget) close()
      }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9500,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '12vh',
        background: 'rgba(0,0,0,0.42)',
        backdropFilter: 'blur(2px)',
      }}
    >
      <div
        style={{
          width: 620,
          maxWidth: '92vw',
          maxHeight: '70vh',
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--lbb-surface)',
          border: '1px solid var(--lbb-border2)',
          borderRadius: 12,
          boxShadow: '0 24px 70px rgba(0,0,0,0.55)',
          overflow: 'hidden',
          fontFamily: 'var(--lbb-font)',
        }}
      >
        {/* Input */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '12px 16px',
            borderBottom: '1px solid var(--lbb-border)',
          }}
        >
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('palette.placeholder')}
            spellCheck={false}
            style={{
              flex: 1,
              border: 'none',
              outline: 'none',
              background: 'transparent',
              color: 'var(--lbb-fg)',
              fontSize: 'var(--lbb-fs-14)',
              fontFamily: 'inherit',
            }}
          />
          <kbd
            style={{
              fontSize: 'var(--lbb-fs-10-5)',
              color: 'var(--lbb-fg3)',
              border: '1px solid var(--lbb-border2)',
              borderRadius: 4,
              padding: '1px 6px',
              fontFamily: 'var(--lbb-mono)',
            }}
          >
            {t('palette.hint')}
          </kbd>
        </div>

        {/* Results */}
        <div style={{ overflowY: 'auto', flex: 1, padding: '6px 0' }}>
          {flatRows.length === 0 ? (
            <div
              style={{
                padding: '18px 16px',
                color: 'var(--lbb-fg3)',
                fontSize: 'var(--lbb-fs-12-5)',
                textAlign: 'center',
              }}
            >
              {t('palette.empty')}
            </div>
          ) : (
            sections.map((section) => (
              <div key={section.key}>
                <div
                  style={{
                    padding: '6px 16px 3px',
                    fontSize: 'var(--lbb-fs-9-5)',
                    fontWeight: 700,
                    letterSpacing: 0.06,
                    textTransform: 'uppercase',
                    color: 'var(--lbb-fg3)',
                  }}
                >
                  {t(`palette.sections.${section.key}`)}
                </div>
                {section.rows.map((row) => {
                  flatIndex += 1
                  const idx = flatIndex
                  const active = idx === highlight
                  return (
                    <div
                      key={rowKey(row, idx)}
                      onMouseEnter={() => setHighlight(idx)}
                      onClick={() => runRow(row)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        padding: '7px 16px',
                        cursor: 'pointer',
                        background: active ? 'var(--lbb-accent-soft)' : 'transparent',
                        color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
                        fontSize: 'var(--lbb-fs-12-5)',
                      }}
                    >
                      {renderRow(row, tDyn)}
                    </div>
                  )
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer (action outcome) */}
        {footer && (
          <div
            style={{
              padding: '9px 16px',
              borderTop: '1px solid var(--lbb-border)',
              fontSize: 'var(--lbb-fs-11-5)',
              color: 'var(--lbb-fg2)',
              background: 'var(--lbb-surface2)',
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}

function rowKey(row: ResultRow, idx: number): string {
  if (row.kind === 'lb') return `lb-${row.n}`
  if (row.kind === 'entry') return `entry-${row.entry.lb}-${idx}`
  return `cmd-${row.command.id}`
}

function renderRow(
  row: ResultRow,
  t: (key: string, opts?: Record<string, unknown>) => string,
): React.ReactNode {
  if (row.kind === 'lb') {
    return <span style={{ fontWeight: 600 }}>{t('palette.goToLb', { n: row.n })}</span>
  }
  if (row.kind === 'entry') {
    const { lb, dateStr, location } = row.entry
    const parts = [`LB-${String(lb).padStart(5, '0')}`, dateStr, location].filter(Boolean)
    return (
      <span
        style={{
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {parts.join(' · ')}
      </span>
    )
  }
  return <span style={{ flex: 1 }}>{row.label}</span>
}
