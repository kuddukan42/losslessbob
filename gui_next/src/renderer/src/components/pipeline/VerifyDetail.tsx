import React from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../Icon'
import { Button, Chip, Pill, Banner, TableShell, TH, TR, TD } from '../index'
import { FileRow, CheckStatus } from '../../lib/verifyStore'

export function StatusDot({ s }: { s: CheckStatus }): React.JSX.Element {
  if (s === 'pass') return <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-bar)' }} />
  if (s === 'fail') return <Icon name="x"     size={13} style={{ color: 'var(--lbb-bad-fg)' }} />
  if (s === 'miss') return <Icon name="x"     size={13} style={{ color: 'var(--lbb-warn-fg)' }} />
  return <span style={{ color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)', fontSize: 'var(--lbb-fs-10)' }}>na</span>
}

export interface VerifyDetailProps {
  files: FileRow[]
  showAll: boolean
  onShowAllChange: (v: boolean) => void
  onCopyReport: () => void
  onOpenFinder?: () => void
  onGenerateMissing?: () => void
  generateBusy?: boolean
  /** Tighter spacing for use inside the pipeline detail panel (no full-bleed borders/padding). */
  compact?: boolean
}

/**
 * Files chip-bar + per-file table, shared between ScreenVerify and the pipeline
 * Verify stage panel. Source of truth for both — see design doc 14 §1.
 */
export function VerifyDetail({
  files, showAll, onShowAllChange, onCopyReport, onOpenFinder, onGenerateMissing, generateBusy, compact,
}: VerifyDetailProps): React.JSX.Element {
  const { t } = useTranslation()
  const problems = files.filter(f => f.overall !== 'pass')
  const visible = showAll ? files : problems

  const toolbar = (
    <>
      <span style={{ fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)', letterSpacing: 0.08, textTransform: 'uppercase' }}>
        {t('verify.toolbar.files')}
      </span>
      <Chip active={!showAll} onClick={() => onShowAllChange(false)} size="sm" count={problems.length}>{t('verify.toolbar.problems')}</Chip>
      <Chip active={showAll}  onClick={() => onShowAllChange(true)}  size="sm" count={files.length}>{t('verify.toolbar.showAll')}</Chip>
      <div style={{ flex: 1 }} />
      {onOpenFinder && (
        <Button variant="ghost" size="sm" icon="reveal" onClick={onOpenFinder} title="Reveal folder in Finder">
          {t('verify.toolbar.openFinder')}
        </Button>
      )}
      <Button variant="ghost" size="sm" icon="copy" onClick={onCopyReport} title="Copy to clipboard">
        {t('verify.toolbar.copyReport')}
      </Button>
      {onGenerateMissing && (
        <Button variant="secondary" size="sm" icon="plus" disabled={generateBusy} onClick={onGenerateMissing}>
          {t('verify.toolbar.generateMissing')}
        </Button>
      )}
    </>
  )

  const body = (
    <>
      {visible.length === 0 ? (
        <Banner tone="ok" icon="check" title={t('verify.allClear.title')}>
          {t('verify.allClear.desc', { count: files.length })}
        </Banner>
      ) : (
        <TableShell>
          <colgroup>
            <col style={{ width: 3 }} />
            <col />
            <col style={{ width: 130 }} /><col style={{ width: 130 }} /><col style={{ width: 60 }} />
            <col style={{ width: 130 }} /><col style={{ width: 130 }} /><col style={{ width: 60 }} />
            <col style={{ width: 60 }} /><col style={{ width: 60 }} /><col style={{ width: 90 }} />
          </colgroup>
          <thead>
            <tr>
              <TH> </TH><TH>{t('verify.table.filename')}</TH>
              <TH align="right">{t('verify.table.md5Expected')}</TH><TH align="right">{t('verify.table.md5Actual')}</TH><TH align="center">{t('verify.table.md5')}</TH>
              <TH align="right">{t('verify.table.ffpExpected')}</TH><TH align="right">{t('verify.table.ffpActual')}</TH><TH align="center">{t('verify.table.ffp')}</TH>
              <TH align="center">{t('verify.table.st5')}</TH><TH align="center">{t('verify.table.disk')}</TH><TH>{t('verify.table.overall')}</TH>
            </tr>
          </thead>
          <tbody>
            {visible.map((f, i) => {
              const edge: 'ok' | 'warn' | 'bad' = f.overall === 'pass' ? 'ok' : f.overall === 'missing' ? 'warn' : 'bad'
              const md5e = f.md5_expected ? f.md5_expected.slice(0, 12) + '…' : '—'
              const md5a = f.md5_actual   ? f.md5_actual.slice(0, 12)   + '…' : '—'
              const ffpe = f.ffp_expected ? f.ffp_expected.slice(0, 12) + '…' : '—'
              const ffpa = f.ffp_actual   ? f.ffp_actual.slice(0, 12)   + '…' : '—'
              return (
                <TR key={i} edge={edge}>
                  <TD mono style={{ color: f.overall === 'pass' ? 'var(--lbb-fg)' : f.overall === 'missing' ? 'var(--lbb-warn-fg)' : 'var(--lbb-bad-fg)' }}>
                    {f.filename}
                  </TD>
                  <TD align="right" mono dim>{md5e}</TD>
                  <TD align="right" mono style={{ color: f.md5_status === 'fail' ? 'var(--lbb-bad-fg)' : f.md5_status === 'miss' ? 'var(--lbb-fg3)' : 'var(--lbb-fg2)' }}>
                    {md5a}
                  </TD>
                  <TD align="center"><StatusDot s={f.md5_status} /></TD>
                  <TD align="right" mono dim>{ffpe}</TD>
                  <TD align="right" mono style={{ color: f.ffp_status === 'fail' ? 'var(--lbb-bad-fg)' : f.ffp_status === 'miss' ? 'var(--lbb-fg3)' : 'var(--lbb-fg2)' }}>
                    {ffpa}
                  </TD>
                  <TD align="center"><StatusDot s={f.ffp_status} /></TD>
                  <TD align="center"><StatusDot s={f.shntool_status} /></TD>
                  <TD align="center">
                    {f.on_disk
                      ? <Icon name="check" size={12} style={{ color: 'var(--lbb-ok-bar)' }} />
                      : <Icon name="x"     size={12} style={{ color: 'var(--lbb-warn-fg)' }} />}
                  </TD>
                  <TD>
                    <Pill tone={edge} soft>
                      {f.overall === 'pass' ? t('verify.fileStates.pass') : f.overall === 'missing' ? t('verify.fileStates.missing') : f.overall === 'extra' ? t('verify.fileStates.extra') : t('verify.fileStates.fail')}
                    </Pill>
                  </TD>
                </TR>
              )
            })}
          </tbody>
        </TableShell>
      )}

      {!showAll && visible.length > 0 && (
        <div style={{ marginTop: 10, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', fontStyle: 'italic', textAlign: 'center' }}>
          {t('verify.showingProblems', { count: visible.length })}{' '}
          <button
            onClick={() => onShowAllChange(true)}
            style={{
              background: 'none', border: 'none', color: 'var(--lbb-accent-mid)',
              cursor: 'pointer', textDecoration: 'underline', fontStyle: 'italic',
              padding: 0, font: 'inherit',
            }}
          >
            {t('verify.showAllCount', { count: files.length })}
          </button>
        </div>
      )}
    </>
  )

  if (compact) {
    return (
      <>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>{toolbar}</div>
        {body}
      </>
    )
  }

  return (
    <>
      <div style={{ padding: '10px 24px', borderBottom: '1px solid var(--lbb-border)', display: 'flex', alignItems: 'center', gap: 10 }}>
        {toolbar}
      </div>
      <div style={{ flex: 1, overflow: 'auto', minHeight: 0, padding: '0 24px 24px' }}>
        {body}
      </div>
    </>
  )
}
