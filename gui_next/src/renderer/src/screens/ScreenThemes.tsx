import React, { useState, useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useSettingsStore } from '../store'
import {
  Button, Pill, Chip, Icon,
  TableShell, TH, TR, TD,
} from '../components'
import {
  applyTheme, loadTheme, saveTheme, getSystemMode,
  type ThemeOptions, type Mode, type Accent, type Density, type Font, type FontSize,
  type Palette, type CardStyle,
  DEFAULT_THEME, FONT_SIZES, PALETTE_OPTIONS, PALETTES,
} from '../lib/tokens'

// ── SetupCard (local, same shape as ScreenSetup) ─────────────────────────────

function SetupCard({
  title,
  badge,
  children,
  style,
}: {
  title: string
  badge?: React.ReactNode
  children?: React.ReactNode
  style?: React.CSSProperties
}) {
  return (
    <div
      style={{
        background: 'var(--lbb-surface)',
        border: '1px solid var(--lbb-border)',
        borderRadius: 10,
        padding: 18,
        ...style,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <span
          style={{
            fontSize: 'var(--lbb-fs-12)',
            fontWeight: 700,
            letterSpacing: 0.08,
            textTransform: 'uppercase',
            color: 'var(--lbb-fg)',
          }}
        >
          {title}
        </span>
        {badge}
      </div>
      {children}
    </div>
  )
}

// ── Toast ─────────────────────────────────────────────────────────────────────

type ToastTone = 'ok' | 'bad' | 'info'

function Toast({ msg, tone, onDone }: { msg: string; tone: ToastTone; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3000)
    return () => clearTimeout(t)
  }, [onDone])
  const bg = tone === 'ok' ? 'var(--lbb-ok-bg)' : tone === 'bad' ? 'var(--lbb-bad-bg)' : 'var(--lbb-info-bg)'
  const fg = tone === 'ok' ? 'var(--lbb-ok-fg)' : tone === 'bad' ? 'var(--lbb-bad-fg)' : 'var(--lbb-info-fg)'
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

// ── Custom token editor ───────────────────────────────────────────────────────

const CUSTOM_EDITABLE_TOKENS = [
  { key: '--lbb-bg',       label: 'Background' },
  { key: '--lbb-surface',  label: 'Surface' },
  { key: '--lbb-surface2', label: 'Surface 2' },
  { key: '--lbb-border',   label: 'Border' },
  { key: '--lbb-fg',       label: 'Foreground' },
  { key: '--lbb-fg2',      label: 'Foreground 2' },
  { key: '--lbb-fg3',      label: 'Foreground 3' },
] as const

function CustomTokenEditor({
  customTokens,
  onChange,
}: {
  customTokens: Record<string, string>
  onChange: (next: Record<string, string>) => void
}) {
  const { t } = useTranslation()

  function getLiveColor(key: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(key).trim()
  }

  return (
    <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {CUSTOM_EDITABLE_TOKENS.map(({ key }) => {
        const tokenKey = key.replace('--lbb-', '').replace('-', '')
        const labelMap: Record<string, string> = {
          'bg': t('themes.tokens.background'),
          'surface': t('themes.tokens.surface'),
          'surface2': t('themes.tokens.surface2'),
          'border': t('themes.tokens.border'),
          'fg': t('themes.tokens.foreground'),
          'fg2': t('themes.tokens.foreground2'),
          'fg3': t('themes.tokens.foreground3'),
        }
        const label = labelMap[tokenKey] ?? tokenKey
        const override = customTokens[key]
        const displayVal = override ?? getLiveColor(key)
        return (
          <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)', minWidth: 96 }}>{label}</span>
            <input
              type="color"
              value={displayVal.startsWith('#') ? displayVal : '#888888'}
              onChange={(e) => onChange({ ...customTokens, [key]: e.target.value })}
              style={{
                width: 30, height: 22, borderRadius: 4, padding: 1,
                border: '1px solid var(--lbb-border)', cursor: 'pointer', background: 'none',
              }}
            />
            <span style={{ fontSize: 'var(--lbb-fs-11)', fontFamily: 'var(--lbb-mono)', color: 'var(--lbb-fg3)' }}>
              {displayVal || '—'}
            </span>
            {override && (
              <button
                type="button"
                onClick={() => { const n = { ...customTokens }; delete n[key]; onChange(n) }}
                style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', background: 'none', border: 'none', cursor: 'pointer', padding: '0 4px' }}
              >
                {t('themes.tokens.reset')}
              </button>
            )}
          </div>
        )
      })}
      {Object.keys(customTokens).length > 0 && (
        <div style={{ marginTop: 4 }}>
          <Button variant="ghost" size="sm" onClick={() => onChange({})}>
            {t('themes.advanced.resetAll')}
          </Button>
        </div>
      )}
    </div>
  )
}

// ── Accent swatch data ────────────────────────────────────────────────────────

const ACCENT_SWATCHES: { k: Accent; c: string }[] = [
  { k: 'indigo',  c: '#2b5fd0' },
  { k: 'plum',    c: '#7a3fb1' },
  { k: 'rust',    c: '#a8462e' },
  { k: 'forest',  c: '#2a7a4a' },
  { k: 'teal',    c: '#2b6f7c' },
  { k: 'amber',   c: '#9a6800' },
  { k: 'gray',    c: '#4a463e' },
  { k: 'crimson', c: '#a31a35' },
]

// ── Preview table rows ────────────────────────────────────────────────────────

const PREVIEW_ROWS = [
  { lb: 'LB-1',  date: '5/xx/87',  venue: 'Dead Dylan Rehearsals',  tone: 'ok'   as const, label: 'Public'  },
  { lb: 'LB-7',  date: '—',        venue: '—',                      tone: 'warn' as const, label: 'Missing' },
  { lb: 'LB-12', date: '11/11/80', venue: 'Warfield, SF',           tone: 'bad'  as const, label: 'Mismatch'},
  { lb: 'LB-18', date: '6/29/81',  venue: "Earl's Court, London",   tone: 'info' as const, label: 'Public'  },
]

const PREVIEW_BTN_VARIANTS = ['primary', 'secondary', 'ghost', 'danger'] as const

// ── ScreenThemes ──────────────────────────────────────────────────────────────

export function ScreenThemes() {
  const { t } = useTranslation()
  const [theme, setTheme] = useState<ThemeOptions>(loadTheme)
  const rowHighlight    = useSettingsStore((s) => s.rowHighlight)
  const setRowHighlight = useSettingsStore((s) => s.setRowHighlight)
  const [showCustomEditor, setShowCustomEditor] = useState(false)
  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone = 'ok') => setToast({ msg, tone }), [])
  const resolvedMode = theme.mode === 'system' ? getSystemMode() : theme.mode

  function setTweak<K extends keyof ThemeOptions>(key: K, value: ThemeOptions[K]) {
    const next = { ...theme, [key]: value }
    applyTheme(next)
    saveTheme(next)
    setTheme(next)
  }

  async function handleExportTheme() {
    const json = JSON.stringify(theme, null, 2)
    const ok = await window.api.saveFile(json, 'losslessbob-theme.json')
    if (ok) showToast(t('themes.toast.exported'), 'ok')
  }

  async function handleImportTheme() {
    const content = await window.api.pickAndReadFile({
      title: 'Import theme JSON',
      filters: [{ name: 'JSON', extensions: ['json'] }],
    })
    if (!content) return
    try {
      const parsed = JSON.parse(content) as Partial<ThemeOptions>
      if (typeof parsed !== 'object' || !parsed.mode || !parsed.accent) {
        showToast(t('themes.toast.notValid'), 'bad')
        return
      }
      const imported: ThemeOptions = {
        mode:         parsed.mode         ?? DEFAULT_THEME.mode,
        accent:       parsed.accent       ?? DEFAULT_THEME.accent,
        density:      parsed.density      ?? DEFAULT_THEME.density,
        palette:      parsed.palette,
        cardStyle:    parsed.cardStyle    ?? DEFAULT_THEME.cardStyle,
        font:         parsed.font         ?? DEFAULT_THEME.font,
        fontSize:     parsed.fontSize     ?? DEFAULT_THEME.fontSize,
        customTokens: parsed.customTokens ?? {},
      }
      applyTheme(imported)
      saveTheme(imported)
      setTheme(imported)
      showToast(t('themes.toast.imported'), 'ok')
    } catch {
      showToast(t('themes.toast.parseFailed'), 'bad')
    }
  }

  const densityTiles: { k: Density; l: string; n: string; bars: number; barH: number; gap: number }[] = [
    { k: 'comfortable', l: t('themes.density.comfortable'), n: t('themes.density.comfortableRows'), bars: 4, barH: 11, gap: 8 },
    { k: 'default',     l: t('themes.density.default'),     n: t('themes.density.defaultRows'),     bars: 6, barH:  7, gap: 5 },
    { k: 'compact',     l: t('themes.density.compact'),     n: t('themes.density.compactRows'),     bars: 8, barH:  5, gap: 2 },
  ]

  const typefaceDefs: { k: Font; l: string; n: string; stack: string }[] = [
    { k: 'inter',    l: 'Inter',         n: t('themes.typeface.interDesc'),   stack: 'Inter, sans-serif' },
    { k: 'ibm-plex', l: 'IBM Plex Sans', n: t('themes.typeface.ibmPlexDesc'), stack: '"IBM Plex Sans", sans-serif' },
    { k: 'source',   l: 'Source Sans 3', n: t('themes.typeface.sourceDesc'),  stack: '"Source Sans 3", sans-serif' },
  ]

  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      <div style={{ padding: '24px 32px 40px', maxWidth: 1500, margin: '0 auto' }}>

        <h1 style={{ margin: 0, fontSize: 'var(--lbb-fs-22)', fontWeight: 700, letterSpacing: -0.02, color: 'var(--lbb-fg)' }}>
          {t('themes.title')}
        </h1>
        <p style={{ fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)', marginTop: 4, marginBottom: 0 }}>
          {t('themes.subtitle')}
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 24 }}>

          {/* ── Mode ── */}
          <SetupCard title={t('themes.mode.title')}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {([
                { k: 'light',  l: t('themes.mode.light'),  bg: '#faf8f3', side: '#e2dfd2' },
                { k: 'dark',   l: t('themes.mode.dark'),   bg: '#27251d', side: '#161510' },
                { k: 'system', l: t('themes.mode.system'), bg: '#faf8f3', side: '#161510' },
              ] as { k: Mode; l: string; bg: string; side: string }[]).map((m) => (
                <button
                  key={m.k}
                  type="button"
                  onClick={() => setTweak('mode', m.k)}
                  style={{
                    padding: 10,
                    borderRadius: 10,
                    background: 'var(--lbb-surface)',
                    border: `2px solid ${theme.mode === m.k ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    color: 'var(--lbb-fg)',
                    transition: 'border-color 0.15s',
                  }}
                >
                  {/* Mini preview */}
                  <div style={{ height: 80, borderRadius: 6, overflow: 'hidden', border: '1px solid var(--lbb-border2)', display: 'grid', gridTemplateColumns: '1fr 2fr' }}>
                    <div style={{ background: m.side }} />
                    <div style={{ background: m.bg, padding: 8 }}>
                      <div style={{ height: 6, background: m.side, opacity: 0.6, borderRadius: 2, marginBottom: 6 }} />
                      <div style={{ height: 4, background: m.side, opacity: 0.3, borderRadius: 2, marginBottom: 4 }} />
                      <div style={{ height: 4, background: m.side, opacity: 0.3, borderRadius: 2, width: '60%' }} />
                    </div>
                  </div>
                  <div style={{ marginTop: 8, fontSize: 'var(--lbb-fs-12)', fontWeight: 600 }}>{m.l}</div>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* ── Density ── */}
          <SetupCard title={t('themes.density.title')}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {densityTiles.map((d) => (
                <button
                  key={d.k}
                  type="button"
                  onClick={() => setTweak('density', d.k)}
                  style={{
                    padding: 12,
                    borderRadius: 10,
                    background: 'var(--lbb-surface)',
                    border: `2px solid ${theme.density === d.k ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    color: 'var(--lbb-fg)',
                    textAlign: 'left',
                    transition: 'border-color 0.15s',
                  }}
                >
                  <div style={{ height: 80, display: 'flex', flexDirection: 'column', gap: d.gap }}>
                    {Array.from({ length: d.bars }).map((_, i) => (
                      <div
                        key={i}
                        style={{
                          height: d.barH,
                          background: 'var(--lbb-surface2)',
                          borderRadius: 2,
                          border: '1px solid var(--lbb-border)',
                        }}
                      />
                    ))}
                  </div>
                  <div style={{ marginTop: 8, fontSize: 'var(--lbb-fs-12)', fontWeight: 600 }}>{d.l}</div>
                  <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)' }}>{d.n}</div>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* ── Frame theme (palette) ── */}
          <SetupCard title={t('themes.palette.title')}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {(['default', ...PALETTE_OPTIONS] as ('default' | Palette)[]).map((p) => {
                const active = (theme.palette ?? 'default') === p
                const tone = p === 'default' ? undefined : PALETTES[resolvedMode][p]
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setTweak('palette', p === 'default' ? undefined : p)}
                    style={{
                      padding: 8,
                      borderRadius: 10,
                      background: 'var(--lbb-surface)',
                      border: `2px solid ${active ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: 6,
                      width: 84,
                      transition: 'border-color 0.15s',
                    }}
                  >
                    <div
                      style={{
                        width: 50,
                        height: 50,
                        borderRadius: '50%',
                        background: tone ? tone.surface : 'var(--lbb-surface)',
                        border: `2px solid ${tone ? tone.bg : 'var(--lbb-border2)'}`,
                        boxShadow: '0 1px 0 rgba(255,255,255,0.3) inset',
                      }}
                    />
                    <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg)', fontWeight: 600, textTransform: 'capitalize' }}>
                      {p === 'default' ? t('themes.palette.default') : p}
                    </span>
                  </button>
                )
              })}
            </div>
          </SetupCard>

          {/* ── Card style ── */}
          <SetupCard title={t('themes.cardStyle.title')}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
              {([
                { k: 'flat',   l: t('themes.cardStyle.flat') },
                { k: 'framed', l: t('themes.cardStyle.framed') },
              ] as { k: CardStyle; l: string }[]).map((c) => (
                <button
                  key={c.k}
                  type="button"
                  onClick={() => setTweak('cardStyle', c.k)}
                  style={{
                    padding: 10,
                    borderRadius: 10,
                    background: 'var(--lbb-surface)',
                    border: `2px solid ${(theme.cardStyle ?? 'flat') === c.k ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    color: 'var(--lbb-fg)',
                    transition: 'border-color 0.15s',
                  }}
                >
                  <div style={{ height: 80, borderRadius: 6, background: 'var(--lbb-surface2)', padding: 10, display: 'flex', gap: 6 }}>
                    {c.k === 'framed' ? (
                      <>
                        <div style={{ flex: 1, background: 'var(--lbb-surface)', borderRadius: 6, boxShadow: '0 4px 10px rgba(0,0,0,0.18)' }} />
                        <div style={{ flex: 2, background: 'var(--lbb-surface)', borderRadius: 6, boxShadow: '0 4px 10px rgba(0,0,0,0.18)' }} />
                      </>
                    ) : (
                      <>
                        <div style={{ flex: 1, borderRight: '1px solid var(--lbb-border)' }} />
                        <div style={{ flex: 2 }} />
                      </>
                    )}
                  </div>
                  <div style={{ marginTop: 8, fontSize: 'var(--lbb-fs-12)', fontWeight: 600 }}>{c.l}</div>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* ── Accent (span 2) ── */}
          <SetupCard title={t('themes.accent.title')} style={{ gridColumn: 'span 2' }}>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {ACCENT_SWATCHES.map((a) => (
                <button
                  key={a.k}
                  type="button"
                  onClick={() => setTweak('accent', a.k)}
                  style={{
                    padding: 8,
                    borderRadius: 10,
                    background: 'var(--lbb-surface)',
                    border: `2px solid ${theme.accent === a.k ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 6,
                    width: 84,
                    transition: 'border-color 0.15s',
                  }}
                >
                  <div
                    style={{
                      width: 50,
                      height: 50,
                      borderRadius: '50%',
                      background: a.c,
                      border: '1px solid rgba(0,0,0,0.08)',
                      boxShadow: '0 1px 0 rgba(255,255,255,0.3) inset',
                    }}
                  />
                  <span style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg)', fontWeight: 600, textTransform: 'capitalize' }}>
                    {a.k}
                  </span>
                </button>
              ))}
            </div>
          </SetupCard>

          {/* ── Typeface ── */}
          <SetupCard title={t('themes.typeface.title')}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {typefaceDefs.map((f) => {
                const active = (theme.font ?? 'inter') === f.k
                return (
                  <button
                    key={f.k}
                    type="button"
                    onClick={() => setTweak('font', f.k)}
                    style={{
                      padding: '10px 14px',
                      borderRadius: 8,
                      background: 'var(--lbb-surface)',
                      border: `1px solid ${active ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      textAlign: 'left',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      transition: 'border-color 0.15s',
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 'var(--lbb-fs-13)', fontWeight: 600, color: 'var(--lbb-fg)', fontFamily: f.stack }}>{f.l}</div>
                      <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>{f.n}</div>
                    </div>
                    {active && <Icon name="check" size={14} style={{ color: 'var(--lbb-accent-mid)', flexShrink: 0 }} />}
                  </button>
                )
              })}
            </div>
            <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)', marginRight: 4 }}>{t('themes.typeface.size')}</span>
              {(FONT_SIZES as FontSize[]).map((sz) => (
                <button
                  key={sz}
                  type="button"
                  onClick={() => setTweak('fontSize', sz)}
                  style={{
                    padding: '3px 10px',
                    borderRadius: 6,
                    fontSize: 'var(--lbb-fs-12)',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    color: 'var(--lbb-fg)',
                    background: 'var(--lbb-surface)',
                    border: `1px solid ${(theme.fontSize ?? 13) === sz ? 'var(--lbb-accent-mid)' : 'var(--lbb-border)'}`,
                    transition: 'border-color 0.15s',
                  }}
                >
                  {sz}pt
                </button>
              ))}
            </div>
          </SetupCard>

          {/* ── Advanced ── */}
          <SetupCard title={t('themes.advanced.title')}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowCustomEditor((v) => !v)}
              >
                {showCustomEditor ? t('themes.advanced.hideTokens') : t('themes.advanced.showTokens')}
              </Button>
              {showCustomEditor && (
                <CustomTokenEditor
                  customTokens={theme.customTokens ?? {}}
                  onChange={(next) => setTweak('customTokens', next)}
                />
              )}
              <Button variant="ghost" size="sm" onClick={handleExportTheme}>
                {t('themes.advanced.exportTheme')}
              </Button>
              <Button variant="ghost" size="sm" onClick={handleImportTheme}>
                {t('themes.advanced.importTheme')}
              </Button>
            </div>
            <div
              style={{
                marginTop: 14,
                padding: '10px 12px',
                borderRadius: 6,
                background: 'var(--lbb-surface2)',
                fontSize: 'var(--lbb-fs-11-5)',
                color: 'var(--lbb-fg2)',
                lineHeight: 1.5,
              }}
            >
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', marginBottom: 8 }}>
                <input
                  type="checkbox"
                  checked={rowHighlight}
                  onChange={(e) => setRowHighlight(e.target.checked)}
                  style={{ accentColor: 'var(--lbb-accent-mid)' }}
                />
                <span>{t('themes.advanced.rowHighlight')}</span>
              </label>
              {t('themes.advanced.statusColorsNote')}
            </div>
          </SetupCard>

          {/* ── Live preview (span 2) ── */}
          <SetupCard
            title={t('themes.preview.title')}
            style={{ gridColumn: 'span 2' }}
            badge={<Pill tone="mute" soft>{t('themes.preview.subtitle')}</Pill>}
          >
            <div style={{ border: '1px solid var(--lbb-border)', borderRadius: 8, overflow: 'hidden' }}>
              {/* Mock titlebar */}
              <div
                style={{
                  padding: '10px 16px',
                  background: 'var(--lbb-accent-mid)',
                  color: 'var(--lbb-accent-onMid)',
                  fontSize: 'var(--lbb-fs-12)',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                }}
              >
                <Icon name="collection" size={14} />
                {t('themes.preview.collectionLabel')}
                <div style={{ flex: 1 }} />
                <span style={{ fontSize: 'var(--lbb-fs-11)', opacity: 0.85 }}>{t('themes.preview.previewSub')}</span>
              </div>

              {/* Mock content area */}
              <div style={{ padding: 16, background: 'var(--lbb-bg)' }}>
                <TableShell stickyHeader={false}>
                  <colgroup>
                    <col style={{ width: 3 }} />
                    <col style={{ width: 90 }} />
                    <col style={{ width: 90 }} />
                    <col style={{ width: 100 }} />
                    <col />
                    <col style={{ width: 150 }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <TH /><TH>LB#</TH><TH>Status</TH><TH>Date</TH><TH>Location</TH><TH align="right">Action</TH>
                    </tr>
                  </thead>
                  <tbody>
                    {PREVIEW_ROWS.map((r, i) => (
                      <TR key={r.lb} edge={r.tone}>
                        <TD mono style={{ color: 'var(--lbb-accent-mid)', fontWeight: 600 }}>{r.lb}</TD>
                        <TD><Pill tone={r.tone} soft>{r.label}</Pill></TD>
                        <TD mono dim={r.date === '—'}>{r.date}</TD>
                        <TD dim={r.venue === '—'}>{r.venue}</TD>
                        <TD align="right">
                          <Button size="sm" variant={PREVIEW_BTN_VARIANTS[i]}>
                            {['Primary', 'Secondary', 'Ghost', 'Danger'][i]}
                          </Button>
                        </TD>
                      </TR>
                    ))}
                  </tbody>
                </TableShell>

                <div style={{ marginTop: 14, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Chip active count={1234}>Active chip</Chip>
                  <Chip count={88}>Filter chip</Chip>
                  <Chip count={12}>Another</Chip>
                  <Pill tone="ok"   soft>ok</Pill>
                  <Pill tone="warn" soft>warn</Pill>
                  <Pill tone="bad"  soft>bad</Pill>
                  <Pill tone="info" soft>info</Pill>
                </div>
              </div>
            </div>
          </SetupCard>

        </div>
      </div>

      {toast && <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />}
    </div>
  )
}
