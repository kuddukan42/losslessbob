import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button, Pill } from '../components'

const BASE = window.api.flaskBase

// ── Types ─────────────────────────────────────────────────────────────────────

interface TableMeta {
  name: string
  row_count: number
  readonly?: boolean
  audit?: boolean
  warn?: boolean
}

interface ColumnDef {
  name: string
  type: string
  pk?: boolean
  notnull?: boolean
}

interface IntegrityStats {
  public: number
  private: number
  missing: number
  max_lb: number
  overrides: number
  needs_review: number
}

interface LbAlias {
  alias_lb: number
  canonical_lb: number
  relationship: string
  note: string | null
}

// ── Toast ─────────────────────────────────────────────────────────────────────

type ToastTone = 'ok' | 'bad' | 'info'

function Toast({ msg, tone, onDone }: { msg: string; tone: ToastTone; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3500)
    return () => clearTimeout(t)
  }, [onDone])
  const bg =
    tone === 'ok'  ? 'var(--lbb-ok-bg)'  :
    tone === 'bad' ? 'var(--lbb-bad-bg)' : 'var(--lbb-info-bg)'
  const fg =
    tone === 'ok'  ? 'var(--lbb-ok-fg)'  :
    tone === 'bad' ? 'var(--lbb-bad-fg)' : 'var(--lbb-info-fg)'
  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
      padding: '10px 16px', borderRadius: 8, background: bg, color: fg,
      fontSize: 'var(--lbb-fs-13)', fontWeight: 500, boxShadow: 'var(--lbb-shadowLg)',
      border: '1px solid color-mix(in oklab, currentColor 20%, transparent)',
    }}>
      {msg}
    </div>
  )
}

// ── Modal ─────────────────────────────────────────────────────────────────────

function Modal({
  title,
  onClose,
  children,
}: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 8000,
        background: 'rgba(0,0,0,0.45)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 12, padding: '20px 24px', minWidth: 360, maxWidth: 480,
        boxShadow: 'var(--lbb-shadowLg)',
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-15)', fontWeight: 700, marginBottom: 16, color: 'var(--lbb-fg)' }}>
          {title}
        </div>
        {children}
      </div>
    </div>
  )
}

function FormRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
      <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', minWidth: 130, textAlign: 'right' }}>
        {label}
      </span>
      {children}
    </div>
  )
}

function ModalInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      style={{
        padding: '5px 8px', borderRadius: 6, fontSize: 'var(--lbb-fs-13)',
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
        color: 'var(--lbb-fg)', width: '100%',
        ...props.style,
      }}
    />
  )
}

function ModalSelect(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      style={{
        padding: '5px 8px', borderRadius: 6, fontSize: 'var(--lbb-fs-13)',
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
        color: 'var(--lbb-fg)', width: '100%',
        ...props.style,
      }}
    />
  )
}

function ModalTextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      style={{
        padding: '5px 8px', borderRadius: 6, fontSize: 'var(--lbb-fs-13)',
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
        color: 'var(--lbb-fg)', width: '100%', resize: 'vertical',
        ...props.style,
      }}
    />
  )
}

// ── SidePanel section ─────────────────────────────────────────────────────────

function SideSection({
  title,
  children,
  collapsed,
  onToggle,
}: {
  title: string
  children: React.ReactNode
  collapsed: boolean
  onToggle: () => void
}) {
  return (
    <div style={{
      border: '1px solid var(--lbb-border)', borderRadius: 8,
      margin: '8px 8px 0',
      background: 'var(--lbb-surface)',
      overflow: 'hidden',
    }}>
      <button
        type="button"
        onClick={onToggle}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 6,
          padding: '7px 10px', background: 'var(--lbb-surface2)',
          border: 'none', borderBottom: collapsed ? 'none' : '1px solid var(--lbb-border)',
          cursor: 'pointer', fontSize: 'var(--lbb-fs-11)', fontWeight: 700, letterSpacing: 0.08,
          textTransform: 'uppercase', color: 'var(--lbb-fg2)', fontFamily: 'inherit',
        }}
      >
        <span style={{ fontSize: 'var(--lbb-fs-9)' }}>{collapsed ? '▶' : '▼'}</span>
        {title}
      </button>
      {!collapsed && (
        <div style={{ padding: '8px 10px' }}>
          {children}
        </div>
      )}
    </div>
  )
}

function SideButton({
  onClick,
  children,
  title: titleProp,
}: {
  onClick: () => void
  children: React.ReactNode
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={titleProp}
      style={{
        display: 'block', width: '100%', marginBottom: 4,
        padding: '5px 8px', borderRadius: 5, fontSize: 'var(--lbb-fs-11-5)',
        background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
        color: 'var(--lbb-fg)', cursor: 'pointer', textAlign: 'left',
        fontFamily: 'inherit',
      }}
    >
      {children}
    </button>
  )
}

// ── IntegrityPanel ────────────────────────────────────────────────────────────

function IntegrityPanel({
  stats,
  onReconcile,
  onShowNeedsReview,
  onAddOverride,
  onRemoveOverride,
  onExportOverrides,
  onImportOverrides,
  onBackup,
}: {
  stats: IntegrityStats | null
  onReconcile: () => void
  onShowNeedsReview: () => void
  onAddOverride: () => void
  onRemoveOverride: () => void
  onExportOverrides: () => void
  onImportOverrides: () => void
  onBackup: () => void
}) {
  const { t } = useTranslation()
  return (
    <div>
      {stats ? (
        <div style={{
          fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg2)', marginBottom: 8,
          fontFamily: 'var(--lbb-mono)', lineHeight: 1.7,
        }}>
          {t('dbeditor.integrity.public')}: {stats.public.toLocaleString()}{'\n'}
          {t('dbeditor.integrity.private')}: {stats.private.toLocaleString()}{'\n'}
          {t('dbeditor.integrity.missing')}: {stats.missing.toLocaleString()}{'\n'}
          {t('dbeditor.integrity.maxLb')}: {stats.max_lb.toLocaleString()}{'\n'}
          {t('dbeditor.integrity.overrides')}: {stats.overrides.toLocaleString()}{'\n'}
          {t('dbeditor.integrity.needsReview')}: {stats.needs_review.toLocaleString()}
        </div>
      ) : (
        <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginBottom: 8 }}>—</div>
      )}
      <SideButton onClick={onReconcile} title={t('dbeditor.integrity.reconcileHint')}>
        {t('dbeditor.integrity.reconcileAll')}
      </SideButton>
      <SideButton onClick={onShowNeedsReview} title={t('dbeditor.integrity.needsReviewHint')}>
        {t('dbeditor.integrity.showNeedsReview')}
      </SideButton>
      <SideButton onClick={onAddOverride} title={t('dbeditor.integrity.addOverrideHint')}>
        {t('dbeditor.integrity.addOverride')}
      </SideButton>
      <SideButton onClick={onRemoveOverride} title={t('dbeditor.integrity.removeOverrideHint')}>
        {t('dbeditor.integrity.removeOverride')}
      </SideButton>
      <SideButton onClick={onExportOverrides} title={t('dbeditor.integrity.exportOverridesHint')}>
        {t('dbeditor.integrity.exportOverrides')}
      </SideButton>
      <SideButton onClick={onImportOverrides} title={t('dbeditor.integrity.importOverridesHint')}>
        {t('dbeditor.integrity.importOverrides')}
      </SideButton>
      <SideButton onClick={onBackup} title={t('dbeditor.integrity.backupHint')}>
        {t('dbeditor.integrity.backup')}
      </SideButton>
    </div>
  )
}

// ── AliasPanel ────────────────────────────────────────────────────────────────

function AliasPanel({
  aliases,
  isCurator,
  status: aliasStatus,
  onAdd,
  onDelete,
  onReload,
}: {
  aliases: LbAlias[]
  isCurator: boolean
  status: string
  onAdd: () => void
  onDelete: (aliasLb: number) => void
  onReload: () => void
}) {
  const { t } = useTranslation()
  const [selected, setSelected] = useState<number | null>(null)

  return (
    <div>
      <div style={{ overflowX: 'auto', marginBottom: 6 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--lbb-fs-11)' }}>
          <thead>
            <tr>
              {[t('dbeditor.aliases.aliasLb'), '→', t('dbeditor.aliases.canonicalLb'),
                t('dbeditor.aliases.rel')].map((h, i) => (
                <th key={i} style={{
                  padding: '3px 5px', textAlign: 'left', fontWeight: 700,
                  color: 'var(--lbb-fg3)', borderBottom: '1px solid var(--lbb-border)',
                  whiteSpace: 'nowrap',
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {aliases.map((a) => (
              <tr
                key={a.alias_lb}
                onClick={() => setSelected(selected === a.alias_lb ? null : a.alias_lb)}
                style={{
                  cursor: 'pointer',
                  background: selected === a.alias_lb ? 'var(--lbb-accent-soft)' : 'transparent',
                }}
              >
                <td style={{ padding: '3px 5px', color: 'var(--lbb-fg)', fontFamily: 'var(--lbb-mono)' }}>
                  {String(a.alias_lb).padStart(5, '0')}
                </td>
                <td style={{ padding: '3px 5px', textAlign: 'center', color: 'var(--lbb-fg3)' }}>→</td>
                <td style={{ padding: '3px 5px', color: 'var(--lbb-fg)', fontFamily: 'var(--lbb-mono)' }}>
                  {String(a.canonical_lb).padStart(5, '0')}
                </td>
                <td style={{ padding: '3px 5px', color: 'var(--lbb-fg2)', fontSize: 'var(--lbb-fs-10)' }}>
                  {a.relationship}
                </td>
              </tr>
            ))}
            {aliases.length === 0 && (
              <tr>
                <td colSpan={4} style={{ padding: '6px 5px', color: 'var(--lbb-fg3)', fontStyle: 'italic', fontSize: 'var(--lbb-fs-11)' }}>
                  {t('dbeditor.aliases.empty')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
        <button
          type="button"
          onClick={onAdd}
          disabled={!isCurator}
          title={t('dbeditor.aliases.addHint')}
          style={{
            flex: 1, padding: '4px 6px', borderRadius: 5, fontSize: 'var(--lbb-fs-11)',
            background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
            color: isCurator ? 'var(--lbb-fg)' : 'var(--lbb-fg3)',
            cursor: isCurator ? 'pointer' : 'not-allowed', fontFamily: 'inherit',
          }}
        >
          {t('dbeditor.aliases.add')}
        </button>
        <button
          type="button"
          onClick={() => { if (selected !== null) onDelete(selected) }}
          disabled={!isCurator || selected === null}
          title={t('dbeditor.aliases.deleteHint')}
          style={{
            flex: 1, padding: '4px 6px', borderRadius: 5, fontSize: 'var(--lbb-fs-11)',
            background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
            color: (isCurator && selected !== null) ? 'var(--lbb-fg)' : 'var(--lbb-fg3)',
            cursor: (isCurator && selected !== null) ? 'pointer' : 'not-allowed', fontFamily: 'inherit',
          }}
        >
          {t('dbeditor.aliases.delete')}
        </button>
        <button
          type="button"
          onClick={onReload}
          style={{
            flex: 1, padding: '4px 6px', borderRadius: 5, fontSize: 'var(--lbb-fs-11)',
            background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
            color: 'var(--lbb-fg)', cursor: 'pointer', fontFamily: 'inherit',
          }}
        >
          {t('dbeditor.aliases.reload')}
        </button>
      </div>

      {aliasStatus && (
        <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', marginTop: 2 }}>{aliasStatus}</div>
      )}
    </div>
  )
}

// ── AddOverrideModal ──────────────────────────────────────────────────────────

function AddOverrideModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void
  onConfirm: (lb: number, status: string, notes: string) => void
}) {
  const { t } = useTranslation()
  const [lb, setLb]         = useState('')
  const [status, setStatus] = useState('public')
  const [notes, setNotes]   = useState('')

  function submit() {
    const n = parseInt(lb, 10)
    if (!n || n < 1) return
    onConfirm(n, status, notes.trim())
    onClose()
  }

  return (
    <Modal title={t('dbeditor.overrides.addTitle')} onClose={onClose}>
      <FormRow label={t('dbeditor.overrides.lbNumber')}>
        <ModalInput
          type="number" min={1} max={99999} value={lb}
          onChange={(e) => setLb(e.target.value)}
          autoFocus
          style={{ width: 90 }}
        />
      </FormRow>
      <FormRow label={t('dbeditor.overrides.status')}>
        <ModalSelect value={status} onChange={(e) => setStatus(e.target.value)}>
          {['public', 'private', 'missing', 'nonexistent'].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </ModalSelect>
      </FormRow>
      <FormRow label={t('dbeditor.overrides.notes')}>
        <ModalInput
          placeholder={t('dbeditor.overrides.notesPlaceholder')}
          value={notes} onChange={(e) => setNotes(e.target.value)}
        />
      </FormRow>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
        <Button variant="ghost" size="sm" onClick={onClose}>{t('dbeditor.cancel')}</Button>
        <Button variant="primary" size="sm" onClick={submit}>{t('dbeditor.ok')}</Button>
      </div>
    </Modal>
  )
}

// ── RemoveOverrideModal ───────────────────────────────────────────────────────

function RemoveOverrideModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void
  onConfirm: (lb: number) => void
}) {
  const { t } = useTranslation()
  const [lb, setLb] = useState('')

  function submit() {
    const n = parseInt(lb, 10)
    if (!n || n < 1) return
    onConfirm(n)
    onClose()
  }

  return (
    <Modal title={t('dbeditor.overrides.removeTitle')} onClose={onClose}>
      <FormRow label={t('dbeditor.overrides.lbNumber')}>
        <ModalInput
          type="number" min={1} max={99999} value={lb}
          onChange={(e) => setLb(e.target.value)}
          autoFocus
          style={{ width: 90 }}
        />
      </FormRow>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
        <Button variant="ghost" size="sm" onClick={onClose}>{t('dbeditor.cancel')}</Button>
        <Button variant="danger" size="sm" onClick={submit}>{t('dbeditor.overrides.clear')}</Button>
      </div>
    </Modal>
  )
}

// ── AddAliasModal ─────────────────────────────────────────────────────────────

function AddAliasModal({
  onClose,
  onConfirm,
}: {
  onClose: () => void
  onConfirm: (payload: {
    alias_lb: number; canonical_lb: number; relationship: string; note: string
  }) => void
}) {
  const { t } = useTranslation()
  const [aliasLb, setAliasLb]       = useState('')
  const [canonLb, setCanonLb]       = useState('')
  const [rel, setRel]               = useState('duplicate')
  const [note, setNote]             = useState('')

  function submit() {
    const a = parseInt(aliasLb, 10)
    const c = parseInt(canonLb, 10)
    if (!a || !c || a < 1 || c < 1) return
    onConfirm({ alias_lb: a, canonical_lb: c, relationship: rel, note: note.trim() })
    onClose()
  }

  return (
    <Modal title={t('dbeditor.aliases.addTitle')} onClose={onClose}>
      <FormRow label={t('dbeditor.aliases.aliasLbFull')}>
        <ModalInput
          type="number" min={1} max={999999} value={aliasLb}
          onChange={(e) => setAliasLb(e.target.value)}
          autoFocus style={{ width: 90 }}
        />
      </FormRow>
      <FormRow label={t('dbeditor.aliases.canonLbFull')}>
        <ModalInput
          type="number" min={1} max={999999} value={canonLb}
          onChange={(e) => setCanonLb(e.target.value)}
          style={{ width: 90 }}
        />
      </FormRow>
      <FormRow label={t('dbeditor.aliases.relationship')}>
        <ModalSelect value={rel} onChange={(e) => setRel(e.target.value)}>
          {['duplicate', 'supersedes', 'see_also'].map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </ModalSelect>
      </FormRow>
      <FormRow label={t('dbeditor.aliases.noteFull')}>
        <ModalTextArea
          rows={2} placeholder={t('dbeditor.aliases.notePlaceholder')}
          value={note} onChange={(e) => setNote(e.target.value)}
        />
      </FormRow>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
        <Button variant="ghost" size="sm" onClick={onClose}>{t('dbeditor.cancel')}</Button>
        <Button variant="primary" size="sm" onClick={submit}>{t('dbeditor.ok')}</Button>
      </div>
    </Modal>
  )
}

// ── SqlQueryPanel ─────────────────────────────────────────────────────────────

interface SqlResult {
  columns: string[]
  rows: unknown[][]
  row_count?: number
  rows_affected?: number
  truncated?: boolean
  error?: string
}

function SqlQueryPanel({ db }: { db: 'losslessbob' | 'batchverify' }) {
  const { t } = useTranslation()
  const [sql, setSql]           = useState('')
  const [running, setRunning]   = useState(false)
  const [result, setResult]     = useState<SqlResult | null>(null)

  async function runQuery() {
    if (!sql.trim()) return
    setRunning(true)
    setResult(null)
    try {
      const resp = await fetch(`${BASE}/api/dbedit/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql: sql.trim(), limit: 500, db }),
      })
      const data: SqlResult = await resp.json()
      setResult(data)
    } catch (e) {
      setResult({ columns: [], rows: [], error: String(e) })
    } finally {
      setRunning(false)
    }
  }

  function statusLine(): string {
    if (!result) return ''
    if (result.error) return t('dbeditor.query.error', { msg: result.error })
    if (result.rows_affected !== undefined) return t('dbeditor.query.affected', { count: result.rows_affected })
    if (!result.columns?.length) return t('dbeditor.query.noResults')
    const base = t('dbeditor.query.rows', { count: result.row_count ?? result.rows.length })
    return result.truncated ? base + ' ' + t('dbeditor.query.truncated') : base
  }

  const statusColor = result?.error ? 'var(--lbb-bad-fg)' : 'var(--lbb-ok-fg)'

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      borderTop: '1px solid var(--lbb-border)',
    }}>
      {/* Input row */}
      <div style={{ display: 'flex', gap: 6, padding: '6px 12px', flexShrink: 0, alignItems: 'flex-end' }}>
        <textarea
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); runQuery() }
          }}
          placeholder={t('dbeditor.query.placeholder')}
          rows={3}
          spellCheck={false}
          style={{
            flex: 1, padding: '5px 8px', borderRadius: 6, fontSize: 'var(--lbb-fs-12)',
            background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
            color: 'var(--lbb-fg)', fontFamily: 'var(--lbb-mono)', resize: 'none',
          }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <button
            type="button"
            onClick={runQuery}
            disabled={running || !sql.trim()}
            style={{
              padding: '5px 14px', borderRadius: 6, fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-accent-mid)', border: 'none',
              color: 'var(--lbb-accent-onMid)',
              cursor: (running || !sql.trim()) ? 'not-allowed' : 'pointer',
              fontFamily: 'inherit', fontWeight: 600,
            }}
          >
            {running ? '…' : t('dbeditor.query.run')}
          </button>
          <button
            type="button"
            onClick={() => { setSql(''); setResult(null) }}
            style={{
              padding: '5px 14px', borderRadius: 6, fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              color: 'var(--lbb-fg)', cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {t('dbeditor.query.clear')}
          </button>
        </div>
      </div>

      {/* Status */}
      {result && (
        <div style={{
          padding: '2px 12px 4px', fontSize: 'var(--lbb-fs-11-5)', flexShrink: 0,
          color: statusColor, fontFamily: 'var(--lbb-mono)',
        }}>
          {statusLine()}
        </div>
      )}

      {/* Results table */}
      {result && result.columns.length > 0 && (
        <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--lbb-fs-11-5)', fontFamily: 'var(--lbb-mono)' }}>
            <thead>
              <tr>
                {result.columns.map((col, i) => (
                  <th key={i} style={{
                    padding: '4px 8px', textAlign: 'left', fontWeight: 700, fontSize: 'var(--lbb-fs-11)',
                    color: 'var(--lbb-fg3)', borderBottom: '2px solid var(--lbb-border)',
                    background: 'var(--lbb-surface)', position: 'sticky', top: 0, whiteSpace: 'nowrap',
                  }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, ri) => (
                <tr key={ri} style={{ background: ri % 2 === 0 ? 'transparent' : 'var(--lbb-surface2)' }}>
                  {(row as unknown[]).map((cell, ci) => (
                    <td key={ci} style={{
                      padding: '3px 8px', borderBottom: '1px solid var(--lbb-border)',
                      color: 'var(--lbb-fg)', maxWidth: 300,
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {cell === null ? <em style={{ color: 'var(--lbb-fg3)' }}>NULL</em> : String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── ScreenDbEditor ────────────────────────────────────────────────────────────

type DirtyKey = `${number}_${number}`

export function ScreenDbEditor() {
  const { t } = useTranslation()

  // Database selector
  const [activeDb, setActiveDb] = useState<'losslessbob' | 'batchverify'>('losslessbob')

  // Table list state
  const [tableMeta, setTableMeta] = useState<Record<string, TableMeta>>({})
  const [tableList, setTableList] = useState<string[]>([])
  const [currentTable, setCurrentTable] = useState('')

  // Schema / rows
  const [schema, setSchema]     = useState<ColumnDef[]>([])
  const [columns, setColumns]   = useState<string[]>([])
  const [rows, setRows]         = useState<unknown[][]>([])
  const [rowids, setRowids]     = useState<number[]>([])
  const [total, setTotal]       = useState(0)
  const [page, setPage]         = useState(0)
  const [limit, setLimit]       = useState(100)
  const [search, setSearch]     = useState('')
  const [lbFilter, setLbFilter] = useState('')
  const [sortCol, setSortCol]   = useState('')
  const [sortDir, setSortDir]   = useState<'asc' | 'desc'>('asc')
  const [loading, setLoading]   = useState(false)
  const [status, setStatus]     = useState('')

  // Inline editing
  const [dirty, setDirty]       = useState<Record<DirtyKey, string>>({})
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [editCell, setEditCell] = useState<{ row: number; col: number } | null>(null)
  const [editValue, setEditValue] = useState('')
  const editInputRef = useRef<HTMLInputElement>(null)

  // Integrity panel
  const [integrityStats, setIntegrityStats] = useState<IntegrityStats | null>(null)
  const [integrityCollapsed, setIntegrityCollapsed] = useState(false)

  // Aliases panel
  const [aliases, setAliases]       = useState<LbAlias[]>([])
  const [isCurator, setIsCurator]   = useState(false)
  const [aliasStatus, setAliasStatus] = useState('')
  const [aliasCollapsed, setAliasCollapsed] = useState(false)

  // SQL query panel
  const [sqlPanelOpen, setSqlPanelOpen] = useState(false)

  // Modal state
  const [showAddOverride, setShowAddOverride]     = useState(false)
  const [showRemoveOverride, setShowRemoveOverride] = useState(false)
  const [showAddAlias, setShowAddAlias]           = useState(false)

  // Toast
  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null)
  const showToast = useCallback((msg: string, tone: ToastTone = 'ok') => setToast({ msg, tone }), [])

  // ── Load tables on mount ──────────────────────────────────────────────────

  useEffect(() => {
    loadTables()
    loadIntegrityStats()
    checkCurator()
    loadAliases()
  }, [])

  function loadTables(db = activeDb) {
    fetch(`${BASE}/api/dbedit/tables?db=${db}`)
      .then((r) => r.json())
      .then((data: TableMeta[]) => {
        if (!Array.isArray(data)) return
        const meta: Record<string, TableMeta> = {}
        const names: string[] = []
        for (const t of data) {
          meta[t.name] = t
          names.push(t.name)
        }
        setTableMeta(meta)
        setTableList(names)
      })
      .catch(() => setStatus(t('dbeditor.error.loadTables')))
  }

  function switchDb(db: 'losslessbob' | 'batchverify') {
    setActiveDb(db)
    setCurrentTable('')
    setTableList([])
    setTableMeta({})
    setRows([])
    setColumns([])
    setSchema([])
    setTotal(0)
    setPage(0)
    setSearch('')
    setLbFilter('')
    setDirty({})
    setSelected(new Set())
    setStatus('')
    loadTables(db)
  }

  // ── Table selection ───────────────────────────────────────────────────────

  function selectTable(name: string) {
    setCurrentTable(name)
    setPage(0)
    setDirty({})
    setSelected(new Set())
    setSearch('')
    setLbFilter('')
    setSortCol('')
    setSortDir('asc')
    setEditCell(null)
    loadSchema(name)
    loadRows(name, 0, 100, '', '', '', 'asc')
  }

  // ── Schema ────────────────────────────────────────────────────────────────

  function loadSchema(name: string) {
    fetch(`${BASE}/api/dbedit/table/${encodeURIComponent(name)}/schema?db=${activeDb}`)
      .then((r) => r.json())
      .then((data: ColumnDef[]) => {
        if (Array.isArray(data)) setSchema(data)
      })
      .catch(() => {})
  }

  // ── Rows ──────────────────────────────────────────────────────────────────

  function loadRows(
    table = currentTable,
    pg    = page,
    lim   = limit,
    srch  = search,
    lb    = lbFilter,
    sc    = sortCol,
    sd    = sortDir,
  ) {
    if (!table) return
    setLoading(true)
    let url = `${BASE}/api/dbedit/table/${encodeURIComponent(table)}/rows?page=${pg}&limit=${lim}&db=${activeDb}`
    if (srch) url += `&search=${encodeURIComponent(srch)}`
    if (lb)   url += `&lb_number=${encodeURIComponent(lb)}`
    if (sc)   url += `&sort_col=${encodeURIComponent(sc)}&sort_dir=${sd}`

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        if (data.error) { setStatus(`Error: ${data.error}`); return }
        setColumns(data.columns ?? [])
        setRows(data.rows ?? [])
        setRowids((data.rows ?? []).map((r: unknown[]) => r[0] as number))
        setTotal(data.total ?? 0)
        setDirty({})
        setSelected(new Set())
        setStatus(t('dbeditor.status.rows', { count: (data.total ?? 0).toLocaleString() }))
      })
      .catch((e) => setStatus(`Error: ${e}`))
      .finally(() => setLoading(false))
  }

  function doSearch() {
    setPage(0)
    setSelected(new Set())
    loadRows(currentTable, 0, limit, search, lbFilter, sortCol, sortDir)
  }

  function onLoadAll() {
    if (!currentTable) { setStatus(t('dbeditor.status.selectTable')); return }
    setSearch('')
    setLbFilter('')
    setPage(0)
    setSortCol('')
    setSortDir('asc')
    loadRows(currentTable, 0, limit, '', '', '', 'asc')
  }

  function onLimitChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const lim = parseInt(e.target.value, 10)
    setLimit(lim)
    setPage(0)
    loadRows(currentTable, 0, lim, search, lbFilter, sortCol, sortDir)
  }

  function prevPage() {
    if (page > 0) {
      const np = page - 1
      setPage(np)
      loadRows(currentTable, np, limit, search, lbFilter, sortCol, sortDir)
    }
  }

  function nextPage() {
    const pages = Math.max(1, Math.ceil(total / limit))
    if (page < pages - 1) {
      const np = page + 1
      setPage(np)
      loadRows(currentTable, np, limit, search, lbFilter, sortCol, sortDir)
    }
  }

  // ── Sorting ───────────────────────────────────────────────────────────────

  function onSortHeader(colIdx: number) {
    if (!columns.length || colIdx === 0) return
    const colName = columns[colIdx]
    const newDir: 'asc' | 'desc' =
      sortCol === colName ? (sortDir === 'asc' ? 'desc' : 'asc') : 'asc'
    setSortCol(colName)
    setSortDir(newDir)
    setPage(0)
    loadRows(currentTable, 0, limit, search, lbFilter, colName, newDir)
  }

  // ── Inline editing ────────────────────────────────────────────────────────

  function onCellDoubleClick(rowIdx: number, colIdx: number) {
    if (colIdx === 0) return
    const meta = tableMeta[currentTable]
    if (meta?.readonly || meta?.audit) return
    const val = rows[rowIdx]?.[colIdx]
    setEditCell({ row: rowIdx, col: colIdx })
    setEditValue(val === null || val === undefined ? '' : String(val))
    setTimeout(() => editInputRef.current?.focus(), 0)
  }

  function commitEditCell() {
    if (!editCell) return
    const { row, col } = editCell
    const key: DirtyKey = `${row}_${col}`
    const original = rows[row]?.[col]
    const origStr = original === null || original === undefined ? '' : String(original)
    if (editValue !== origStr) {
      setDirty((prev) => ({ ...prev, [key]: editValue }))
    } else {
      setDirty((prev) => { const n = { ...prev }; delete n[key]; return n })
    }
    setEditCell(null)
  }

  function cancelEditCell() {
    setEditCell(null)
  }

  function onEditKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter')  { commitEditCell() }
    if (e.key === 'Escape') { cancelEditCell() }
  }

  // ── Commit / Discard ──────────────────────────────────────────────────────

  async function commitChanges() {
    if (!Object.keys(dirty).length) return
    const byRow: Record<number, Record<string, string>> = {}
    for (const [key, val] of Object.entries(dirty)) {
      const [r, c] = key.split('_').map(Number)
      if (!byRow[r]) byRow[r] = {}
      byRow[r][columns[c]] = val
    }
    let errors = 0
    for (const [rStr, updates] of Object.entries(byRow)) {
      const rowid = rowids[Number(rStr)]
      try {
        const resp = await fetch(
          `${BASE}/api/dbedit/table/${encodeURIComponent(currentTable)}/row?db=${activeDb}`,
          { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rowid, updates }) }
        ).then((r) => r.json())
        if (resp.error) errors++
      } catch { errors++ }
    }
    if (errors) {
      showToast(t('dbeditor.status.commitErrors', { count: errors }), 'bad')
    } else {
      showToast(t('dbeditor.status.committed', { count: Object.keys(byRow).length }), 'ok')
    }
    loadRows()
  }

  function discardChanges() {
    setDirty({})
    loadRows()
  }

  // ── Delete ────────────────────────────────────────────────────────────────

  function deleteSelected() {
    if (!selected.size) { setStatus(t('dbeditor.status.selectRows')); return }
    const meta = tableMeta[currentTable]
    if (meta?.readonly) { setStatus(t('dbeditor.status.readOnly')); return }

    let msg = t('dbeditor.delete.confirm', { count: selected.size, table: currentTable })
    if (meta?.warn) msg += '\n\n' + t('dbeditor.delete.coreWarning')
    if (!window.confirm(msg)) return

    const ids = [...selected].map((r) => rowids[r])
    fetch(`${BASE}/api/dbedit/table/${encodeURIComponent(currentTable)}/rows?db=${activeDb}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rowids: ids }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          showToast(`Error: ${data.error}`, 'bad')
        } else {
          showToast(t('dbeditor.status.deleted', { count: data.deleted ?? 0 }), 'ok')
          loadRows()
        }
      })
      .catch((e) => showToast(`Error: ${e}`, 'bad'))
  }

  // ── Export CSV ────────────────────────────────────────────────────────────

  async function exportCsv() {
    if (!currentTable) return
    try {
      const resp = await fetch(
        `${BASE}/api/dbedit/table/${encodeURIComponent(currentTable)}/export?db=${activeDb}`
      )
      const text = await resp.text()
      const ok = await window.api.saveFile(text, `${currentTable}.csv`)
      if (ok) showToast(t('dbeditor.status.exported', { table: currentTable }), 'ok')
    } catch (e) {
      showToast(`Export error: ${e}`, 'bad')
    }
  }

  // ── DB Integrity ──────────────────────────────────────────────────────────

  function loadIntegrityStats() {
    fetch(`${BASE}/api/lb_master/stats`)
      .then((r) => r.json())
      .then((data: IntegrityStats) => {
        if (data && typeof data.public === 'number') setIntegrityStats(data)
      })
      .catch(() => {})
  }

  function reconcileAll() {
    if (!window.confirm(t('dbeditor.integrity.reconcileConfirm'))) return
    setStatus(t('dbeditor.integrity.reconciling'))
    fetch(`${BASE}/api/lb_master/reconcile`, { method: 'POST' })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          if (data.stats) setIntegrityStats(data.stats)
          showToast(t('dbeditor.integrity.reconcileDone'), 'ok')
        } else {
          showToast(`Error: ${data.error || 'unknown'}`, 'bad')
        }
      })
      .catch((e) => showToast(`Error: ${e}`, 'bad'))
  }

  function showNeedsReview() {
    if (!tableList.includes('lb_master')) return
    setCurrentTable('lb_master')
    setSearch('needs_review:1')
    setLbFilter('')
    setPage(0)
    setSortCol('')
    setSortDir('asc')
    loadSchema('lb_master')
    loadRows('lb_master', 0, limit, 'needs_review:1', '', '', 'asc')
  }

  function addOverride(lb: number, ovStatus: string, notes: string) {
    fetch(`${BASE}/api/lb_master/${lb}/manual`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: ovStatus, notes }),
    })
      .then((r) => r.json())
      .then(() => {
        showToast(
          t('dbeditor.integrity.overrideSet', { lb: String(lb).padStart(5, '0'), status: ovStatus }),
          'ok'
        )
        loadIntegrityStats()
      })
      .catch((e) => showToast(`Error: ${e}`, 'bad'))
  }

  function removeOverride(lb: number) {
    if (!window.confirm(t('dbeditor.integrity.removeOverrideConfirm', {
      lb: String(lb).padStart(5, '0')
    }))) return
    fetch(`${BASE}/api/lb_master/${lb}/manual`, { method: 'DELETE' })
      .then((r) => r.json())
      .then((data) => {
        showToast(
          t('dbeditor.integrity.overrideCleared', {
            lb: String(lb).padStart(5, '0'), status: data.lb_status ?? '?'
          }),
          'ok'
        )
        loadIntegrityStats()
      })
      .catch((e) => showToast(`Error: ${e}`, 'bad'))
  }

  async function exportOverrides() {
    try {
      const data = await fetch(`${BASE}/api/lb_master/overrides/export`).then((r) => r.json())
      const json = JSON.stringify(data, null, 2)
      const ok = await window.api.saveFile(json, 'lb_overrides.json')
      if (ok) showToast(t('dbeditor.integrity.exportedOverrides', { count: data.length }), 'ok')
    } catch (e) {
      showToast(`Export error: ${e}`, 'bad')
    }
  }

  async function importOverrides() {
    const content = await window.api.pickAndReadFile({
      title: t('dbeditor.integrity.importTitle'),
      filters: [{ name: 'JSON', extensions: ['json'] }],
    })
    if (!content) return
    let payload: unknown[]
    try {
      payload = JSON.parse(content)
      if (!Array.isArray(payload)) throw new Error('not array')
    } catch {
      showToast(t('dbeditor.integrity.importInvalid'), 'bad')
      return
    }
    if (!window.confirm(t('dbeditor.integrity.importConfirm', { count: payload.length }))) return
    fetch(`${BASE}/api/lb_master/overrides/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json())
      .then((data) => {
        showToast(
          t('dbeditor.integrity.importDone', {
            imported: data.imported ?? 0, skipped: data.skipped ?? 0
          }),
          'ok'
        )
        loadIntegrityStats()
      })
      .catch((e) => showToast(`Error: ${e}`, 'bad'))
  }

  function backupDb() {
    fetch(`${BASE}/api/db/backup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'manual' }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          const mb = ((data.size_bytes ?? 0) / 1_048_576).toFixed(1)
          showToast(t('dbeditor.integrity.backupDone', { path: data.path ?? '?', mb }), 'ok')
        } else {
          showToast(`Backup error: ${data.error || 'unknown'}`, 'bad')
        }
      })
      .catch((e) => showToast(`Error: ${e}`, 'bad'))
  }

  // ── Curator check ─────────────────────────────────────────────────────────

  function checkCurator() {
    fetch(`${BASE}/api/curator`)
      .then((r) => r.json())
      .then((d) => setIsCurator(!!d.is_curator))
      .catch(() => setIsCurator(false))
  }

  // ── Aliases ───────────────────────────────────────────────────────────────

  function loadAliases() {
    fetch(`${BASE}/api/lb_alias`)
      .then((r) => r.json())
      .then((data: LbAlias[]) => {
        if (Array.isArray(data)) {
          setAliases(data)
          setAliasStatus(
            t('dbeditor.aliases.count', { count: data.length }) +
            (isCurator ? '' : t('dbeditor.aliases.readOnly'))
          )
        }
      })
      .catch((e) => setAliasStatus(`Error: ${e}`))
  }

  function addAlias(payload: {
    alias_lb: number; canonical_lb: number; relationship: string; note: string
  }) {
    fetch(`${BASE}/api/lb_alias`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.error) {
          setAliasStatus(`Error: ${data.error}`)
        } else {
          const suffix = data.rewrote_chain ? t('dbeditor.aliases.chainRewritten') : ''
          setAliasStatus(
            t('dbeditor.aliases.saved', {
              alias: String(payload.alias_lb).padStart(5, '0'),
              canon: String(data.canonical_lb ?? payload.canonical_lb).padStart(5, '0'),
              suffix,
            })
          )
          loadAliases()
        }
      })
      .catch((e) => setAliasStatus(`Error: ${e}`))
  }

  function deleteAlias(aliasLb: number) {
    if (!window.confirm(t('dbeditor.aliases.deleteConfirm', {
      lb: String(aliasLb).padStart(5, '0')
    }))) return
    fetch(`${BASE}/api/lb_alias/${aliasLb}`, { method: 'DELETE' })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          setAliasStatus(t('dbeditor.aliases.removed', { lb: String(aliasLb).padStart(5, '0') }))
          loadAliases()
        } else {
          setAliasStatus(`Error: ${data.error || 'unknown'}`)
        }
      })
      .catch((e) => setAliasStatus(`Error: ${e}`))
  }

  // ── Derived ───────────────────────────────────────────────────────────────

  const pages      = Math.max(1, Math.ceil(total / limit))
  const hasDirty   = Object.keys(dirty).length > 0
  const meta       = tableMeta[currentTable]
  const isEditable = !!currentTable && !meta?.readonly && !meta?.audit

  const schemaStr = schema.map((c) => {
    let s = `${c.name} ${c.type ?? ''}`
    if (c.pk)      s += ' [PK]'
    if (c.notnull) s += ' NOT NULL'
    return s
  }).join('  |  ')

  function tableLabel() {
    if (!currentTable) return t('dbeditor.selectTable')
    let lbl = currentTable
    if (meta?.readonly) lbl += ' ' + t('dbeditor.readOnly')
    if (meta?.audit)    lbl += ' ' + t('dbeditor.auditOnly')
    if (meta?.warn)     lbl += ' — ' + t('dbeditor.coreWarning')
    return lbl
  }

  function rowBackground(rowIdx: number): string {
    if (selected.has(rowIdx)) return 'var(--lbb-accent-soft)'
    if (meta?.warn)     return 'color-mix(in oklab, var(--lbb-warn-bg) 40%, transparent)'
    if (meta?.audit)    return 'color-mix(in oklab, var(--lbb-info-bg) 40%, transparent)'
    if (meta?.readonly) return 'var(--lbb-surface2)'
    return 'transparent'
  }

  function cellBackground(rowIdx: number, colIdx: number): string {
    const key: DirtyKey = `${rowIdx}_${colIdx}`
    if (key in dirty) return 'color-mix(in oklab, var(--lbb-warn-bg) 60%, transparent)'
    return 'transparent'
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden', fontFamily: 'inherit' }}>

      {/* ── Left sidebar ─────────────────────────────────────────────────── */}
      <div style={{
        width: 230, flexShrink: 0, display: 'flex', flexDirection: 'column',
        borderRight: '1px solid var(--lbb-border)', overflowY: 'auto',
        background: 'var(--lbb-surface)',
      }}>
        {/* DB selector */}
        <div style={{ display: 'flex', padding: '8px 8px 0', gap: 4 }}>
          {(['losslessbob', 'batchverify'] as const).map((db) => (
            <button
              key={db}
              type="button"
              onClick={() => switchDb(db)}
              style={{
                flex: 1, padding: '4px 6px', borderRadius: 5, fontSize: 'var(--lbb-fs-10-5)',
                fontFamily: 'inherit', cursor: 'pointer',
                background: activeDb === db ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface2)',
                border: `1px solid ${activeDb === db ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                color: activeDb === db ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)',
                fontWeight: activeDb === db ? 700 : 500,
              }}
            >
              {db === 'losslessbob' ? 'losslessbob' : 'batch_verify'}
            </button>
          ))}
        </div>

        {/* Table list */}
        <div style={{ padding: '10px 8px 4px' }}>
          <div style={{
            fontSize: 'var(--lbb-fs-10)', fontWeight: 700, textTransform: 'uppercase',
            letterSpacing: 0.1, color: 'var(--lbb-fg3)', marginBottom: 4, paddingLeft: 4,
          }}>
            {t('dbeditor.tables')}
          </div>
          <div style={{ maxHeight: 260, overflowY: 'auto', marginBottom: 4 }}>
            {tableList.map((name) => {
              const m = tableMeta[name]
              const labelColor =
                m?.readonly ? 'var(--lbb-fg3)' :
                m?.warn     ? 'var(--lbb-bad-fg)' :
                m?.audit    ? 'var(--lbb-info-fg)' :
                'var(--lbb-fg)'
              const countStr = typeof m?.row_count === 'number' && m.row_count >= 0
                ? ` (${m.row_count.toLocaleString()})`
                : ''
              return (
                <button
                  key={name}
                  type="button"
                  onClick={() => selectTable(name)}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '5px 8px', borderRadius: 5, fontSize: 'var(--lbb-fs-11-5)',
                    background: currentTable === name ? 'var(--lbb-accent-soft)' : 'transparent',
                    border: '1px solid transparent',
                    color: currentTable === name ? 'var(--lbb-accent-mid)' : labelColor,
                    fontWeight: currentTable === name ? 600 : 500,
                    cursor: 'pointer', fontFamily: 'inherit', marginBottom: 1,
                  }}
                >
                  {name}{countStr}
                </button>
              )
            })}
            {tableList.length === 0 && (
              <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', padding: '4px 8px' }}>—</div>
            )}
          </div>
          <button
            type="button"
            onClick={() => { loadTables(); if (activeDb === 'losslessbob') { loadIntegrityStats(); loadAliases() } }}
            style={{
              width: '100%', padding: '4px 8px', borderRadius: 5, fontSize: 'var(--lbb-fs-11)',
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              color: 'var(--lbb-fg)', cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {t('dbeditor.refresh')}
          </button>
        </div>

        {activeDb === 'losslessbob' && (
          <>
            {/* DB Integrity */}
            <SideSection
              title={t('dbeditor.integrity.title')}
              collapsed={integrityCollapsed}
              onToggle={() => setIntegrityCollapsed((v) => !v)}
            >
              <IntegrityPanel
                stats={integrityStats}
                onReconcile={reconcileAll}
                onShowNeedsReview={showNeedsReview}
                onAddOverride={() => setShowAddOverride(true)}
                onRemoveOverride={() => setShowRemoveOverride(true)}
                onExportOverrides={exportOverrides}
                onImportOverrides={importOverrides}
                onBackup={backupDb}
              />
            </SideSection>

            {/* LB Aliases */}
            <SideSection
              title={t('dbeditor.aliases.title')}
              collapsed={aliasCollapsed}
              onToggle={() => setAliasCollapsed((v) => !v)}
            >
              <AliasPanel
                aliases={aliases}
                isCurator={isCurator}
                status={aliasStatus}
                onAdd={() => setShowAddAlias(true)}
                onDelete={deleteAlias}
                onReload={loadAliases}
              />
            </SideSection>
          </>
        )}

        <div style={{ flex: 1 }} />
      </div>

      {/* ── Right main area ──────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Toolbar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
          padding: '8px 12px', borderBottom: '1px solid var(--lbb-border)',
          background: 'var(--lbb-surface)', flexShrink: 0,
        }}>
          <span style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 700, color: 'var(--lbb-fg)', flex: 1, minWidth: 0 }}>
            {tableLabel()}
          </span>
          <button
            type="button"
            onClick={onLoadAll}
            style={{
              padding: '5px 10px', borderRadius: 6, fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              color: 'var(--lbb-fg)', cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {t('dbeditor.loadRecords')}
          </button>
          <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>{t('dbeditor.lbFilter')}</span>
          <input
            type="text"
            value={lbFilter}
            onChange={(e) => setLbFilter(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doSearch()}
            placeholder="e.g. 1797"
            style={{
              width: 70, padding: '5px 7px', borderRadius: 6, fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              color: 'var(--lbb-fg)', fontFamily: 'inherit',
            }}
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doSearch()}
            placeholder={t('dbeditor.searchPlaceholder')}
            style={{
              width: 200, padding: '5px 7px', borderRadius: 6, fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              color: 'var(--lbb-fg)', fontFamily: 'inherit',
            }}
          />
          <button
            type="button"
            onClick={doSearch}
            style={{
              padding: '5px 10px', borderRadius: 6, fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-accent-mid)', border: 'none',
              color: 'var(--lbb-accent-onMid)', cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            {t('dbeditor.search')}
          </button>
        </div>

        {/* Schema strip */}
        {schemaStr && (
          <div style={{
            padding: '3px 12px', fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)',
            borderBottom: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)',
            fontFamily: 'var(--lbb-mono)', whiteSpace: 'nowrap', overflowX: 'auto', flexShrink: 0,
          }}>
            {schemaStr}
          </div>
        )}

        {/* Data table */}
        <div style={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
          {loading && (
            <div style={{ padding: 16, color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
              {t('dbeditor.loading')}
            </div>
          )}
          {!loading && rows.length > 0 && (
            <table style={{
              width: '100%', borderCollapse: 'collapse', fontSize: 'var(--lbb-fs-12)',
              fontFamily: 'var(--lbb-mono)',
            }}>
              <thead>
                <tr>
                  {columns.map((col, ci) => (
                    <th
                      key={ci}
                      onClick={() => onSortHeader(ci)}
                      style={{
                        padding: '6px 10px', textAlign: 'left', fontWeight: 700,
                        fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)',
                        borderBottom: '2px solid var(--lbb-border)',
                        background: 'var(--lbb-surface)',
                        position: 'sticky', top: 0, zIndex: 1,
                        cursor: ci > 0 ? 'pointer' : 'default',
                        whiteSpace: 'nowrap',
                        userSelect: 'none',
                      }}
                    >
                      {col}
                      {sortCol === col && (
                        <span style={{ marginLeft: 4, fontSize: 'var(--lbb-fs-9)' }}>
                          {sortDir === 'asc' ? '▲' : '▼'}
                        </span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, ri) => (
                  <tr
                    key={ri}
                    onClick={() => setSelected((prev) => {
                      const next = new Set(prev)
                      if (next.has(ri)) next.delete(ri); else next.add(ri)
                      return next
                    })}
                    style={{ background: rowBackground(ri), cursor: 'pointer' }}
                  >
                    {(row as unknown[]).map((cell, ci) => {
                      const isEdit = editCell?.row === ri && editCell?.col === ci
                      const isDirty = (`${ri}_${ci}` as DirtyKey) in dirty
                      const displayVal = isDirty
                        ? dirty[`${ri}_${ci}` as DirtyKey]
                        : (cell === null || cell === undefined ? '' : String(cell))
                      return (
                        <td
                          key={ci}
                          onDoubleClick={() => onCellDoubleClick(ri, ci)}
                          style={{
                            padding: '4px 10px',
                            borderBottom: '1px solid var(--lbb-border)',
                            color: ci === 0 ? 'var(--lbb-fg3)' : 'var(--lbb-fg)',
                            background: isEdit
                              ? 'var(--lbb-accent-soft)'
                              : isDirty
                              ? 'color-mix(in oklab, var(--lbb-warn-bg) 70%, transparent)'
                              : cellBackground(ri, ci),
                            maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {isEdit && isEditable ? (
                            <input
                              ref={editInputRef}
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onBlur={commitEditCell}
                              onKeyDown={onEditKeyDown}
                              style={{
                                width: '100%', padding: '1px 4px', fontSize: 'var(--lbb-fs-12)',
                                background: 'var(--lbb-bg)', border: '1px solid var(--lbb-accent-mid)',
                                borderRadius: 3, color: 'var(--lbb-fg)', fontFamily: 'var(--lbb-mono)',
                                boxSizing: 'border-box',
                              }}
                            />
                          ) : (
                            displayVal
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!loading && rows.length === 0 && currentTable && (
            <div style={{ padding: 20, color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
              {t('dbeditor.noRows')}
            </div>
          )}
        </div>

        {currentTable && (<>
        {/* Pagination row */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
          borderTop: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)', flexShrink: 0,
        }}>
          <button
            type="button"
            onClick={prevPage}
            disabled={page === 0}
            style={{
              padding: '4px 10px', borderRadius: 5, fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              color: page === 0 ? 'var(--lbb-fg3)' : 'var(--lbb-fg)',
              cursor: page === 0 ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
            }}
          >
            {t('dbeditor.prev')}
          </button>
          <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', minWidth: 140 }}>
            {t('dbeditor.pageInfo', {
              page: page + 1, pages, total: total.toLocaleString()
            })}
          </span>
          <button
            type="button"
            onClick={nextPage}
            disabled={page >= pages - 1}
            style={{
              padding: '4px 10px', borderRadius: 5, fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              color: page >= pages - 1 ? 'var(--lbb-fg3)' : 'var(--lbb-fg)',
              cursor: page >= pages - 1 ? 'not-allowed' : 'pointer', fontFamily: 'inherit',
            }}
          >
            {t('dbeditor.next')}
          </button>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>{t('dbeditor.rowsPerPage')}</span>
          <select
            value={limit}
            onChange={onLimitChange}
            style={{
              padding: '3px 6px', borderRadius: 5, fontSize: 'var(--lbb-fs-12)',
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              color: 'var(--lbb-fg)', fontFamily: 'inherit',
            }}
          >
            {[50, 100, 200, 500].map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </div>

        {/* Action row */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
          borderTop: '1px solid var(--lbb-border)', background: 'var(--lbb-surface)', flexShrink: 0,
        }}>
          <Button
            variant="primary" size="sm"
            onClick={commitChanges}
            disabled={!hasDirty}
          >
            {t('dbeditor.commitChanges')}
          </Button>
          <Button
            variant="ghost" size="sm"
            onClick={discardChanges}
            disabled={!hasDirty}
          >
            {t('dbeditor.discardChanges')}
          </Button>
          <Button variant="danger" size="sm" onClick={deleteSelected}>
            {t('dbeditor.deleteSelected')}
          </Button>
          <Button variant="secondary" size="sm" onClick={exportCsv}>
            {t('dbeditor.exportCsv')}
          </Button>
          <Button
            variant="ghost" size="sm"
            onClick={() => setSqlPanelOpen((v) => !v)}
          >
            {t('dbeditor.query.toggle')}
          </Button>
          {hasDirty && (
            <Pill tone="warn" soft>
              {t('dbeditor.dirtyCount', { count: Object.keys(dirty).length })}
            </Pill>
          )}
          <div style={{ flex: 1 }} />
          {status && (
            <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>
              {status}
            </span>
          )}
        </div>
        </>)}

        {/* SQL Query panel */}
        {currentTable && sqlPanelOpen && (
          <div style={{ height: 280, flexShrink: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <SqlQueryPanel db={activeDb} />
          </div>
        )}
      </div>

      {/* ── Modals ───────────────────────────────────────────────────────── */}

      {showAddOverride && (
        <AddOverrideModal
          onClose={() => setShowAddOverride(false)}
          onConfirm={addOverride}
        />
      )}
      {showRemoveOverride && (
        <RemoveOverrideModal
          onClose={() => setShowRemoveOverride(false)}
          onConfirm={removeOverride}
        />
      )}
      {showAddAlias && (
        <AddAliasModal
          onClose={() => setShowAddAlias(false)}
          onConfirm={addAlias}
        />
      )}

      {toast && <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />}
    </div>
  )
}
