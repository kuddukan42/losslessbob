// Setlist fingerprinting curator review queue (TODO-225). For entries whose
// date/location metadata is unusable ('various', empty/xx dates, or a
// location the geocoder's TODO-221 filter parked in skipped_not_concert),
// backend/setlist_fingerprint.py scores the folder tracklist against every
// Olof Björner setlist and surfaces the best-matching show(s) here as
// suggestions only — never auto-applied. A curator reviews a match, then
// either hand-edits the entry's date in the DB Editor (which drops it out of
// the candidate set on the next scan) or dismisses a bad suggestion.

import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Pill, Chip, Button } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { useSettingsStore } from '../store'

const BASE = window.api.flaskBase

// ── Types (mirror backend/setlist_fingerprint.py row shapes) ─────────────────

interface SongMatch {
  entry_index: number
  position: number
  matched_title: string
}

interface Suggestion {
  lb_number: number
  rank: number
  event_id: number
  score: number
  matched_count: number
  entry_song_count: number
  olof_song_count: number
  matched: SongMatch[]
  missing: string[]
  status: 'pending' | 'dismissed'
  computed_at: string
  entry_date_str: string
  entry_location: string
  event_date: string
  venue: string | null
  city: string | null
  region: string | null
  country: string | null
  event_type: string | null
}

interface ScanStats {
  candidates_scanned: number
  candidates_matched: number
  suggestions_written: number
  skipped_no_titles: number
}

type StatusFilter = 'pending' | 'dismissed' | 'all'

function fmtLb(n: number): string {
  return `LB-${String(n).padStart(5, '0')}`
}

function scoreTone(score: number): 'ok' | 'warn' | 'mute' {
  if (score >= 0.6) return 'ok'
  if (score >= 0.3) return 'warn'
  return 'mute'
}

function eventTypeTone(eventType: string | null): 'ok' | 'info' | 'mute' {
  if (eventType === 'concert') return 'ok'
  if (eventType) return 'info'
  return 'mute'
}

// ── Row ────────────────────────────────────────────────────────────────────

function SuggestionRow({
  s, expanded, onToggle, onOpenLb, onDismiss, curatorMode, dismissing,
}: {
  s: Suggestion
  expanded: boolean
  onToggle: () => void
  onOpenLb: (lb: number) => void
  onDismiss: (lb: number, eventId: number) => void
  curatorMode: boolean
  dismissing: boolean
}) {
  const { t } = useTranslation()
  const venue = [s.venue, s.city, s.region || s.country].filter(Boolean).join(', ')

  return (
    <React.Fragment>
      <TR>
        <TD align="center">
          <button
            type="button"
            onClick={onToggle}
            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, display: 'inline-flex' }}
          >
            <Icon name={expanded ? 'chevDown' : 'chevRight'} size={12} style={{ color: 'var(--lbb-fg3)' }} />
          </button>
        </TD>
        <TD>
          <button
            type="button"
            onClick={() => onOpenLb(s.lb_number)}
            title={t('fingerprint.table.openInLibrary')}
            style={{
              fontFamily: 'var(--lbb-mono)', fontSize: 'inherit', fontWeight: 600,
              color: 'var(--lbb-accent-mid)', background: 'none', border: 'none',
              padding: 0, cursor: 'pointer',
            }}
          >
            {fmtLb(s.lb_number)}
          </button>
          {s.rank > 1 && (
            <span style={{ marginLeft: 6, fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)' }}>
              {t('fingerprint.table.rank', { rank: s.rank })}
            </span>
          )}
        </TD>
        <TD dim style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          <span title={s.entry_location}>{s.entry_date_str || t('fingerprint.table.noDate')} · {s.entry_location || t('fingerprint.table.noLocation')}</span>
        </TD>
        <TD mono>{s.event_date}</TD>
        <TD style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          <span title={venue}>{venue || t('fingerprint.table.noLocation')}</span>
        </TD>
        <TD>
          <Pill tone={eventTypeTone(s.event_type)} soft>{s.event_type || t('fingerprint.table.noLocation')}</Pill>
        </TD>
        <TD align="center">
          <Pill tone={scoreTone(s.score)} soft>{Math.round(s.score * 100)}%</Pill>
        </TD>
        <TD mono align="center">{s.matched_count} / {s.entry_song_count}</TD>
        <TD align="right">
          {curatorMode && s.status === 'pending' && (
            <Button
              variant="ghost" size="sm" disabled={dismissing}
              onClick={() => onDismiss(s.lb_number, s.event_id)}
            >
              {t('fingerprint.table.dismiss')}
            </Button>
          )}
          {s.status === 'dismissed' && (
            <Pill tone="mute" soft>{t('fingerprint.table.dismissedBadge')}</Pill>
          )}
        </TD>
      </TR>
      {expanded && (
        <tr>
          <td colSpan={9} style={{ padding: 0 }}>
            <div style={{
              padding: '12px 16px 14px 44px', background: 'var(--lbb-surface2)',
              borderBottom: '1px solid var(--lbb-border)',
              display: 'flex', gap: 32, flexWrap: 'wrap',
            }}>
              <div style={{ minWidth: 220 }}>
                <div style={{
                  fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: 0.05,
                  textTransform: 'uppercase', color: 'var(--lbb-ok-fg)', marginBottom: 6,
                }}>
                  {t('fingerprint.detail.matched', { count: s.matched.length })}
                </div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)' }}>
                  {s.matched.map(m => <li key={`${m.entry_index}-${m.position}`}>{m.matched_title}</li>)}
                </ul>
              </div>
              <div style={{ minWidth: 220 }}>
                <div style={{
                  fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, letterSpacing: 0.05,
                  textTransform: 'uppercase', color: 'var(--lbb-fg3)', marginBottom: 6,
                }}>
                  {t('fingerprint.detail.missing', { count: s.missing.length })}
                </div>
                {s.missing.length === 0 ? (
                  <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontStyle: 'italic' }}>
                    {t('fingerprint.detail.completeMatch')}
                  </div>
                ) : (
                  <ul style={{ margin: 0, paddingLeft: 16, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
                    {s.missing.map((title, i) => <li key={i}>{title}</li>)}
                  </ul>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  )
}

// ── Screen ─────────────────────────────────────────────────────────────────

export function ScreenFingerprint(): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const curatorMode = useSettingsStore((s) => s.curatorMode)

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending')
  const [expandedKey, setExpandedKey] = useState<string | null>(null)
  const [scanning, setScanning] = useState(false)
  const [scanStats, setScanStats] = useState<ScanStats | null>(null)
  const [scanError, setScanError] = useState<string | null>(null)
  const [dismissingKey, setDismissingKey] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['fingerprint-suggestions', statusFilter],
    queryFn: () => fetch(`${BASE}/api/fingerprint/suggestions?status=${statusFilter}`).then(r => r.json()),
    staleTime: 15_000,
  })
  const suggestions: Suggestion[] = data?.suggestions ?? []

  const openLb = (lb: number) => navigate(`/library?lb=${lb}`)

  const runScan = async () => {
    setScanning(true)
    setScanError(null)
    try {
      const resp = await fetch(`${BASE}/api/fingerprint/scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      if (!resp.ok) {
        setScanError(t('fingerprint.scan.failed'))
        return
      }
      const stats: ScanStats = await resp.json()
      setScanStats(stats)
      queryClient.invalidateQueries({ queryKey: ['fingerprint-suggestions'] })
    } catch {
      setScanError(t('fingerprint.scan.failed'))
    } finally {
      setScanning(false)
    }
  }

  const dismiss = async (lb: number, eventId: number) => {
    const key = `${lb}-${eventId}`
    setDismissingKey(key)
    try {
      const resp = await fetch(`${BASE}/api/fingerprint/suggestions/dismiss`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lb_number: lb, event_id: eventId }),
      })
      if (resp.ok) {
        queryClient.invalidateQueries({ queryKey: ['fingerprint-suggestions'] })
      }
    } finally {
      setDismissingKey(null)
    }
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>

      {/* Header */}
      <div style={{
        padding: '14px 24px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="fingerprint" size={18} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('fingerprint.title')}
          </h1>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('fingerprint.subtitle')}
          </div>
        </div>
        <Button variant="primary" size="sm" icon="refresh" disabled={scanning} onClick={runScan}>
          {scanning ? t('fingerprint.scan.running') : t('fingerprint.scan.button')}
        </Button>
      </div>

      {(scanStats || scanError) && (
        <div style={{
          padding: '8px 24px', borderBottom: '1px solid var(--lbb-border)',
          fontSize: 'var(--lbb-fs-11-5)', color: scanError ? 'var(--lbb-bad-fg)' : 'var(--lbb-fg3)',
        }}>
          {scanError ?? t('fingerprint.scan.stats', {
            scanned: scanStats!.candidates_scanned,
            matched: scanStats!.candidates_matched,
            written: scanStats!.suggestions_written,
          })}
        </div>
      )}

      <div style={{ padding: '12px 24px 0', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Chip size="sm" active={statusFilter === 'pending'} onClick={() => setStatusFilter('pending')}>
          {t('fingerprint.filter.pending')}
        </Chip>
        <Chip size="sm" active={statusFilter === 'dismissed'} onClick={() => setStatusFilter('dismissed')}>
          {t('fingerprint.filter.dismissed')}
        </Chip>
        <Chip size="sm" active={statusFilter === 'all'} onClick={() => setStatusFilter('all')}>
          {t('fingerprint.filter.all')}
        </Chip>
        <span style={{ marginLeft: 'auto', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
          {t('fingerprint.count', { count: suggestions.length })}
        </span>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '12px 24px 24px' }}>
        {isLoading ? (
          <div style={{ padding: '24px 0', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
            {t('common.loading')}
          </div>
        ) : suggestions.length === 0 ? (
          <div style={{
            padding: '40px 0', textAlign: 'center', color: 'var(--lbb-fg3)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
          }}>
            <Icon name="fingerprint" size={32} style={{ opacity: 0.15 }} />
            <span style={{ fontSize: 'var(--lbb-fs-13)' }}>{t('fingerprint.empty')}</span>
          </div>
        ) : (
          <TableShell stickyHeader={false}>
            <colgroup>
              <col style={{ width: 28 }} />
              <col style={{ width: 100 }} />
              <col style={{ width: 220 }} />
              <col style={{ width: 100 }} />
              <col />
              <col style={{ width: 90 }} />
              <col style={{ width: 64 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 90 }} />
            </colgroup>
            <thead>
              <tr>
                <TH> </TH>
                <TH>{t('fingerprint.table.lb')}</TH>
                <TH>{t('fingerprint.table.entry')}</TH>
                <TH>{t('fingerprint.table.matchDate')}</TH>
                <TH>{t('fingerprint.table.matchVenue')}</TH>
                <TH>{t('fingerprint.table.type')}</TH>
                <TH align="center">{t('fingerprint.table.score')}</TH>
                <TH align="center">{t('fingerprint.table.songs')}</TH>
                <TH> </TH>
              </tr>
            </thead>
            <tbody>
              {suggestions.map(s => {
                const key = `${s.lb_number}-${s.event_id}`
                return (
                  <SuggestionRow
                    key={key}
                    s={s}
                    expanded={expandedKey === key}
                    onToggle={() => setExpandedKey(expandedKey === key ? null : key)}
                    onOpenLb={openLb}
                    onDismiss={dismiss}
                    curatorMode={curatorMode}
                    dismissing={dismissingKey === key}
                  />
                )
              })}
            </tbody>
          </TableShell>
        )}
      </div>
    </div>
  )
}
