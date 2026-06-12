import React from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Pill } from '../index'

export interface Mount {
  id: number
  label: string
  span: string
  free: string
  total: string
  used_pct: number | null
  online: boolean
}

// ── Mount picker ────────────────────────────────────────────────────────────────

export interface MountPickerProps {
  mounts: Mount[]
  selectedMount: number | null
  recommendedMount: number | null
  routedYear?: number | null
  onSelectMount: (id: number) => void
}

/** Storage-mount picker grid — harvested target: design doc 14 §2.5 / pipeline2-stages.jsx L588-614. */
export function MountPicker({
  mounts, selectedMount, recommendedMount, routedYear, onSelectMount,
}: MountPickerProps): React.JSX.Element | null {
  const { t } = useTranslation()
  if (mounts.length === 0) return null

  const recommended = mounts.find(m => m.id === recommendedMount)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
          {t('pipeline.collect.storageMount')}
        </span>
        {routedYear != null && recommended && (
          <Pill tone="info" soft>
            {t('pipeline.collect.routedByYear', { year: routedYear, mount: recommended.label })}
          </Pill>
        )}
        <div style={{ flex: 1 }} />
        {selectedMount !== recommendedMount && recommendedMount != null && (
          <Button variant="ghost" size="sm" icon="refresh" onClick={() => onSelectMount(recommendedMount)}>
            {t('pipeline.collect.resetToSuggested')}
          </Button>
        )}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 16 }}>
        {mounts.map(m => {
          const sel = selectedMount === m.id
          return (
            <label
              key={m.id}
              title={m.online
                ? t('pipeline.collect.mountTooltip', { span: m.span, free: m.free, total: m.total, pct: m.used_pct })
                : t('pipeline.collect.mountOffline')}
              style={{
                display: 'flex', flexDirection: 'column', gap: 3, padding: '10px 12px',
                cursor: m.online ? 'pointer' : 'not-allowed',
                opacity: m.online ? 1 : 0.5,
                background: sel ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
                border: `1px solid ${sel ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`, borderRadius: 9,
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <input type="radio" name="collect-mount" checked={sel} disabled={!m.online}
                  onChange={() => onSelectMount(m.id)} />
                <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-13)', fontWeight: 700, color: sel ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)' }}>
                  {m.label}
                </span>
                {m.id === recommendedMount && (
                  <Pill tone="ok" soft style={{ marginLeft: 'auto' }}>{t('pipeline.collect.suggested')}</Pill>
                )}
              </span>
              <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)' }}>{m.span}</span>
              <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
                {m.online ? t('pipeline.collect.freeOfTotal', { free: m.free, total: m.total }) : t('pipeline.collect.mountOffline')}
              </span>
              {m.online && m.used_pct != null && (
                <div style={{ height: 4, borderRadius: 2, background: 'var(--lbb-border)', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', width: `${m.used_pct}%`,
                    background: m.used_pct >= 90 ? 'var(--lbb-bad-bar)'
                      : m.used_pct >= 75 ? 'var(--lbb-warn-bar)' : 'var(--lbb-accent-mid)',
                  }} />
                </div>
              )}
            </label>
          )
        })}
      </div>
    </div>
  )
}

// ── Tag table ─────────────────────────────────────────────────────────────────

export interface TagTableProps {
  lbLabel?: string | null
  collectionCount?: number | null
  lbStatus?: string | null
  owned?: boolean | null
  confirmedAt?: string | null
}

/** "Tag in the collection" preview rows — design doc 14 §2.5 / pipeline2-stages.jsx L616-630. */
export function TagTable({ lbLabel, collectionCount, lbStatus, owned, confirmedAt }: TagTableProps): React.JSX.Element {
  const { t } = useTranslation()
  const statusLabel = lbStatus === 'public' ? t('pipeline.collect.statusPublic')
    : lbStatus === 'private' ? t('pipeline.collect.statusPrivate')
    : lbStatus === 'missing' ? t('pipeline.collect.statusMissing')
    : lbStatus === 'nonexistent' ? t('pipeline.collect.statusNonexistent')
    : t('pipeline.collect.statusUnknown')
  const ownedLabel = t(owned ? 'pipeline.collect.ownedYes' : 'pipeline.collect.ownedNo')
  const confirmedLabel = confirmedAt
    ? confirmedAt.slice(0, 10)
    : t('pipeline.collect.notConfirmed')
  const rows: [string, string, boolean?][] = [
    [t('pipeline.collect.rowLb'), lbLabel ?? t('pipeline.collect.valueUnassigned'), true],
    [t('pipeline.collect.rowStatus'), `${statusLabel} · ${ownedLabel}`],
    [t('pipeline.collect.rowConfirmed'), confirmedLabel],
  ]
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
          {t('pipeline.collect.tagInCollection')}
        </span>
        <div style={{ flex: 1 }} />
        {collectionCount != null && (
          <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
            {t('pipeline.collect.itemsCounter', { count: collectionCount, next: collectionCount + 1 })}
          </span>
        )}
      </div>
      <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 8, overflow: 'hidden', marginBottom: 14 }}>
        {rows.map(([k, v, mono], i) => (
          <div key={k} style={{
            display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px',
            borderBottom: i < rows.length - 1 ? '1px solid var(--lbb-border)' : 'none',
            background: i % 2 ? 'var(--lbb-surface)' : 'var(--lbb-surface2)',
          }}>
            <span style={{ fontSize: 'var(--lbb-fs-11)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.04, textTransform: 'uppercase', width: 110 }}>{k}</span>
            <span style={{ fontSize: 'var(--lbb-fs-12-5)', fontFamily: mono ? 'var(--lbb-mono)' : 'inherit', fontWeight: mono ? 700 : 500, color: mono ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)' }}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── CollectDetail ─────────────────────────────────────────────────────────────

export interface CollectDetailProps {
  mounts: Mount[]
  selectedMount: number | null
  recommendedMount: number | null
  routedYear?: number | null
  lbLabel?: string | null
  collectionCount?: number | null
  lbStatus?: string | null
  owned?: boolean | null
  confirmedAt?: string | null
  onSelectMount: (id: number) => void
}

/**
 * Mount picker + "Tag in the collection" preview for the Collect stage's
 * ready-to-file state. The only genuinely new panel in design doc 14 §2.5 —
 * everything else in the gap punch-list is harvested from existing screens.
 */
export function CollectDetail({
  mounts, selectedMount, recommendedMount, routedYear, lbLabel, collectionCount,
  lbStatus, owned, confirmedAt, onSelectMount,
}: CollectDetailProps): React.JSX.Element {
  return (
    <>
      <MountPicker
        mounts={mounts}
        selectedMount={selectedMount}
        recommendedMount={recommendedMount}
        routedYear={routedYear}
        onSelectMount={onSelectMount}
      />
      <TagTable
        lbLabel={lbLabel}
        collectionCount={collectionCount}
        lbStatus={lbStatus}
        owned={owned}
        confirmedAt={confirmedAt}
      />
    </>
  )
}
