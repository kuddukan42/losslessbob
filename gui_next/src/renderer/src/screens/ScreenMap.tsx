import React, { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Button, Chip, Input, Pill } from '../components'

const PINS = [
  { x: 22, y: 28, c: '#3b6a99',                  n: 3,   l: 'Hibbing, MN',              era: '1957'    },
  { x: 36, y: 36, c: '#2a8b6f',                  n: 87,  l: 'Greenwich Village, NY',    era: '1961–63' },
  { x: 28, y: 48, c: 'var(--lbb-accent-mid)',    n: 124, l: 'San Francisco Bay',         era: '1965–80' },
  { x: 44, y: 42, c: '#c25a48',                  n: 56,  l: 'Texas (Houston / Dallas)',  era: '1981–86' },
  { x: 56, y: 30, c: 'var(--lbb-accent-mid)',    n: 290, l: 'NYC area',                  era: '1980s'   },
  { x: 60, y: 50, c: '#b58a3a',                  n: 67,  l: 'Florida',                  era: '2000s+'  },
  { x: 72, y: 28, c: '#2a8b6f',                  n: 32,  l: "London / Earl's Court",    era: '1978–81' },
  { x: 78, y: 36, c: '#c25a48',                  n: 22,  l: 'Paris / Avignon',          era: '1990s'   },
  { x: 82, y: 50, c: '#b58a3a',                  n: 14,  l: 'Cairo',                    era: '1995'    },
  { x: 50, y: 68, c: '#2a8b6f',                  n: 9,   l: 'Sydney',                   era: '1986'    },
  { x: 30, y: 64, c: 'var(--lbb-accent-mid)',    n: 18,  l: 'Buenos Aires',              era: '1990s'   },
]

const SELECTED_LBS = [
  { lb: 'LB-280',  d: '1980-11-09', v: 'Fox Warfield, San Francisco', owned: true,  status: 'current' },
  { lb: 'LB-281',  d: '1980-11-10', v: 'Fox Warfield, San Francisco', owned: true,  status: 'current' },
  { lb: 'LB-282',  d: '1980-11-11', v: 'Fox Warfield, San Francisco', owned: true,  status: 'current' },
  { lb: 'LB-283',  d: '1980-11-12', v: 'Fox Warfield, San Francisco', owned: false, status: 'current' },
  { lb: 'LB-294',  d: '1980-11-22', v: 'Berkeley Comm. Theatre',      owned: true,  status: 'current' },
  { lb: 'LB-2841', d: '1986-09-13', v: 'Greek Theatre, Berkeley',     owned: true,  status: 'current' },
  { lb: 'LB-7710', d: '2002-10-13', v: 'Berkeley Comm. Theatre',      owned: false, status: 'missing' },
  { lb: 'LB-7716', d: '2002-10-15', v: 'Berkeley Comm. Theatre',      owned: false, status: 'current' },
]

const DECADES = [
  { c: '#3b6a99',               l: '1960s' },
  { c: '#2a8b6f',               l: '1970s' },
  { c: 'var(--lbb-accent-mid)', l: '1980s' },
  { c: '#c25a48',               l: '1990s' },
  { c: '#b58a3a',               l: '2000s+' },
]

const DECADE_CHIPS: Array<[string, number, number]> = [
  ['60s', 1960, 1969], ['70s', 1970, 1979], ['80s', 1980, 1989],
  ['90s', 1990, 1999], ['00s', 2000, 2009], ['10s+', 2010, 2030],
]

const STATUS_OPTIONS = [
  { k: 'all',     l: 'All entries',        n: 6676 },
  { k: 'public',  l: 'Public',             n: 5184 },
  { k: 'private', l: 'Private',            n: 1404 },
  { k: 'missing', l: 'Missing on archive', n: 88   },
]

const DISPLAY_OPTS = [
  { l: 'Cluster markers',   v: true  },
  { l: 'Color by decade',   v: true  },
  { l: 'Heatmap overlay',   v: false },
  { l: 'Show venue labels', v: false },
]

const SECTION_LABEL: React.CSSProperties = {
  fontSize: 10.5, fontWeight: 700, color: 'var(--lbb-fg3)',
  letterSpacing: 0.08, textTransform: 'uppercase',
}

const MAP_URL = 'http://localhost:5174/map'

export function ScreenMap(): React.JSX.Element {
  const { t } = useTranslation()
  const [yearMin, setYearMin] = useState(1980)
  const [yearMax, setYearMax] = useState(1989)
  const [owned,   setOwned]   = useState('all')
  const [status,  setStatus]  = useState('all')
  const [search,  setSearch]  = useState('')
  const iframeRef = useRef<HTMLIFrameElement>(null)

  const selectedPinData = PINS[2]

  function handleApplyFilters() {
    const filters: Record<string, string | boolean> = {}
    if (status && status !== 'all') filters.status = status
    if (owned === 'owned')   filters.owned = true
    if (yearMin)             filters.year_min = String(yearMin)
    if (yearMax)             filters.year_max = String(yearMax)
    if (search.trim())       filters.q = search.trim()
    iframeRef.current?.contentWindow?.postMessage({ type: 'applyFilters', filters }, '*')
  }

  function handleResetFilters() {
    setYearMin(1900)
    setYearMax(2030)
    setOwned('all')
    setStatus('all')
    setSearch('')
    iframeRef.current?.contentWindow?.postMessage({ type: 'applyFilters', filters: {} }, '*')
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
          <Icon name="map" size={18} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: -0.01 }}>{t('map.title')}</h1>
            <Pill tone="ok"   soft>{t('map.geocoded', { count: 6676 })}</Pill>
            <Pill tone="warn" soft>{t('map.awaitingGeocode', { count: 9954 })}</Pill>
          </div>
          <div style={{ fontSize: 12, color: 'var(--lbb-fg3)', marginTop: 2 }}>
            {t('map.desc')}
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <Button variant="ghost"   size="sm" icon="copy"   onClick={() => navigator.clipboard.writeText(MAP_URL)}>{t('map.copyShareUrl')}</Button>
        <Button variant="primary" size="sm" icon="reveal" onClick={() => window.open(MAP_URL)}>{t('map.openLiveMap')}</Button>
      </div>

      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '300px 1fr 320px', minHeight: 0 }}>

        {/* Filter rail */}
        <aside style={{
          background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
          padding: 18, display: 'flex', flexDirection: 'column', gap: 18, overflowY: 'auto',
        }}>
          {/* Year range */}
          <section>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <span style={SECTION_LABEL}>{t('map.yearRange')}</span>
              <div style={{ flex: 1 }} />
              <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11.5, fontWeight: 600, color: 'var(--lbb-accent-mid)' }}>
                {yearMin} – {yearMax}
              </span>
            </div>
            {/* Dual-handle slider (visual stand-in) */}
            <div style={{ position: 'relative', height: 28, padding: '10px 0' }}>
              <div style={{ position: 'absolute', top: 13, left: 0, right: 0, height: 4, background: 'var(--lbb-border)', borderRadius: 2 }} />
              <div style={{ position: 'absolute', top: 13, left: '28%', right: '33%', height: 4, background: 'var(--lbb-accent-mid)', borderRadius: 2 }} />
              <div style={{ position: 'absolute', top: 7, left: '28%', width: 14, height: 14, borderRadius: '50%', background: '#fff', border: '2px solid var(--lbb-accent-mid)', transform: 'translateX(-50%)' }} />
              <div style={{ position: 'absolute', top: 7, left: '67%', width: 14, height: 14, borderRadius: '50%', background: '#fff', border: '2px solid var(--lbb-accent-mid)', transform: 'translateX(-50%)' }} />
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <Input size="sm" placeholder="1961" style={{ flex: 1 }} />
              <span style={{ alignSelf: 'center', color: 'var(--lbb-fg3)' }}>–</span>
              <Input size="sm" placeholder="2030" style={{ flex: 1 }} />
            </div>
            <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
              {DECADE_CHIPS.map(([l, a, b]) => (
                <Chip key={l} size="sm" active={yearMin === a && yearMax === b} onClick={() => { setYearMin(a); setYearMax(b) }}>
                  {l}
                </Chip>
              ))}
            </div>
          </section>

          {/* Ownership */}
          <section>
            <div style={{ ...SECTION_LABEL, marginBottom: 8 }}>{t('map.ownership')}</div>
            <div style={{ display: 'flex', padding: 2, background: 'var(--lbb-surface2)', borderRadius: 6, border: '1px solid var(--lbb-border)' }}>
              {[['all', t('map.ownerAll')], ['owned', t('map.ownerOwned')], ['unowned', t('map.ownerNotOwned')]].map(([k, l]) => (
                <button key={k} onClick={() => setOwned(k)} style={{
                  flex: 1, padding: '5px 8px', borderRadius: 4,
                  background: owned === k ? 'var(--lbb-surface)' : 'transparent',
                  color: owned === k ? 'var(--lbb-fg)' : 'var(--lbb-fg2)',
                  fontWeight: owned === k ? 600 : 500, fontSize: 11.5,
                  border: owned === k ? '1px solid var(--lbb-border2)' : '1px solid transparent',
                  cursor: 'pointer', fontFamily: 'inherit',
                }}>{l}</button>
              ))}
            </div>
          </section>

          {/* LB status */}
          <section>
            <div style={{ ...SECTION_LABEL, marginBottom: 8 }}>{t('map.lbStatus')}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {STATUS_OPTIONS.map(o => (
                <label key={o.k} style={{
                  display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px', borderRadius: 6,
                  background: status === o.k ? 'var(--lbb-accent-soft)' : 'transparent',
                  cursor: 'pointer', fontSize: 12,
                }}>
                  <input type="radio" name="status" checked={status === o.k} onChange={() => setStatus(o.k)} />
                  <span style={{ flex: 1, color: status === o.k ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)', fontWeight: status === o.k ? 600 : 500 }}>
                    {o.l}
                  </span>
                  <span style={{ fontSize: 10.5, color: 'var(--lbb-fg3)', fontFamily: 'var(--lbb-mono)' }}>
                    {o.n.toLocaleString()}
                  </span>
                </label>
              ))}
            </div>
          </section>

          {/* Search */}
          <section>
            <div style={{ ...SECTION_LABEL, marginBottom: 8 }}>{t('map.search')}</div>
            <Input size="sm" icon="search" placeholder={t('map.searchPlaceholder')} style={{ width: '100%' }}
              value={search} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)} />
          </section>

          {/* Display */}
          <section>
            <div style={{ ...SECTION_LABEL, marginBottom: 8 }}>{t('map.display')}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {[
                { l: t('map.displayOpts.clusterMarkers'),  v: DISPLAY_OPTS[0].v },
                { l: t('map.displayOpts.colorByDecade'),   v: DISPLAY_OPTS[1].v },
                { l: t('map.displayOpts.heatmapOverlay'),  v: DISPLAY_OPTS[2].v },
                { l: t('map.displayOpts.showVenueLabels'), v: DISPLAY_OPTS[3].v },
              ].map((opt, i) => (
                <label key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--lbb-fg2)' }}>
                  <input type="checkbox" defaultChecked={opt.v} />
                  {opt.l}
                </label>
              ))}
            </div>
          </section>

          <div style={{ flex: 1 }} />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Button variant="primary" size="sm" icon="map" block onClick={handleApplyFilters}>{t('map.applyFilters')}</Button>
            <Button variant="ghost"   size="sm"            block onClick={handleResetFilters}>{t('map.resetDefaults')}</Button>
          </div>
        </aside>

        {/* Map — live Leaflet iframe */}
        <section style={{ position: 'relative', minHeight: 0, overflow: 'hidden' }}>
          <iframe
            ref={iframeRef}
            src={`${MAP_URL}?embedded=1`}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 'none' }}
            title="Concert map"
          />
        </section>

        {/* Selected venue panel */}
        <aside style={{
          background: 'var(--lbb-surface)', borderLeft: '1px solid var(--lbb-border)',
          display: 'flex', flexDirection: 'column', minHeight: 0,
        }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--lbb-border)' }}>
            <div style={{ ...SECTION_LABEL, marginBottom: 6 }}>
              {t('map.selected', { era: selectedPinData.era })}
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--lbb-fg)' }}>{selectedPinData.l}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
              <Pill tone="info" soft>{t('map.shows', { count: selectedPinData.n })}</Pill>
              <span style={{ fontSize: 11, color: 'var(--lbb-fg3)' }}>· 4 owned · 3 wishlist · 1 missing</span>
            </div>
            <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
              <Button size="sm" variant="primary" icon="search" block>{t('map.openInSearch')}</Button>
              <Button size="sm" variant="ghost" icon="copy">Copy</Button>
            </div>
          </div>

          <div style={{ padding: '10px 14px 4px', ...SECTION_LABEL }}>
            {t('map.entriesHere')}
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 6px 8px' }}>
            {SELECTED_LBS.map((r, i) => (
              <button key={i} style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                padding: '7px 10px', marginBottom: 1, borderRadius: 6,
                background: 'transparent', color: 'var(--lbb-fg2)',
                border: '1px solid transparent', textAlign: 'left',
                fontFamily: 'inherit', cursor: 'pointer',
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: r.status === 'missing' ? 'var(--lbb-bad-bar)' : 'var(--lbb-ok-bar)',
                }} />
                <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 600, fontSize: 11.5, color: 'var(--lbb-accent-mid)' }}>{r.lb}</span>
                    <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 10.5, color: 'var(--lbb-fg3)' }}>{r.d}</span>
                    {r.owned && <Icon name="check" size={10} style={{ color: 'var(--lbb-ok-bar)' }} />}
                  </span>
                  <span style={{ fontSize: 10.5, color: 'var(--lbb-fg3)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.v}</span>
                </span>
              </button>
            ))}
          </div>

          <div style={{ padding: 12, borderTop: '1px solid var(--lbb-border)' }}>
            <div style={{
              padding: '8px 10px', borderRadius: 6,
              background: 'var(--lbb-info-bg)', border: '1px solid var(--lbb-info-bar)',
              fontSize: 11, color: 'var(--lbb-fg2)',
              display: 'flex', alignItems: 'flex-start', gap: 8,
            }}>
              <Icon name="info" size={11} style={{ color: 'var(--lbb-info-fg)', marginTop: 2 }} />
              <span>
                {t('map.mapInfoHint')}
              </span>
            </div>
          </div>
        </aside>

      </div>
    </div>
  )
}
