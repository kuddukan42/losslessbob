// LB catalogue sync — route /lbdir/sync (TODO-305).
//
// Spec: instructions/design_handoff_lb_coverage_award/README.md §1 — "history of
// snapshots, diff per update, manual pull". The catalogue arrives as a master
// snapshot (GET /api/master/github_check → install in Setup), so this screen is
// the history of those imports plus the check that tells you a newer one exists.
//
// The history rows come from lb_snapshot_history, written on every master
// import. A DB that installed its catalogue before that table existed gets one
// `synthetic` row derived from meta — flagged as such rather than pretending to
// be a real import record.

import React, { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Icon } from '../components/Icon'
import { Banner, Button, Pill, TableShell, TH, TR, TD } from '../components'

const BASE = window.api.flaskBase

interface Snapshot {
  id:                  number | null
  label:               string | null
  master_version:      string | null
  master_published_at: string | null
  imported_at:         string | null
  source:              string
  entries_total:       number | null
  entries_held:        number | null
  entries_added:       number | null
  lb_status_changes:   number | null
  status_counts:       Record<string, number>
  row_counts:          Record<string, number>
  backup_path:         string | null
  synthetic:           boolean
}

interface SnapshotsPayload {
  snapshots: Snapshot[]
  current: {
    label: string | null
    version: string | null
    published_at: string | null
    last_import: string | null
    entry_count: number
  }
  total: number
}

interface GithubCheck {
  available:      boolean
  local_version:  string
  remote_version: string
}

type CheckState =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'uptodate'; version: string }
  | { kind: 'newer'; version: string }
  | { kind: 'error' }

function fmtStamp(raw: string | null): string {
  if (!raw) return '—'
  return raw.replace('T', ' ').slice(0, 16)
}

function num(n: number | null | undefined): string {
  return n === null || n === undefined ? '—' : n.toLocaleString('en-US')
}

export function ScreenLbdirSync(): React.JSX.Element {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [check, setCheck] = useState<CheckState>({ kind: 'idle' })

  const { data, isLoading, isError, refetch } = useQuery<SnapshotsPayload>({
    queryKey: ['lb-snapshots'],
    queryFn: async () => {
      const r = await fetch(`${BASE}/api/lb/snapshots`)
      if (!r.ok) throw new Error(String(r.status))
      return r.json() as Promise<SnapshotsPayload>
    },
    staleTime: 60_000,
  })

  const runCheck = useCallback(async () => {
    setCheck({ kind: 'busy' })
    try {
      const r = await fetch(`${BASE}/api/master/github_check`)
      if (!r.ok) throw new Error(String(r.status))
      const j = (await r.json()) as GithubCheck
      setCheck(j.available
        ? { kind: 'newer', version: j.remote_version }
        : { kind: 'uptodate', version: j.local_version })
      void refetch()
    } catch {
      setCheck({ kind: 'error' })
    }
  }, [refetch])

  const current = data?.current
  const rows = data?.snapshots ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
        padding: '14px 16px 12px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 'auto' }}>
          <Icon name="lbdir" size={16} />
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--lbb-fg)' }}>
            {t('lbSync.title')}
          </span>
          <span style={{ fontSize: 12, color: 'var(--lbb-fg3)' }}>{t('lbSync.subtitle')}</span>
        </div>
        <Button
          variant="primary" size="sm" icon="refresh"
          disabled={check.kind === 'busy'} aria-busy={check.kind === 'busy'}
          onClick={() => void runCheck()}
        >
          {check.kind === 'busy' ? t('lbSync.checking') : t('lbSync.actCheck')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => navigate('/lbdir/ledger')}>
          {t('lbSync.actLedger')}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => navigate('/about/coverage')}>
          {t('lbSync.actBack')}
        </Button>
      </div>

      <div style={{ padding: '0 16px 12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Installed catalogue. */}
        <div style={{
          display: 'flex', gap: 26, flexWrap: 'wrap', alignItems: 'baseline',
          padding: '12px 16px', borderRadius: 7,
          border: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)',
        }}>
          {([
            ['lbSync.curLabel', current?.label ?? '—'],
            ['lbSync.curVersion', current?.version ?? '—'],
            ['lbSync.curPublished', fmtStamp(current?.published_at ?? null)],
            ['lbSync.curImported', fmtStamp(current?.last_import ?? null)],
            ['lbSync.curEntries', num(current?.entry_count)],
          ] as const).map(([key, value]) => (
            <div key={key}>
              <div style={{
                fontSize: 10, fontWeight: 600, letterSpacing: '.1em',
                textTransform: 'uppercase', color: 'var(--lbb-fg3)',
              }}>
                {t(key)}
              </div>
              <div style={{
                marginTop: 3, fontFamily: 'var(--lbb-mono)', fontSize: 13,
                fontWeight: 600, color: 'var(--lbb-fg)',
              }}>
                {value}
              </div>
            </div>
          ))}
        </div>

        {/* Result of a manual check. */}
        {check.kind === 'newer' && (
          <Banner
            tone="warn" icon="download" title={t('lbSync.newerTitle', { version: check.version })}
            action={<Button size="sm" onClick={() => navigate('/setup')}>{t('lbSync.openSetup')}</Button>}
          >
            {t('lbSync.newerBody')}
          </Banner>
        )}
        {check.kind === 'uptodate' && (
          <Banner tone="ok" icon="check" title={t('lbSync.upToDateTitle', { version: check.version })}>
            {t('lbSync.upToDateBody')}
          </Banner>
        )}
        {check.kind === 'error' && (
          <Banner
            tone="bad" icon="alert" title={t('lbSync.failedTitle')}
            action={<Button size="sm" onClick={() => void runCheck()}>{t('lbSync.retry')}</Button>}
          >
            {t('lbSync.failedBody')}
          </Banner>
        )}
      </div>

      {/* Import history. */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', borderTop: '1px solid var(--lbb-border)' }}>
        <TableShell>
          <colgroup>
            <col style={{ width: 3 }} />
            <col style={{ width: 96 }} />
            <col style={{ width: 150 }} />
            <col style={{ width: 92 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 110 }} />
            <col style={{ width: 120 }} />
            <col />
          </colgroup>
          <thead>
            <tr>
              <th style={{ width: 3, padding: 0, background: 'var(--lbb-surface2)' }} />
              <TH>{t('lbSync.colLabel')}</TH>
              <TH>{t('lbSync.colImported')}</TH>
              <TH>{t('lbSync.colSource')}</TH>
              <TH align="right">{t('lbSync.colTotal')}</TH>
              <TH align="right">{t('lbSync.colAdded')}</TH>
              <TH align="right">{t('lbSync.colChanges')}</TH>
              <TH>{t('lbSync.colNote')}</TH>
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => (
              <TR key={s.id ?? `synthetic-${i}`} edge={s.synthetic ? 'mute' : 'ok'}>
                <TD mono style={{ color: 'var(--lbb-fg)' }}>{s.label ?? '—'}</TD>
                <TD mono>{fmtStamp(s.imported_at)}</TD>
                <TD>
                  <Pill tone={s.source === 'github' ? 'info' : 'mute'} soft>
                    {t(`lbSync.source.${s.source === 'github' || s.source === 'file' ? s.source : 'unknown'}`)}
                  </Pill>
                </TD>
                <TD mono align="right">{num(s.entries_total)}</TD>
                <TD mono align="right" style={{
                  color: (s.entries_added ?? 0) > 0 ? 'var(--lbb-ok-fg)' : undefined,
                }}>
                  {s.entries_added === null || s.entries_added === undefined
                    ? '—'
                    : `${s.entries_added > 0 ? '+' : ''}${s.entries_added.toLocaleString('en-US')}`}
                </TD>
                <TD mono align="right">{num(s.lb_status_changes)}</TD>
                <TD dim>
                  <span title={s.master_version ?? undefined}>
                    {s.synthetic ? t('lbSync.syntheticNote') : (s.master_version ?? '—')}
                  </span>
                </TD>
              </TR>
            ))}
            {!rows.length && (
              <TR>
                <TD colSpan={7} dim align="center" style={{ padding: 28, whiteSpace: 'normal' }}>
                  {isLoading ? t('common.loading')
                    : isError ? t('lbSync.error')
                    : t('lbSync.empty')}
                </TD>
              </TR>
            )}
          </tbody>
        </TableShell>
      </div>
    </div>
  )
}
