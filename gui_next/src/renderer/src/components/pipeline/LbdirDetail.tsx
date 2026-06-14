import React, { useCallback, useState } from 'react'
import { Icon } from '../Icon'
import { Button, Pill, TableShell, TH, TR, TD } from '../index'
import { CheckFile, CheckResult, ReconcileResult, SiteProposal } from '../../lib/lbdirStore'

// ── CheckDot ──────────────────────────────────────────────────────────────────

export function CheckDot({ s }: { s: CheckFile['md5_status'] }): React.JSX.Element {
  if (s === 'pass') return <Icon name="check" size={12} style={{ color: 'var(--lbb-ok-bar)' }} />
  if (s === 'miss') return <Icon name="x"     size={12} style={{ color: 'var(--lbb-warn-fg)' }} />
  return <span style={{ color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)' }}>na</span>
}

// ── File table ────────────────────────────────────────────────────────────────

const DEFAULT_FILE_COL_WIDTHS = { filename: 260, md5: 50, disk: 60, overall: 80, length: 80, fmt: 60, ratio: 70 }

export interface LbdirFileTableProps {
  files: CheckFile[]
}

/** Per-file table with resizable columns — harvested from ScreenLBDIR. See design doc 14 §2.4. */
export function LbdirFileTable({ files }: LbdirFileTableProps): React.JSX.Element {
  const [colWidths, setColWidths] = useState(DEFAULT_FILE_COL_WIDTHS)

  const startResize = useCallback((key: keyof typeof DEFAULT_FILE_COL_WIDTHS, startX: number, startW: number) => {
    const onMove = (e: MouseEvent) => {
      const newW = Math.max(36, startW + e.clientX - startX)
      setColWidths(ws => ({ ...ws, [key]: newW }))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [])

  return (
    <TableShell>
      <colgroup>
        <col style={{ width: 3 }} />
        <col style={{ width: colWidths.filename }} />
        <col style={{ width: colWidths.md5 }} />
        <col style={{ width: colWidths.disk }} />
        <col style={{ width: colWidths.overall }} />
        <col style={{ width: colWidths.length }} />
        <col style={{ width: colWidths.fmt }} />
        <col style={{ width: colWidths.ratio }} />
      </colgroup>
      <thead>
        <tr>
          <TH> </TH>
          <TH onResizeStart={e => startResize('filename', e.clientX, colWidths.filename)}>Filename</TH>
          <TH align="center" onResizeStart={e => startResize('md5', e.clientX, colWidths.md5)}>MD5</TH>
          <TH align="center" onResizeStart={e => startResize('disk', e.clientX, colWidths.disk)}>Disk</TH>
          <TH onResizeStart={e => startResize('overall', e.clientX, colWidths.overall)}>Overall</TH>
          <TH align="right" onResizeStart={e => startResize('length', e.clientX, colWidths.length)}>Length</TH>
          <TH onResizeStart={e => startResize('fmt', e.clientX, colWidths.fmt)}>Fmt</TH>
          <TH align="right" onResizeStart={e => startResize('ratio', e.clientX, colWidths.ratio)}>Ratio</TH>
        </tr>
      </thead>
      <tbody>
        {files.map((f, i) => {
          const edge: 'ok' | 'warn' | 'bad' =
            f.overall === 'pass' ? 'ok' : f.overall === 'missing' || f.overall === 'extra' ? 'warn' : 'bad'
          const overallLabel =
            f.overall === 'pass' ? 'Pass' : f.overall === 'missing' ? 'Missing' : f.overall === 'extra' ? 'Extra' : 'Fail'
          return (
            <TR key={i} edge={edge}>
              <TD mono style={{ color: f.overall === 'pass' || f.overall === 'extra' ? 'var(--lbb-fg)' : 'var(--lbb-bad-fg)' }}>{f.filename}</TD>
              <TD align="center"><CheckDot s={f.md5_status} /></TD>
              <TD align="center">
                {f.on_disk
                  ? <Icon name="check" size={12} style={{ color: 'var(--lbb-ok-bar)' }} />
                  : <Icon name="x"     size={12} style={{ color: 'var(--lbb-warn-fg)' }} />}
              </TD>
              <TD><Pill tone={edge} soft>{overallLabel}</Pill></TD>
              <TD align="right" mono dim>{f.length ?? '—'}</TD>
              <TD mono dim>{f.fmt ?? '—'}</TD>
              <TD align="right" mono dim>{f.ratio ?? '—'}</TD>
            </TR>
          )
        })}
      </tbody>
    </TableShell>
  )
}

// ── Reconcile panel ────────────────────────────────────────────────────────────

export interface ReconcilePanelProps {
  result: ReconcileResult
  reconSelected: Set<string>
  setReconSelected: (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  siteSelected: Set<string>
  setSiteSelected: (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  busy: boolean
  onRescan: () => void
  onApply: () => void
  /** Tighter spacing for use inside the pipeline detail panel (no full-bleed margins). */
  compact?: boolean
}

/**
 * Reconcile proposals + extras + site/files recovery — harvested from ScreenLBDIR.
 * See design doc 14 §2.4.
 */
export function ReconcilePanel({
  result, reconSelected, setReconSelected, siteSelected, setSiteSelected, busy, onRescan, onApply, compact,
}: ReconcilePanelProps): React.JSX.Element {
  const selectedCount = result.proposals.filter(p => reconSelected.has(p.disk_rel)).length
  const extrasCount = result.unmatched_disk.length
  const siteProposals: SiteProposal[] = result.site_proposals ?? []
  const siteSelectedCount = siteProposals.filter(p => siteSelected.has(p.site_path)).length

  return (
    <div style={{
      margin: compact ? 0 : '0 24px 20px',
      borderRadius: 8,
      border: '1px solid var(--lbb-border)',
      background: 'var(--lbb-surface)',
      overflow: 'hidden',
    }}>
      {/* Panel header */}
      <div style={{
        padding: '10px 16px', background: 'var(--lbb-surface2)',
        borderBottom: '1px solid var(--lbb-border)',
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <Icon name="rename" size={13} style={{ color: 'var(--lbb-fg3)' }} />
        <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
          Reconcile
        </span>
        {result.proposals.length > 0 && (
          <Pill tone="info" soft>{result.proposals.length} rename{result.proposals.length !== 1 ? 's' : ''}</Pill>
        )}
        {extrasCount > 0 && (
          <Pill tone="warn" soft>{extrasCount} extra{extrasCount !== 1 ? 's' : ''} → /extras/</Pill>
        )}
        {siteProposals.length > 0 && (
          <Pill tone="ok" soft>{siteProposals.length} in site/files</Pill>
        )}
        <div style={{ flex: 1 }} />
        <Button variant="ghost" size="sm" disabled={busy} onClick={onRescan}>Re-scan</Button>
        <Button variant="primary" size="sm" icon="check" disabled={busy || (selectedCount === 0 && extrasCount === 0 && siteSelectedCount === 0)} onClick={onApply}>
          Apply{selectedCount > 0 ? ` ${selectedCount} rename${selectedCount !== 1 ? 's' : ''}` : ''}
          {extrasCount > 0 ? ` + move ${extrasCount} extra${extrasCount !== 1 ? 's' : ''}` : ''}
          {siteSelectedCount > 0 ? ` + copy ${siteSelectedCount} from site/files` : ''}
        </Button>
      </div>

      {/* Proposals */}
      {result.proposals.length > 0 ? (
        <div style={{ borderBottom: extrasCount > 0 ? '1px solid var(--lbb-border)' : undefined }}>
          <div style={{ padding: '8px 16px 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox"
              checked={result.proposals.length > 0 && result.proposals.every(p => reconSelected.has(p.disk_rel))}
              onChange={e => setReconSelected(e.target.checked
                ? new Set(result.proposals.map(p => p.disk_rel))
                : new Set()
              )}
            />
            <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
              Proposed renames — files found by MD5 match
            </span>
          </div>
          <TableShell style={{ margin: 0, borderRadius: 0, border: 'none' }}>
            <colgroup>
              <col style={{ width: 3 }} /><col style={{ width: 32 }} />
              <col style={{ width: 32 }} /><col /><col style={{ width: 24 }} /><col /><col style={{ width: 140 }} />
            </colgroup>
            <thead>
              <tr>
                <TH> </TH><TH> </TH>
                <TH> </TH><TH>Current path on disk</TH><TH> </TH>
                <TH>Will rename to</TH><TH>MD5</TH>
              </tr>
            </thead>
            <tbody>
              {result.proposals.map((p, i) => (
                <TR key={i} edge="info">
                  <TD> </TD>
                  <TD>
                    <input type="checkbox"
                      checked={reconSelected.has(p.disk_rel)}
                      onChange={e => setReconSelected(prev => {
                        const next = new Set(prev)
                        e.target.checked ? next.add(p.disk_rel) : next.delete(p.disk_rel)
                        return next
                      })}
                    />
                  </TD>
                  <TD mono style={{ color: 'var(--lbb-fg2)' }}>{p.disk_rel}</TD>
                  <TD align="center"><Icon name="chevRight" size={12} style={{ color: 'var(--lbb-fg3)' }} /></TD>
                  <TD mono style={{ color: 'var(--lbb-ok-fg)' }}>{p.lbdir_rel}</TD>
                  <TD mono dim>{p.md5.slice(0, 12)}…</TD>
                </TR>
              ))}
            </tbody>
          </TableShell>
        </div>
      ) : (
        <div style={{ padding: '12px 16px', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)', borderBottom: extrasCount > 0 ? '1px solid var(--lbb-border)' : undefined }}>
          No rename proposals — missing files could not be matched by MD5.
        </div>
      )}

      {/* Extras */}
      {extrasCount > 0 && (
        <div>
          <div style={{ padding: '8px 16px 4px' }}>
            <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
              Extra files — not in lbdir, will be moved to <span style={{ fontFamily: 'var(--lbb-mono)' }}>/extras/</span>
            </span>
          </div>
          <div style={{ padding: '4px 16px 12px', display: 'flex', flexDirection: 'column', gap: 3 }}>
            {result.unmatched_disk.map((f, i) => (
              <span key={i} style={{ fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-warn-fg)' }}>{f}</span>
            ))}
          </div>
        </div>
      )}

      {/* Site recovery */}
      {siteProposals.length > 0 && (
        <div style={{ borderTop: '1px solid var(--lbb-border)' }}>
          <div style={{ padding: '8px 16px 4px', display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox"
              checked={siteProposals.length > 0 && siteProposals.every(p => siteSelected.has(p.site_path))}
              onChange={e => setSiteSelected(e.target.checked
                ? new Set(siteProposals.map(p => p.site_path))
                : new Set()
              )}
            />
            <span style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
              Recoverable from site/files
            </span>
          </div>
          {siteProposals.some(p => p.matched_by === 'name') && (
            <div style={{ padding: '0 16px 8px', fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-warn-fg)' }}>
              Rows marked "MD5 mismatch" matched by filename only — the copy in site/files is a
              different revision than what this folder's lbdir expects, and won't pass MD5
              verification after copying. Review before applying.
            </div>
          )}
          <TableShell style={{ margin: 0, borderRadius: 0, border: 'none' }}>
            <colgroup>
              <col style={{ width: 3 }} /><col style={{ width: 32 }} />
              <col /><col style={{ width: 24 }} /><col /><col style={{ width: 140 }} />
            </colgroup>
            <thead>
              <tr>
                <TH> </TH><TH> </TH>
                <TH>File in site/files</TH><TH> </TH>
                <TH>Will copy to</TH><TH>MD5</TH>
              </tr>
            </thead>
            <tbody>
              {siteProposals.map((p, i) => (
                <TR key={i} edge={p.matched_by === 'name' ? 'warn' : 'ok'}>
                  <TD>
                    <input type="checkbox"
                      checked={siteSelected.has(p.site_path)}
                      onChange={e => setSiteSelected(prev => {
                        const next = new Set(prev)
                        e.target.checked ? next.add(p.site_path) : next.delete(p.site_path)
                        return next
                      })}
                    />
                  </TD>
                  <TD mono style={{ color: 'var(--lbb-fg2)' }}>{p.site_path.split('/').pop()}</TD>
                  <TD align="center"><Icon name="chevRight" size={12} style={{ color: 'var(--lbb-fg3)' }} /></TD>
                  <TD mono style={{ color: 'var(--lbb-ok-fg)' }}>{p.lbdir_rel}</TD>
                  {p.matched_by === 'name' ? (
                    <TD>
                      <span title={`site/files copy: ${p.md5.slice(0, 12)}… — folder's lbdir expects: ${p.expected_md5.slice(0, 12)}…`}>
                        <Pill tone="warn" soft>MD5 mismatch</Pill>
                      </span>
                    </TD>
                  ) : (
                    <TD mono dim>{p.md5.slice(0, 12)}…</TD>
                  )}
                </TR>
              ))}
            </tbody>
          </TableShell>
        </div>
      )}

      {result.proposals.length === 0 && extrasCount === 0 && siteProposals.length === 0 && (
        <div style={{ padding: '12px 16px', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-12)' }}>
          Nothing to reconcile for this folder.
        </div>
      )}
    </div>
  )
}

// ── LbdirDetail ───────────────────────────────────────────────────────────────

export interface LbdirDetailProps {
  checkResult: CheckResult
  reconResult: ReconcileResult | null
  reconSelected: Set<string>
  setReconSelected: (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  siteSelected: Set<string>
  setSiteSelected: (updater: Set<string> | ((prev: Set<string>) => Set<string>)) => void
  busy: boolean
  canReconcile: boolean
  onReconcile: () => void
  onApplyReconcile: () => void
  /** Tighter spacing for use inside the pipeline detail panel (no full-bleed padding). */
  compact?: boolean
}

/**
 * File table + reconcile section, shared between ScreenLBDIR and the pipeline
 * LBDIR stage panel. See design doc 14 §1 / §2.4.
 */
export function LbdirDetail({
  checkResult, reconResult, reconSelected, setReconSelected, siteSelected, setSiteSelected,
  busy, canReconcile, onReconcile, onApplyReconcile, compact,
}: LbdirDetailProps): React.JSX.Element {
  const fileTable = checkResult.files.length > 0 && <LbdirFileTable files={checkResult.files} />

  const reconcile = canReconcile && (
    !reconResult ? (
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Button variant="secondary" size="sm" icon="rename" disabled={busy} onClick={onReconcile}>
          {busy ? 'Scanning…' : 'Reconcile files…'}
        </Button>
        <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
          Match missing files by MD5 and move extras to <span style={{ fontFamily: 'var(--lbb-mono)' }}>/extras/</span>
        </span>
      </div>
    ) : (
      <ReconcilePanel
        result={reconResult}
        reconSelected={reconSelected}
        setReconSelected={setReconSelected}
        siteSelected={siteSelected}
        setSiteSelected={setSiteSelected}
        busy={busy}
        onRescan={onReconcile}
        onApply={onApplyReconcile}
        compact={compact}
      />
    )
  )

  if (compact) {
    return <>{fileTable}{reconcile}</>
  }

  return (
    <>
      {fileTable && <div style={{ padding: '16px 24px 0' }}>{fileTable}</div>}
      {reconcile && <div style={{ padding: '16px 0 0', ...(reconResult ? {} : { padding: '16px 24px 0' }) }}>{reconcile}</div>}
    </>
  )
}
