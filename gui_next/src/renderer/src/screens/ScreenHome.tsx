import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Icon } from '../components/Icon'
import { Button, Card, Stat, Pill } from '../components'
import { TableShell, TH, TR, TD } from '../components'

const BASE = window.api.flaskBase

interface HomeStats {
  collection_count: number
  wishlist_count: number
  missing_count: number
  bootleg_count: number
  checksum_count: number
  latest_lb: number
  last_import: string | null
}

interface ActivityRow {
  when: string | null
  action: string
  target: string
  result: string
  type: 'import' | 'rename' | 'forum'
}

type ToastTone = 'ok' | 'bad' | 'info'

function Toast({ msg, tone, onDone }: { msg: string; tone: ToastTone; onDone: () => void }) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    timerRef.current = setTimeout(onDone, 3500)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [onDone])
  const bg = tone === 'ok' ? 'var(--lbb-ok-bar)' : tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-accent-mid)'
  return (
    <div style={{
      position: 'fixed', bottom: 28, left: '50%', transform: 'translateX(-50%)',
      background: bg, color: '#fff', padding: '9px 18px', borderRadius: 8,
      fontSize: 'var(--lbb-fs-13)', fontWeight: 600, zIndex: 9999, boxShadow: '0 4px 16px rgba(0,0,0,.25)',
      pointerEvents: 'none',
    }}>{msg}</div>
  )
}

function fmtNum(n: number): string {
  return n.toLocaleString()
}

function fmtLb(n: number): string {
  return `LB-${String(n).padStart(5, '0')}`
}

function relTime(iso: string | null): string {
  if (!iso) return 'never'
  const d = new Date(iso)
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86_400_000)
  if (diffDays === 0) return 'today'
  if (diffDays === 1) return 'yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  return d.toISOString().slice(0, 10)
}

const STEP_STRIPS = [
  { n: 1, label: 'Verify checksums', icon: 'verify' },
  { n: 2, label: 'Lookup LB#',       icon: 'lookup' },
  { n: 3, label: 'Rename folder',    icon: 'rename' },
  { n: 4, label: 'Check LBDIR',      icon: 'lbdir'  },
]

const JUMP_TILES = [
  { id: 'collection', icon: 'collection', label: 'My Collection'    },
  { id: 'search',     icon: 'search',     label: 'Search master DB' },
  { id: 'bootlegs',   icon: 'bootlegs',   label: 'Bootleg catalog'  },
  { id: 'map',        icon: 'map',        label: 'Concert map'      },
]

const TIPS = [
  { icon: 'user', text: <>Maintaining master data? Enable <strong>Curator mode</strong> in Settings to reveal DB&nbsp;Editor and Scraper.</> },
  { icon: 'star', text: <>Star a filter combo in <strong>Search</strong> to make it a one-click saved view.</> },
]

function fmtActivity(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
}

const TYPE_COLOUR: Record<string, string> = {
  import: 'var(--lbb-accent-mid)',
  rename: 'var(--lbb-ok-bar)',
  forum:  'var(--lbb-fg3)',
}

export function ScreenHome(): React.JSX.Element {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [stats,        setStats]        = useState<HomeStats | null>(null)
  const [activity,     setActivity]     = useState<ActivityRow[]>([])
  const [activityAll,  setActivityAll]  = useState<ActivityRow[] | null>(null)
  const [checkBusy,    setCheckBusy]    = useState(false)
  const [showFullLog,  setShowFullLog]  = useState(false)
  const [toast,        setToast]        = useState<{ msg: string; tone: ToastTone } | null>(null)

  const showToast = useCallback((msg: string, tone: ToastTone) => setToast({ msg, tone }), [])

  useEffect(() => {
    fetch(`${BASE}/api/home/stats`)
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then(setStats)
      .catch(() => { /* stats stay null, UI shows '—' */ })
  }, [])

  useEffect(() => {
    fetch(`${BASE}/api/activity/log?limit=10`)
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then((rows: ActivityRow[]) => setActivity(rows))
      .catch(() => { /* activity stays empty */ })
  }, [])

  const handleCheckUpdate = useCallback(async () => {
    setCheckBusy(true)
    try {
      const r = await fetch(`${BASE}/api/flat_file/discover`)
      const data = await r.json() as {
        available?: boolean | null
        current_release?: { zip_filename?: string } | null
        error?: string
      }
      if (data.error) { showToast(t('home.toast.error', { error: data.error }), 'bad'); return }
      if (data.available) {
        showToast(t('home.toast.newRelease', { filename: data.current_release?.zip_filename ?? '' }), 'ok')
      } else {
        showToast(t('home.toast.upToDate'), 'info')
      }
    } catch (e) {
      showToast(t('home.toast.checkFailed', { message: (e as Error).message }), 'bad')
    } finally {
      setCheckBusy(false)
    }
  }, [showToast])

  const handleViewFullLog = useCallback(async () => {
    setShowFullLog(true)
    if (activityAll) return
    try {
      const r = await fetch(`${BASE}/api/activity/log?limit=0`)
      const rows = (await r.json()) as ActivityRow[]
      setActivityAll(rows)
    } catch {
      setActivityAll([])
    }
  }, [activityAll])

  function onNav(id: string): void {
    navigate(id === 'home' ? '/' : `/${id}`)
  }

  const d = (n: number | undefined, fallback = '—') =>
    n !== undefined ? fmtNum(n) : fallback

  return (
    <div style={{ padding: '24px 28px 36px', maxWidth: 1680, margin: '0 auto' }}>

      {/* ── Welcome strip ──────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
        marginBottom: 22, gap: 24,
      }}>
        <div>
          <div style={{ fontSize: 'var(--lbb-fs-11)', letterSpacing: 0.14, textTransform: 'uppercase', color: 'var(--lbb-fg3)', fontWeight: 600 }}>
            {t('home.welcome')}
          </div>
          <h1 style={{ margin: '6px 0 0', fontSize: 'var(--lbb-fs-28)', fontWeight: 700, letterSpacing: -0.015 }}>
            {t('home.collectionTitle', { count: d(stats?.collection_count, '…') })}
          </h1>
          <div style={{ marginTop: 4, fontSize: 'var(--lbb-fs-13)', color: 'var(--lbb-fg3)' }}>
            {t('home.dbStatus', { when: stats ? relTime(stats.last_import) : '…' })}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <Button icon="refresh" variant="secondary" size="md" disabled={checkBusy} onClick={handleCheckUpdate}>
            {checkBusy ? t('home.checking') : t('home.checkUpdate')}
          </Button>
          <Button icon="drop" variant="primary" size="md" onClick={() => onNav('pipeline')}>
            {t('home.ingestNew')}
          </Button>
        </div>
      </div>

      {/* ── Primary two-column grid ─────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.45fr 1fr', gap: 18, marginBottom: 18 }}>

        {/* Hero ingest card */}
        <div style={{
          background: 'linear-gradient(180deg, var(--lbb-accent-soft), var(--lbb-surface))',
          border: '1px solid var(--lbb-accent-mid)',
          borderRadius: 12, padding: 22,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{
              fontSize: 'var(--lbb-fs-10)', letterSpacing: 0.14, textTransform: 'uppercase',
              color: 'var(--lbb-accent-mid)', fontWeight: 700,
              padding: '2px 7px', borderRadius: 4,
              background: 'var(--lbb-surface)', border: '1px solid var(--lbb-accent-mid)',
            }}>{t('home.primaryWorkflow')}</span>
            <span style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)' }}>{t('home.pipelineTagline')}</span>
          </div>
          <h2 style={{ margin: '2px 0 4px', fontSize: 'var(--lbb-fs-22)', fontWeight: 700, letterSpacing: -0.01 }}>
            {t('home.ingestTitle')}
          </h2>
          <p style={{ margin: '0 0 16px', color: 'var(--lbb-fg2)', fontSize: 'var(--lbb-fs-13-5)', maxWidth: '60ch' }}
            dangerouslySetInnerHTML={{ __html: t('home.ingestDesc') }}
          />

          <button
            type="button"
            onClick={() => onNav('pipeline')}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14,
              padding: '30px 20px', borderRadius: 10,
              background: 'var(--lbb-surface)',
              border: '2px dashed var(--lbb-accent-mid)',
              color: 'var(--lbb-fg2)', fontSize: 'var(--lbb-fs-13-5)', cursor: 'pointer', fontFamily: 'inherit',
            }}
          >
            <Icon name="folderPlus" size={22} style={{ color: 'var(--lbb-accent-mid)' }} />
            <span>
              <strong style={{ color: 'var(--lbb-fg)' }}>{t('home.dragHere')}</strong>
              {' '}&nbsp;·&nbsp;{' '}{t('home.orClickBrowse')}
            </span>
          </button>

          <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            {STEP_STRIPS.map(s => (
              <div key={s.n} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '9px 10px', borderRadius: 8,
                background: 'var(--lbb-surface)',
                border: '1px solid var(--lbb-border)',
              }}>
                <span style={{
                  width: 18, height: 18, borderRadius: '50%',
                  background: 'var(--lbb-accent-mid)', color: 'var(--lbb-accent-onMid)',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 'var(--lbb-fs-10)', fontWeight: 700, flexShrink: 0,
                }}>{s.n}</span>
                <Icon name={s.icon} size={14} style={{ color: 'var(--lbb-fg2)' }} />
                <span style={{ fontSize: 'var(--lbb-fs-11-5)', fontWeight: 500, color: 'var(--lbb-fg2)' }}>
                  {s.n === 1 ? t('home.stepVerify') : s.n === 2 ? t('home.stepLookup') : s.n === 3 ? t('home.stepRename') : t('home.stepLbdir')}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* At a glance + Jump to */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card title={t('home.atAGlance')} subtitle={t('home.atAGlanceSub')} pad={16}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <Stat value={d(stats?.collection_count, '…')} label={t('home.inMyCollection')} />
              <Stat value={d(stats?.missing_count,    '…')} label={t('home.missingEntries')} />
              <Stat value={d(stats?.wishlist_count,   '…')} label={t('home.onWishlist')} />
              <Stat value={d(stats?.bootleg_count,    '…')} label={t('home.bootlegTitles')} />
            </div>
            <div style={{
              marginTop: 14, padding: '10px 12px', borderRadius: 8,
              background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
              display: 'flex', alignItems: 'center', gap: 10, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)',
            }}>
              <Icon name="check" size={13} style={{ color: 'var(--lbb-ok-bar)' }} />
              <span>
                <strong style={{ color: 'var(--lbb-fg)' }}>
                  {d(stats?.checksum_count, '…')}
                </strong>{' '}{t('home.checksumsIndexed')}
              </span>
            </div>
          </Card>

          <Card title={t('home.jumpTo')} pad={14}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {JUMP_TILES.map(tile => {
                const sub =
                  tile.id === 'collection' ? d(stats?.collection_count, '…')
                  : tile.id === 'bootlegs' ? d(stats?.bootleg_count,    '…')
                  : tile.id === 'search'   ? d(stats?.latest_lb,        '…')
                  : '—'
                const tileLabel =
                  tile.id === 'collection' ? t('home.jumpCollection')
                  : tile.id === 'search'   ? t('home.jumpSearch')
                  : tile.id === 'bootlegs' ? t('home.jumpBootlegs')
                  : t('home.jumpMap')
                return (
                  <button
                    key={tile.id}
                    type="button"
                    onClick={() => onNav(tile.id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px',
                      background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
                      borderRadius: 8, cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit',
                      color: 'var(--lbb-fg)',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'var(--lbb-surface2)' }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'var(--lbb-surface)' }}
                  >
                    <span style={{
                      width: 30, height: 30, borderRadius: 7, flexShrink: 0,
                      background: 'var(--lbb-accent-soft)', color: 'var(--lbb-accent-mid)',
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Icon name={tile.icon} size={15} />
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 'var(--lbb-fs-12-5)', fontWeight: 600 }}>{tileLabel}</div>
                      <div style={{ fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontVariantNumeric: 'tabular-nums' }}>
                        {sub}
                      </div>
                    </div>
                    <Icon name="chevRight" size={12} style={{ color: 'var(--lbb-fg3)' }} />
                  </button>
                )
              })}
            </div>
          </Card>
        </div>
      </div>

      {/* ── Bottom row ─────────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.45fr 1fr', gap: 18 }}>

        {/* Recent activity */}
        <Card
          title={t('home.recentActivity')}
          subtitle={t('home.recentActivitySub')}
          action={
            <button
              type="button"
              onClick={handleViewFullLog}
              style={{
                background: 'transparent', border: 'none',
                color: 'var(--lbb-accent-mid)',
                fontSize: 'var(--lbb-fs-12)', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
              }}
            >{t('home.viewFullLog')}</button>
          }
          pad={0}
        >
          <TableShell stickyHeader={false}>
            <colgroup>
              <col style={{ width: 3 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 120 }} />
              <col />
              <col style={{ width: 180 }} />
            </colgroup>
            <thead>
              <tr>
                <TH style={{ background: 'var(--lbb-surface)' }}>{' '}</TH>
                <TH>{t('home.colWhen')}</TH>
                <TH>{t('home.colAction')}</TH>
                <TH>{t('home.colTarget')}</TH>
                <TH>{t('home.colResult')}</TH>
              </tr>
            </thead>
            <tbody>
              {activity.length === 0 ? (
                <TR edge="mute">
                  <TD mono dim>—</TD>
                  <TD colSpan={3} style={{ color: 'var(--lbb-fg3)', fontStyle: 'italic' }}>
                    {t('home.noActivity')}
                  </TD>
                  <TD />
                </TR>
              ) : activity.map((row, i) => (
                <TR key={i} edge={undefined}>
                  <TD>
                    <span style={{
                      display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
                      background: TYPE_COLOUR[row.type] ?? 'var(--lbb-fg3)',
                    }} />
                  </TD>
                  <TD mono dim>{fmtActivity(row.when)}</TD>
                  <TD>{row.action}</TD>
                  <TD style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {row.target}
                  </TD>
                  <TD style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {row.result}
                  </TD>
                </TR>
              ))}
            </tbody>
          </TableShell>
        </Card>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Card title={t('home.tips')} pad={14}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {TIPS.map((tip, i) => (
                <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <Icon name={tip.icon} size={14} style={{ color: 'var(--lbb-fg3)', marginTop: 2 }} />
                  <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg2)', lineHeight: 1.5 }}>
                    {i === 0 ? t('home.tip1') : t('home.tip2')}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* ── Full log modal ──────────────────────────────────────────────────── */}
      {showFullLog && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,.55)', zIndex: 200,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={() => setShowFullLog(false)}
        >
          <div
            style={{
              background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
              borderRadius: 12, padding: 0, width: 820, maxWidth: '94vw',
              maxHeight: '80vh', display: 'flex', flexDirection: 'column',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{
              padding: '16px 20px', borderBottom: '1px solid var(--lbb-border)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            }}>
              <span style={{ fontWeight: 700, fontSize: 'var(--lbb-fs-15)' }}>{t('home.fullActivityLog')}</span>
              <button
                type="button"
                onClick={() => setShowFullLog(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-18)' }}
              >✕</button>
            </div>
            <div style={{ overflow: 'auto', flex: 1 }}>
              <TableShell stickyHeader>
                <colgroup>
                  <col style={{ width: 3 }} />
                  <col style={{ width: 145 }} />
                  <col style={{ width: 120 }} />
                  <col />
                  <col style={{ width: 220 }} />
                </colgroup>
                <thead>
                  <tr>
                    <TH>{' '}</TH>
                    <TH>{t('home.colWhen')}</TH>
                    <TH>{t('home.colAction')}</TH>
                    <TH>{t('home.colTarget')}</TH>
                    <TH>{t('home.colResult')}</TH>
                  </tr>
                </thead>
                <tbody>
                  {activityAll === null ? (
                    <TR edge="mute">
                      <TD mono dim>—</TD>
                      <TD colSpan={3} style={{ color: 'var(--lbb-fg3)' }}>{t('common.loading')}</TD>
                      <TD />
                    </TR>
                  ) : activityAll.length === 0 ? (
                    <TR edge="mute">
                      <TD mono dim>—</TD>
                      <TD colSpan={3} style={{ color: 'var(--lbb-fg3)', fontStyle: 'italic' }}>{t('home.noActivity')}</TD>
                      <TD />
                    </TR>
                  ) : activityAll.map((row, i) => (
                    <TR key={i} edge={undefined}>
                      <TD>
                        <span style={{
                          display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
                          background: TYPE_COLOUR[row.type] ?? 'var(--lbb-fg3)',
                        }} />
                      </TD>
                      <TD mono dim>{fmtActivity(row.when)}</TD>
                      <TD>{row.action}</TD>
                      <TD style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {row.target}
                      </TD>
                      <TD style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {row.result}
                      </TD>
                    </TR>
                  ))}
                </tbody>
              </TableShell>
            </div>
          </div>
        </div>
      )}

      {toast && <Toast msg={toast.msg} tone={toast.tone} onDone={() => setToast(null)} />}
    </div>
  )
}
