import React, { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BASE } from '../lib/api'

const PAGE = 100
const MODE_KEY = {
  all: 'tradingMatrix.modeAll',
  want: 'tradingMatrix.modeWant',
  offer: 'tradingMatrix.modeOffer',
} as const

interface Friend {
  id: number
  friend_name: string
  lb_count: number
}

interface MatrixFriend {
  id: number
  friend_name: string
  they_have_you_dont: number
  you_have_they_dont: number
  both_have: number
  potential: number
}

interface MatrixRow {
  lb_number: number
  date_str: string | null
  location: string | null
  you_have: boolean
  kind: 'want' | 'offer'
  cells: Record<string, boolean>
  best_friend_id: number
}

interface MatrixResult {
  friends: MatrixFriend[]
  total: number
  offset: number
  rows: MatrixRow[]
}

type Mode = 'all' | 'want' | 'offer'

const th: React.CSSProperties = {
  padding: '5px 8px', fontSize: 'var(--lbb-fs-10-5)', fontWeight: 600, color: 'var(--lbb-fg3)',
  borderBottom: '1px solid var(--lbb-border)', background: 'var(--lbb-surface2)',
  position: 'sticky', top: 0, whiteSpace: 'nowrap',
}
const td: React.CSSProperties = { padding: '4px 8px', color: 'var(--lbb-fg2)' }

/** Friends x shows batch-compare matrix with server-side paging and filtering. */
export function TradingMatrix({ friends }: { friends: Friend[] }) {
  const { t } = useTranslation()
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const [mode, setMode] = useState<Mode>('all')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<MatrixResult | null>(null)
  const [ids, setIds] = useState<number[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const run = useCallback(async (use: number[], m: Mode, query: string, off: number) => {
    setBusy(true)
    setError('')
    try {
      const r = await fetch(`${BASE}/api/trading/batch-compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ friend_ids: use, mode: m, q: query, limit: PAGE, offset: off }),
      })
      if (!r.ok) throw new Error()
      setData(await r.json())
    } catch {
      setError(t('tradingMatrix.error'))
    } finally {
      setBusy(false)
    }
  }, [t])

  // Re-query when filters/page change after an initial run.
  useEffect(() => {
    if (ids.length === 0) return
    const h = setTimeout(() => { void run(ids, mode, q, offset) }, q ? 250 : 0)
    return () => clearTimeout(h)
  }, [ids, mode, q, offset, run])

  const toggle = (id: number) => setPicked(p => {
    const n = new Set(p)
    if (n.has(id)) n.delete(id); else n.add(id)
    return n
  })

  const start = () => {
    setOffset(0)
    setIds([...picked])
  }

  const nameOf = (id: number) => data?.friends.find(f => f.id === id)?.friend_name ?? String(id)
  const btn: React.CSSProperties = {
    height: 26, padding: '0 10px', borderRadius: 6, border: '1px solid var(--lbb-border)',
    background: 'var(--lbb-surface2)', color: 'var(--lbb-fg2)', cursor: 'pointer',
    fontSize: 'var(--lbb-fs-12)', fontFamily: 'inherit',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minHeight: 0, flex: 1 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <span style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
          {t('tradingMatrix.pickFriends')}
        </span>
        <button style={btn} onClick={() => setPicked(new Set(friends.map(f => f.id)))}>
          {t('tradingMatrix.selectAll')}
        </button>
        <button style={btn} onClick={() => setPicked(new Set())}>{t('tradingMatrix.selectNone')}</button>
        {friends.map(f => (
          <label key={f.id} style={{ fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg2)' }}>
            <input type="checkbox" checked={picked.has(f.id)} onChange={() => toggle(f.id)} />{' '}
            {f.friend_name}
          </label>
        ))}
        <button style={{ ...btn, fontWeight: 600 }} disabled={picked.size === 0 || busy} onClick={start}>
          {t('tradingMatrix.run')}
        </button>
      </div>

      {!data && !error && (
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-13)', padding: 24 }}>
          {picked.size === 0 ? t('tradingMatrix.needFriends') : t('tradingMatrix.empty')}
        </div>
      )}
      {error && <div style={{ color: 'var(--lbb-err-fg)', fontSize: 'var(--lbb-fs-12)' }}>{error}</div>}

      {data && (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)' }}>
            {data.friends.map(f => (
              <span key={f.id}>
                {t('tradingMatrix.summary', {
                  name: f.friend_name, want: f.they_have_you_dont, offer: f.you_have_they_dont,
                })}
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {(['all', 'want', 'offer'] as Mode[]).map(m => (
              <button
                key={m}
                style={{ ...btn, fontWeight: mode === m ? 700 : 400 }}
                onClick={() => { setMode(m); setOffset(0) }}
              >
                {t(MODE_KEY[m])}
              </button>
            ))}
            <input
              value={q}
              placeholder={t('tradingMatrix.search')}
              onChange={e => { setQ(e.target.value); setOffset(0) }}
              style={{
                flex: 1, maxWidth: 260, height: 26, padding: '0 8px', borderRadius: 6,
                border: '1px solid var(--lbb-border2)', background: 'var(--lbb-bg)',
                color: 'var(--lbb-fg)', fontFamily: 'inherit', fontSize: 'var(--lbb-fs-12)',
              }}
            />
          </div>

          {data.rows.length === 0 ? (
            <div style={{ color: 'var(--lbb-fg3)', fontSize: 'var(--lbb-fs-13)', padding: 24 }}>
              {t('tradingMatrix.noRows')}
            </div>
          ) : (
            <div style={{ overflow: 'auto', flex: 1, minHeight: 120, border: '1px solid var(--lbb-border)', borderRadius: 8 }}>
              <table style={{ borderCollapse: 'collapse', fontSize: 'var(--lbb-fs-12)', width: '100%' }}>
                <thead>
                  <tr>
                    <th style={{ ...th, textAlign: 'left' }}>{t('tradingMatrix.colShow')}</th>
                    <th style={th}>{t('tradingMatrix.colBest')}</th>
                    {data.friends.map(f => (
                      <th key={f.id} style={th} title={f.friend_name}>
                        {f.friend_name.length > 12 ? `${f.friend_name.slice(0, 11)}…` : f.friend_name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map(r => (
                    <tr key={r.lb_number} style={{ borderBottom: '1px solid var(--lbb-border)' }}>
                      <td style={td}>
                        <strong style={{ color: 'var(--lbb-accent-mid)', fontVariantNumeric: 'tabular-nums' }}>
                          {String(r.lb_number).padStart(5, '0')}
                        </strong>{' '}
                        {r.date_str ?? ''} {r.location ?? ''}{' '}
                        <em style={{ color: r.kind === 'want' ? 'var(--lbb-ok-fg)' : 'var(--lbb-fg3)' }}>
                          {t(r.kind === 'want' ? 'tradingMatrix.want' : 'tradingMatrix.offer')}
                        </em>
                      </td>
                      <td style={{ ...td, textAlign: 'center', fontWeight: 600 }} title={t('tradingMatrix.bestHint')}>
                        {nameOf(r.best_friend_id)}
                      </td>
                      {data.friends.map(f => {
                        const has = r.cells[String(f.id)]
                        // Highlight the cells that make a trade: want = they have it; offer = they lack it.
                        const useful = r.kind === 'want' ? has : !has
                        return (
                          <td
                            key={f.id}
                            title={has ? t('tradingMatrix.has') : t('tradingMatrix.lacks')}
                            style={{
                              ...td, textAlign: 'center',
                              background: useful ? 'var(--lbb-ok-bg)' : 'transparent',
                              color: useful ? 'var(--lbb-ok-fg)' : 'var(--lbb-fg3)',
                              outline: f.id === r.best_friend_id ? '1px solid var(--lbb-ok-bar)' : 'none',
                            }}
                          >
                            {has ? '●' : '○'}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>
            <button style={btn} disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              {t('tradingMatrix.prev')}
            </button>
            <span>
              {t('tradingMatrix.page', {
                from: data.total === 0 ? 0 : data.offset + 1,
                to: Math.min(data.offset + PAGE, data.total),
                total: data.total,
              })}
            </span>
            <button style={btn} disabled={offset + PAGE >= data.total || busy} onClick={() => setOffset(offset + PAGE)}>
              {t('tradingMatrix.next')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
