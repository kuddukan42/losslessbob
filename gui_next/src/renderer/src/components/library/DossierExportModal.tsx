// Show dossier export options modal (FABLE_SHOW_DOSSIER.md D4). Channel +
// section toggles + format, remembered across exports via useSettingsStore.
// HTML downloads through the browser flow (same fetch+blobDownload pattern
// as the m3u/collection-html exports); PDF goes through the Electron main
// process (window.api.printDossierPdf — a hidden BrowserWindow prints the
// backend's own HTML render) and falls back to an HTML download when that
// bridge isn't available (dev/browser context, spec D4).
import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../primitives'
import { useSettingsStore, type DossierChannel, type DossierFormat } from '../../store'

function blobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function DossierExportModal({
  showId, base, onClose, showToast,
}: {
  showId: string
  base: string
  onClose: () => void
  showToast: (msg: string, tone: 'ok' | 'bad' | 'info') => void
}) {
  const { t } = useTranslation()
  const {
    dossierChannel, setDossierChannel,
    dossierIncludeContext, setDossierIncludeContext,
    dossierIncludeSetlist, setDossierIncludeSetlist,
    dossierIncludeLocalAnalysis, setDossierIncludeLocalAnalysis,
    dossierFormat, setDossierFormat,
  } = useSettingsStore()
  const [busy, setBusy] = useState(false)

  const buildParams = () => {
    const sections = [
      ...(dossierIncludeContext ? ['context'] : []),
      ...(dossierIncludeSetlist ? ['setlist'] : []),
    ]
    const p = new URLSearchParams({
      date: showId,
      channel: dossierChannel,
      sections: sections.join(','),
      local_analysis: dossierIncludeLocalAnalysis ? '1' : '0',
    })
    return p
  }

  const handleExport = async () => {
    setBusy(true)
    try {
      const params = buildParams()
      const filename = `dossier-${showId}.${dossierFormat}`

      if (dossierFormat === 'pdf' && typeof window.api?.printDossierPdf === 'function') {
        const url = `${window.api.flaskBase}/api/dossier/html?${params.toString()}`
        const ok = await window.api.printDossierPdf(url, filename)
        if (ok) { showToast(t('library.dossier.toastExported'), 'ok'); onClose() }
        setBusy(false)
        return
      }

      // HTML format, or PDF requested outside Electron (D4 fallback).
      const resp = await fetch(`${base}/api/dossier/html?${params.toString()}`)
      if (resp.status === 300) { showToast(t('library.dossier.toastAmbiguous'), 'info'); setBusy(false); return }
      if (!resp.ok) throw new Error(String(resp.status))
      const blob = await resp.blob()
      blobDownload(blob, `dossier-${showId}.html`)
      showToast(
        dossierFormat === 'pdf' ? t('library.dossier.toastPdfFallback') : t('library.dossier.toastExported'),
        'ok',
      )
      onClose()
    } catch {
      showToast(t('library.dossier.toastFailed'), 'bad')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 24, maxWidth: 420, width: '90%',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 4 }}>
          {t('library.dossier.title')}
        </div>
        <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg2)', marginBottom: 18 }}>{showId}</div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 'var(--lbb-fs-11)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.05, color: 'var(--lbb-fg3)', marginBottom: 6 }}>
            {t('library.dossier.channel')}
          </div>
          <div style={{ display: 'flex', gap: 14 }}>
            {(['public', 'full'] as DossierChannel[]).map(ch => (
              <label key={ch} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg)', cursor: 'pointer' }}>
                <input type="radio" name="dossier-channel" checked={dossierChannel === ch} onChange={() => setDossierChannel(ch)} />
                {ch === 'public' ? t('library.dossier.channelPublic') : t('library.dossier.channelFull')}
              </label>
            ))}
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 'var(--lbb-fs-11)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.05, color: 'var(--lbb-fg3)', marginBottom: 6 }}>
            {t('library.dossier.sections')}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg)', cursor: 'pointer' }}>
              <input type="checkbox" checked={dossierIncludeContext} onChange={e => setDossierIncludeContext(e.target.checked)} />
              {t('library.dossier.sectionContext')}
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg)', cursor: 'pointer' }}>
              <input type="checkbox" checked={dossierIncludeSetlist} onChange={e => setDossierIncludeSetlist(e.target.checked)} />
              {t('library.dossier.sectionSetlist')}
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg)', cursor: 'pointer' }}>
              <input type="checkbox" checked={dossierIncludeLocalAnalysis} onChange={e => setDossierIncludeLocalAnalysis(e.target.checked)} />
              {t('library.dossier.sectionLocalAnalysis')}
            </label>
          </div>
        </div>

        <div style={{ marginBottom: 22 }}>
          <div style={{ fontSize: 'var(--lbb-fs-11)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.05, color: 'var(--lbb-fg3)', marginBottom: 6 }}>
            {t('library.dossier.format')}
          </div>
          <div style={{ display: 'flex', gap: 14 }}>
            {(['html', 'pdf'] as DossierFormat[]).map(fmt => (
              <label key={fmt} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg)', cursor: 'pointer' }}>
                <input type="radio" name="dossier-format" checked={dossierFormat === fmt} onChange={() => setDossierFormat(fmt)} />
                {fmt.toUpperCase()}
              </label>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>{t('library.dossier.cancel')}</Button>
          <Button variant="primary" size="sm" onClick={handleExport} disabled={busy}>
            {busy ? t('library.dossier.exporting') : t('library.dossier.export')}
          </Button>
        </div>
      </div>
    </div>
  )
}
