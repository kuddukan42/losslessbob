// TODO-299: curator triage for checksum_disputes findings. A "finding" pairs
// the (up to two) checksum_disputes rows that share one disputed value — one
// row scored against the `checksums` table, one against the LB's own lbdir
// manifest — and is classified into a verdict bucket that decides the fix.
// See backend/checksum_provenance.py get_findings() and
// tools/checksum_dispute_report.py's module docstring for the taxonomy.

import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Pill, Chip, Button } from '../components'
import { TableShell, TH, TR, TD } from '../components'
import { useSettingsStore } from '../store'
import { lbLabel, lbDetailUrl } from '../lib/lbUrl'

const BASE = window.api.flaskBase

// ── Types (mirror backend.checksum_provenance.get_findings) ─────────────────

type Verdict = 'db_error' | 'audio_differs' | 'retag' | 'receipt_unknown' | 'lbdir_only'
type VerdictFilter = Verdict | 'all'
type ReferenceFilter = 'db' | 'lbdir' | 'all'
type DisputeStatus = 'open' | 'confirmed' | 'dismissed'

interface DisputeRef {
  reference_checksum: string
  reference_file: string | null
  confidence: 'high' | 'medium' | 'low'
}

interface Finding {
  ids: number[]
  lb_number: number
  filename: string
  chk_type: 'm' | 'f' | 's'
  verdict: Verdict
  confidence: 'high' | 'medium' | 'low'
  source_checksum: string
  source_files: string[]
  source_kind: string
  source_scope: string
  source_suspect: number
  source_orphan: number
  displaced_to: string | null
  statuses: DisputeStatus[]
  refs: { db?: DisputeRef; lbdir?: DisputeRef }
}

const VERDICT_ORDER: Verdict[] = ['db_error', 'audio_differs', 'retag', 'receipt_unknown', 'lbdir_only']

function verdictTone(v: Verdict): 'bad' | 'warn' | 'info' | 'mute' {
  if (v === 'db_error') return 'bad'
  if (v === 'audio_differs') return 'warn'
  if (v === 'retag') return 'info'
  return 'mute'
}

const CHK_LABEL: Record<string, string> = { m: 'MD5', f: 'FFP', s: 'ST5' }

// ── Row ──────────────────────────────────────────────────────────────────

function FindingRow({
  f, curatorMode, busy, onVerdict,
}: {
  f: Finding
  curatorMode: boolean
  busy: boolean
  onVerdict: (f: Finding, status: DisputeStatus) => void
}) {
  const { t } = useTranslation()
  const settled = f.statuses.every(s => s !== 'open')
  const openLb = () => window.open(lbDetailUrl(f.lb_number))
  const badges: React.JSX.Element[] = []
  if (f.source_orphan) {
    badges.push(<Pill key="orphan" tone="bad" soft title={t('checksumDisputes.badges.orphanTitle')}>
      {t('checksumDisputes.badges.orphan')}
    </Pill>)
  }
  if (f.source_suspect) {
    badges.push(<Pill key="suspect" tone="warn" soft title={t('checksumDisputes.badges.suspectTitle')}>
      {t('checksumDisputes.badges.suspect')}
    </Pill>)
  }
  if (f.source_kind === 'collection') {
    badges.push(<Pill key="collection" tone="mute" soft title={t('checksumDisputes.badges.collectionTitle')}>
      {t('checksumDisputes.badges.collection')}
    </Pill>)
  }
  if (f.source_scope === 'xref') {
    badges.push(<Pill key="xref" tone="mute" soft title={t('checksumDisputes.badges.xrefTitle')}>
      {t('checksumDisputes.badges.xref')}
    </Pill>)
  }
  if (f.displaced_to) {
    badges.push(<Pill key="displaced" tone="info" soft title={t('checksumDisputes.badges.displacedTitle', { file: f.displaced_to })}>
      {t('checksumDisputes.badges.displaced')}
    </Pill>)
  }

  return (
    <TR edge={verdictTone(f.verdict) === 'mute' ? undefined : verdictTone(f.verdict)}>
      <TD>
        <button type="button" onClick={openLb} style={{
          fontFamily: 'var(--lbb-mono)', fontSize: 'inherit', fontWeight: 600,
          color: 'var(--lbb-accent-mid)', background: 'none', border: 'none', padding: 0, cursor: 'pointer',
        }}>
          {lbLabel(f.lb_number)}
        </button>
      </TD>
      <TD mono style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <span title={f.filename}>{f.filename}</span>
      </TD>
      <TD align="center" mono dim>{CHK_LABEL[f.chk_type] ?? f.chk_type}</TD>
      <TD>
        <Pill tone={verdictTone(f.verdict)} soft>{t(`checksumDisputes.verdict.${f.verdict}`)}</Pill>
      </TD>
      <TD align="center">
        <Pill tone={f.confidence === 'high' ? 'ok' : f.confidence === 'medium' ? 'warn' : 'mute'} soft>
          {t(`checksumDisputes.confidence.${f.confidence}`)}
        </Pill>
      </TD>
      <TD>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {badges.length > 0 ? badges : <span style={{ color: 'var(--lbb-fg3)' }}>—</span>}
        </div>
      </TD>
      <TD align="right">
        {settled ? (
          <Pill tone="mute" soft>{t(`checksumDisputes.status.${f.statuses[0]}`)}</Pill>
        ) : curatorMode ? (
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => onVerdict(f, 'confirmed')}>
              {t('checksumDisputes.action.confirm')}
            </Button>
            <Button variant="ghost" size="sm" disabled={busy} onClick={() => onVerdict(f, 'dismissed')}>
              {t('checksumDisputes.action.dismiss')}
            </Button>
          </div>
        ) : (
          <Pill tone="mute" soft>{t('checksumDisputes.status.open')}</Pill>
        )}
      </TD>
    </TR>
  )
}

// ── Screen ───────────────────────────────────────────────────────────────

export function ScreenChecksumDisputes(): React.JSX.Element {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const curatorMode = useSettingsStore((s) => s.curatorMode)

  const [verdictFilter, setVerdictFilter] = useState<VerdictFilter>('all')
  const [referenceFilter, setReferenceFilter] = useState<ReferenceFilter>('all')
  const [busyKey, setBusyKey] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['checksum-disputes', referenceFilter],
    queryFn: () => {
      const params = new URLSearchParams({ grouped: '1', status: 'open' })
      if (referenceFilter !== 'all') params.set('reference', referenceFilter)
      return fetch(`${BASE}/api/checksum-disputes?${params}`).then(r => r.json())
    },
    staleTime: 15_000,
  })
  const findings: Finding[] = Array.isArray(data) ? data : []

  const counts = VERDICT_ORDER.reduce<Record<Verdict, number>>((acc, v) => {
    acc[v] = findings.filter(f => f.verdict === v).length
    return acc
  }, {} as Record<Verdict, number>)

  const visible = verdictFilter === 'all' ? findings : findings.filter(f => f.verdict === verdictFilter)

  const applyVerdict = async (f: Finding, status: DisputeStatus) => {
    const key = f.ids.join(',')
    setBusyKey(key)
    try {
      // A finding may span two checksum_disputes rows (one per reference) —
      // the verdict has to land on both.
      await Promise.all(f.ids.map(id => fetch(`${BASE}/api/checksum-disputes/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })))
      queryClient.invalidateQueries({ queryKey: ['checksum-disputes'] })
    } finally {
      setBusyKey(null)
    }
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{
        padding: '14px 24px', borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Icon name="alert" size={18} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-18)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('checksumDisputes.title')}
          </h1>
          <div style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('checksumDisputes.subtitle')}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          <Chip size="sm" active={referenceFilter === 'all'} onClick={() => setReferenceFilter('all')}>
            {t('checksumDisputes.reference.all')}
          </Chip>
          <Chip size="sm" active={referenceFilter === 'db'} onClick={() => setReferenceFilter('db')}>
            {t('checksumDisputes.reference.db')}
          </Chip>
          <Chip size="sm" active={referenceFilter === 'lbdir'} onClick={() => setReferenceFilter('lbdir')}>
            {t('checksumDisputes.reference.lbdir')}
          </Chip>
        </div>
      </div>

      <div style={{ padding: '12px 24px 0', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <Chip size="sm" active={verdictFilter === 'all'} onClick={() => setVerdictFilter('all')}>
          {t('checksumDisputes.verdictFilter.all', { count: findings.length })}
        </Chip>
        {VERDICT_ORDER.map(v => (
          <Chip key={v} size="sm" active={verdictFilter === v} onClick={() => setVerdictFilter(v)}>
            {t(`checksumDisputes.verdict.${v}`)} ({counts[v]})
          </Chip>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>
          {t('checksumDisputes.count', { count: visible.length })}
        </span>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: '12px 24px 24px' }}>
        {isLoading ? (
          <div style={{ padding: '24px 0', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
            {t('common.loading')}
          </div>
        ) : visible.length === 0 ? (
          <div style={{
            padding: '40px 0', textAlign: 'center', color: 'var(--lbb-fg3)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
          }}>
            <Icon name="alert" size={32} style={{ opacity: 0.15 }} />
            <span style={{ fontSize: 'var(--lbb-fs-13)' }}>{t('checksumDisputes.empty')}</span>
          </div>
        ) : (
          <TableShell stickyHeader={false}>
            <colgroup>
              <col style={{ width: 100 }} />
              <col />
              <col style={{ width: 56 }} />
              <col style={{ width: 140 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 180 }} />
              <col style={{ width: 160 }} />
            </colgroup>
            <thead>
              <tr>
                <TH>{t('checksumDisputes.table.lb')}</TH>
                <TH>{t('checksumDisputes.table.filename')}</TH>
                <TH align="center">{t('checksumDisputes.table.type')}</TH>
                <TH>{t('checksumDisputes.table.verdict')}</TH>
                <TH align="center">{t('checksumDisputes.table.confidence')}</TH>
                <TH>{t('checksumDisputes.table.notes')}</TH>
                <TH align="right"> </TH>
              </tr>
            </thead>
            <tbody>
              {visible.map(f => (
                <FindingRow
                  key={f.ids.join(',')}
                  f={f}
                  curatorMode={curatorMode}
                  busy={busyKey === f.ids.join(',')}
                  onVerdict={applyVerdict}
                />
              ))}
            </tbody>
          </TableShell>
        )}
      </div>
    </div>
  )
}
