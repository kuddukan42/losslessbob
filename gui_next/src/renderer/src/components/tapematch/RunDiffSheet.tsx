/**
 * §12 — the run diff, for the TapeMatch curation screen (Phase 8).
 *
 * The question it answers is never "what are the numbers" but **"does the new
 * run invalidate what I already decided?"**, so the sections are ordered to
 * end on the curator's own judgments. It is not a text diff of two report.md
 * files: a line diff would show hundreds of changed digits and bury the four
 * facts that matter. This diffs *conclusions*.
 *
 * The diff itself is `lib/runDiff.ts`, a pure function of two snapshots from
 * `GET /api/tapematch/run_snapshot` — neither run is mutated by viewing.
 *
 * §12.1 ("what changed in the pipeline") is NOT built and cannot be: the cause
 * list can't be derived from two artifacts' numbers, it needs runs to record
 * their own threshold set, and DECISIONS Q2 made that forward-only. The
 * section says so rather than guessing a cause.
 */

import React, { useMemo, useState } from 'react'
import { Button, Pill } from '../primitives'
import { SheetShell } from './SheetShell'
import { diffRuns, type RunDiff, type RunMeta, type RunSnapshot } from '../../lib/runDiff'

const JUDGMENT_LABEL: Record<string, string> = {
  confirmed_same: 'Same source',
  confirmed_different: 'Different',
  uncertain: 'Uncertain',
  lb_wrong: 'LB wrong',
}
const JUDGMENT_TONE: Record<string, 'ok' | 'info' | 'warn' | 'bad'> = {
  confirmed_same: 'ok', confirmed_different: 'info', uncertain: 'warn', lb_wrong: 'bad',
}

const IMPACT_COPY: Record<string, { tone: 'ok' | 'bad' | 'mute' | 'warn'; text: string }> = {
  unchanged: {
    tone: 'mute',
    text: "The algorithm's call for this pair didn't change between runs — your judgment "
      + 'still stands against the same evidence.',
  },
  corroborated: {
    tone: 'ok',
    text: 'The algorithm flipped its call and now agrees with you. Your judgment is '
      + 'corroborated; nothing to redo.',
  },
  contradicted: {
    tone: 'bad',
    text: 'The algorithm flipped its call and now contradicts you. This judgment was '
      + 'recorded against the older run — re-examine it.',
  },
  orphaned: {
    tone: 'warn',
    text: 'This pair exists in only one of the two runs. The judgment is kept and marked '
      + 'orphaned — a re-run never deletes a human decision.',
  },
}

function short(lb: number): string {
  return String(lb).padStart(5, '0')
}

function fmtRunAt(run: RunMeta | null): string {
  if (!run?.run_at) return run?.run_id ?? '—'
  const d = new Date(run.run_at)
  return Number.isNaN(d.getTime()) ? String(run.run_at) : d.toLocaleString()
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginTop: 28, paddingTop: 12, borderTop: '1px solid var(--lbb-border)' }}>
      <h2 style={{ margin: 0, font: '700 13px var(--lbb-font)', color: 'var(--lbb-fg)' }}>
        {title}
      </h2>
      {children}
    </section>
  )
}

function StatTile({
  figure, label, tone,
}: { figure: string; label: string; tone: 'ok' | 'warn' | 'mute' | 'bad' }) {
  return (
    <div style={{
      border: '1px solid var(--lbb-border)', borderRadius: 8, padding: '10px 12px',
      background: 'var(--lbb-surface2)',
    }}>
      <div style={{
        font: '800 20px var(--lbb-mono)', color: `var(--lbb-${tone}-fg)`,
        fontVariantNumeric: 'tabular-nums',
      }}>{figure}</div>
      <div style={{ fontSize: 10.5, color: 'var(--lbb-fg3)', marginTop: 2 }}>{label}</div>
    </div>
  )
}

function RunCard({
  role, run, runs, onPick, head,
}: {
  role: string
  run: RunMeta | null
  runs: RunMeta[]
  onPick: (runId: string) => void
  head: boolean
}) {
  return (
    <div style={{
      border: `1px solid var(--lbb-${head ? 'border2' : 'border'})`, borderRadius: 8,
      background: 'var(--lbb-surface2)', padding: '10px 12px', minWidth: 0,
    }}>
      <div style={{
        font: '700 9.5px var(--lbb-font)', textTransform: 'uppercase',
        letterSpacing: '.07em', color: 'var(--lbb-fg3)',
      }}>{role}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
        {/* The design leaves room for a select here and calls the pickers "the
            one obvious gap" in its own prototype (Q8). */}
        <select
          value={run?.run_id ?? ''}
          onChange={e => onPick(e.target.value)}
          style={{
            font: '700 12px var(--lbb-mono)', color: 'var(--lbb-fg)',
            background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
            borderRadius: 6, padding: '3px 6px', maxWidth: '100%',
          }}
        >
          {runs.map(r => (
            <option key={r.run_id} value={r.run_id}>{r.run_id}</option>
          ))}
        </select>
        <Pill tone={head ? 'info' : 'mute'} soft>{head ? 'in review' : 'superseded'}</Pill>
      </div>
      <div style={{
        marginTop: 7, font: '500 10.5px/1.6 var(--lbb-mono)', color: 'var(--lbb-fg3)',
      }}>
        <div>{fmtRunAt(run)}</div>
        <div>
          {run?.n_sources_ran ?? '—'} recordings · {run?.n_families ?? '—'} families
          {run?.duration_sec != null && ` · ${Math.round(run.duration_sec)}s`}
        </div>
        {/* §12's run bar wants each run's thresholds here — "putting thresholds
            in the run header is the point of the run bar". The runs table has
            no threshold set (Q2: forward-only), so the slot stays honest. */}
        <div>thresholds not recorded by this run</div>
      </div>
    </div>
  )
}

/** §12.3 — the §5 matrix geometry, re-encoded to show change, not value. */
function DeltaMatrix({
  diff, lbs, onOpenPair,
}: {
  diff: RunDiff
  lbs: number[]
  onOpenPair: (a: number, b: number) => void
}) {
  const byKey = useMemo(() => new Map(diff.pairs.map(p => [p.key, p])), [diff])
  const n = lbs.length
  if (n < 2) return null
  return (
    <div style={{ overflowX: 'auto', marginTop: 10 }}>
      <div style={{
        display: 'grid', gridTemplateColumns: `52px repeat(${n}, minmax(0,1fr))`, gap: 2,
        maxWidth: 760,
      }}>
        <div />
        {lbs.map(lb => (
          <div key={`h${lb}`} style={{
            font: '600 10px var(--lbb-mono)', color: 'var(--lbb-fg3)', textAlign: 'center',
            paddingBottom: 3, alignSelf: 'end',
          }}>{short(lb)}</div>
        ))}
        {lbs.map(a => (
          <React.Fragment key={`r${a}`}>
            <div style={{
              font: '600 10px var(--lbb-mono)', color: 'var(--lbb-fg3)',
              display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 5,
            }}>{short(a)}</div>
            {lbs.map(b => {
              if (a === b) {
                return (
                  <div key={`${a}-${b}`} style={{
                    background: 'var(--lbb-surface2)', border: '1px solid var(--lbb-border)',
                    borderRadius: 4, aspectRatio: '1',
                  }} />
                )
              }
              const p = byKey.get(a < b ? `${a}|${b}` : `${b}|${a}`)
              const d = p && p.corrBase != null && p.corrHead != null
                ? (p.corrHead - p.corrBase) * 100 : null
              const t = d == null ? 0 : Math.min(72, Math.abs(d) * 2.4)
              const bg = d == null || Math.abs(d) < 1
                ? 'var(--lbb-surface2)'
                : `color-mix(in oklab, var(--lbb-${d > 0 ? 'ok' : 'bad'}-bar) ${t}%, var(--lbb-surface))`
              return (
                <button
                  key={`${a}-${b}`}
                  type="button"
                  onClick={() => onOpenPair(a, b)}
                  title={p ? `${short(a)} × ${short(b)} — ${d == null ? 'not comparable'
                    : `${d > 0 ? '+' : ''}${d.toFixed(0)} points`}${p.flipped ? ' · call flipped' : ''}`
                    : 'not measured in either run'}
                  style={{
                    aspectRatio: '1', border: p?.flipped
                      ? '2px solid var(--lbb-fg)' : '1px solid var(--lbb-border)',
                    borderRadius: 4, background: bg, cursor: 'pointer', position: 'relative',
                    font: '600 11px var(--lbb-mono)',
                    color: d != null && Math.abs(d) >= 18 ? 'var(--lbb-fg)' : 'var(--lbb-fg2)',
                  }}
                >
                  {d == null ? 'n/c' : Math.abs(d) < 1 ? '·' : `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(0)}`}
                  {p?.flipped && (
                    <span style={{
                      position: 'absolute', top: 1, right: 3,
                      font: '700 8px var(--lbb-mono)', color: 'var(--lbb-fg)',
                    }}>!</span>
                  )}
                </button>
              )
            })}
          </React.Fragment>
        ))}
      </div>
      {/* The legend deliberately avoids the semantic tone names: green/red here
          means "moved toward/away from similar", not good/bad. */}
      <div style={{
        display: 'flex', gap: 14, marginTop: 8, fontSize: 10.5, color: 'var(--lbb-fg3)',
        alignItems: 'center', flexWrap: 'wrap',
      }}>
        <span><Swatch color="var(--lbb-bad-bar)" /> less similar</span>
        <span><Swatch color="var(--lbb-surface2)" /> unchanged</span>
        <span><Swatch color="var(--lbb-ok-bar)" /> more similar</span>
        <span style={{ fontFamily: 'var(--lbb-mono)' }}>! = the call flipped</span>
      </div>
    </div>
  )
}

function Swatch({ color }: { color: string }) {
  return <span style={{
    display: 'inline-block', width: 9, height: 9, borderRadius: 2, background: color,
    border: '1px solid var(--lbb-border)', marginRight: 5, verticalAlign: 'middle',
  }} />
}

function DeltaValue({ from, to }: { from: number | null; to: number | null }) {
  if (from == null || to == null) {
    return <span style={{ color: 'var(--lbb-fg3)' }}>n/c</span>
  }
  const d = to - from
  return (
    <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11 }}>
      <span style={{ color: 'var(--lbb-fg3)' }}>{from.toFixed(3)}</span>
      <span style={{ color: 'var(--lbb-fg3)' }}> → </span>
      <span style={{ color: 'var(--lbb-fg)' }}>{to.toFixed(3)}</span>
      {Math.abs(d) >= 0.001 && (
        <span style={{
          marginLeft: 6,
          color: d > 0 ? 'var(--lbb-ok-fg)' : 'var(--lbb-bad-fg)',
        }}>{d > 0 ? '+' : '−'}{Math.abs(d).toFixed(3)}</span>
      )}
    </span>
  )
}

export interface RunDiffSheetProps {
  date: string
  venue: string | null
  runs: RunMeta[]
  baseId: string | null
  headId: string | null
  onPickBase: (runId: string) => void
  onPickHead: (runId: string) => void
  baseSnapshot: RunSnapshot | null
  headSnapshot: RunSnapshot | null
  loading: boolean
  onClose: () => void
  onOpenPair: (a: number, b: number) => void
}

export function RunDiffSheet(props: RunDiffSheetProps): React.JSX.Element {
  const {
    date, venue, runs, baseId, headId, onPickBase, onPickHead,
    baseSnapshot, headSnapshot, loading, onClose, onOpenPair,
  } = props
  const [showAllPairs, setShowAllPairs] = useState(false)

  const diff = useMemo(
    () => (baseSnapshot && headSnapshot ? diffRuns(baseSnapshot, headSnapshot) : null),
    [baseSnapshot, headSnapshot],
  )
  const lbs = useMemo(
    () => (headSnapshot?.sources ?? []).map(s => s.lb_number).sort((a, b) => a - b),
    [headSnapshot],
  )

  const listedPairs = useMemo(() => {
    if (!diff) return []
    const shown = diff.pairs.filter(p => p.flipped || p.absDelta >= 0.01)
    return showAllPairs ? diff.pairs : shown
  }, [diff, showAllPairs])

  return (
    <SheetShell
      name="Run diff"
      path={venue ? `${date} · ${venue}` : date}
      label={`Run diff — ${date}`}
      onClose={onClose}
      actions={
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close run diff">✕</Button>
      }
    >
      {runs.length < 2 ? (
        <div style={{ color: 'var(--lbb-fg3)', fontSize: 12, lineHeight: 1.6 }}>
          This date has only {runs.length === 1 ? 'one run' : 'no runs'} — there is nothing to
          compare. A diff appears once the date has been analysed twice.
        </div>
      ) : (
        <>
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 12, alignItems: 'center',
          }}>
            <RunCard
              role="base — earlier run" run={diff?.base ?? null} runs={runs}
              onPick={onPickBase} head={false}
            />
            <div style={{ color: 'var(--lbb-fg3)', fontSize: 16 }}>→</div>
            <RunCard
              role="head — current run" run={diff?.head ?? null} runs={runs}
              onPick={onPickHead} head
            />
          </div>

          {loading || !diff ? (
            <div style={{ marginTop: 22, color: 'var(--lbb-fg3)', fontSize: 12 }}>
              Loading both runs…
            </div>
          ) : baseId === headId ? (
            <div style={{ marginTop: 22, color: 'var(--lbb-fg3)', fontSize: 12 }}>
              Both pickers are on the same run — pick two different runs to see a diff.
            </div>
          ) : (
            <>
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 10,
                marginTop: 16,
              }}>
                <StatTile
                  tone="ok"
                  figure={`${diff.tiles.familiesBase}→${diff.tiles.familiesHead}`}
                  label={`families · ${diff.tiles.merged} merged · ${diff.tiles.split} split`}
                />
                <StatTile tone="warn" figure={String(diff.tiles.flipped)} label="calls flipped" />
                <StatTile
                  tone="mute" figure={String(diff.tiles.heldButMoved)}
                  label="values moved, call held"
                />
                <StatTile
                  tone={diff.tiles.judgmentsToReexamine > 0 ? 'bad' : 'mute'}
                  figure={String(diff.tiles.judgmentsToReexamine)}
                  label="judgments to re-examine"
                />
              </div>

              <Section title="1. What changed in the pipeline">
                <p style={{ margin: '10px 0 0', font: '400 12.5px/1.6 var(--lbb-font)', color: 'var(--lbb-fg2)' }}>
                  Same audio, same recordings — every difference below comes from the analysis,
                  not the tapes.
                </p>
                <div style={{
                  marginTop: 10, padding: '9px 12px', borderRadius: 6,
                  background: 'var(--lbb-info-bg)', border: '1px solid var(--lbb-info-bar)',
                  fontSize: 11.5, lineHeight: 1.6, color: 'var(--lbb-info-fg)',
                }}>
                  <strong>The cause list isn&rsquo;t derivable from these two runs.</strong> Naming
                  what changed — a threshold move, a demoted signal — requires each run to record
                  its own threshold set, and runs on disk don&rsquo;t. Runs analysed from now on
                  can carry it; until then the sections below report the effects without claiming
                  a cause.
                </div>
              </Section>

              <Section title="2. Families">
                <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {diff.families.map(f => (
                    <div key={f.id} style={{
                      display: 'grid', gridTemplateColumns: '112px minmax(0,1fr) auto', gap: 11,
                      alignItems: 'start',
                    }}>
                      <div>
                        <div style={{ font: '700 11.5px var(--lbb-mono)', color: 'var(--lbb-fg)' }}>
                          F{f.index}
                        </div>
                        <div style={{ font: '500 10px var(--lbb-mono)', color: 'var(--lbb-fg3)' }}>
                          {f.note}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                        {f.members.map(lb => (
                          <Chip
                            key={lb} lb={lb}
                            kind={f.movedIn.includes(lb) ? 'moved' : 'plain'}
                          />
                        ))}
                        {f.gone.map(lb => <Chip key={`g${lb}`} lb={lb} kind="gone" />)}
                      </div>
                      <Pill
                        tone={f.verdict === 'held' ? 'mute' : f.verdict === 'merged' ? 'ok' : 'warn'}
                        soft
                      >{f.verdict}</Pill>
                    </div>
                  ))}
                </div>
                {(diff.addedLbs.length > 0 || diff.removedLbs.length > 0) && (
                  <p style={{ margin: '10px 0 0', fontSize: 11.5, lineHeight: 1.6, color: 'var(--lbb-warn-fg)' }}>
                    {diff.addedLbs.length > 0 && `Added since the base run: ${diff.addedLbs.map(short).join(', ')}. `}
                    {diff.removedLbs.length > 0 && `Not in the current run: ${diff.removedLbs.map(short).join(', ')} — kept visible, never silently dropped.`}
                  </p>
                )}
              </Section>

              <Section title="3. Similarity delta">
                <DeltaMatrix diff={diff} lbs={lbs} onOpenPair={onOpenPair} />
              </Section>

              <Section title="4. Pair changes">
                <table style={{
                  width: '100%', borderCollapse: 'collapse', fontSize: 11.5, marginTop: 10,
                }}>
                  <thead>
                    <tr>
                      {['Pair', 'Residual correlation', 'Windowed coverage', 'Call'].map(h => (
                        <th key={h} style={{
                          font: '700 9.5px var(--lbb-font)', textTransform: 'uppercase',
                          letterSpacing: '.07em', color: 'var(--lbb-fg3)', textAlign: 'left',
                          padding: '0 9px 6px 0', borderBottom: '1px solid var(--lbb-border)',
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {listedPairs.map(p => (
                      <tr
                        key={p.key}
                        onClick={() => onOpenPair(p.lbA, p.lbB)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td style={TD}>
                          <span style={{ fontFamily: 'var(--lbb-mono)', fontWeight: 600 }}>
                            {short(p.lbA)} × {short(p.lbB)}
                          </span>
                          {p.presence !== 'both' && (
                            <span style={{ marginLeft: 6 }}>
                              <Pill tone="warn" soft>
                                {p.presence === 'head-only' ? 'new pair' : 'gone'}
                              </Pill>
                            </span>
                          )}
                        </td>
                        <td style={TD}><DeltaValue from={p.corrBase} to={p.corrHead} /></td>
                        <td style={TD}><DeltaValue from={p.winBase} to={p.winHead} /></td>
                        <td style={TD}>
                          {p.flipped ? (
                            <span style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
                              <Pill tone={p.sameBase ? 'ok' : 'info'} soft>
                                {p.sameBase ? 'same' : 'different'}
                              </Pill>
                              <span style={{ color: 'var(--lbb-fg3)' }}>→</span>
                              <Pill tone={p.sameHead ? 'ok' : 'info'} soft>
                                {p.sameHead ? 'same' : 'different'}
                              </Pill>
                            </span>
                          ) : (
                            <span style={{ color: 'var(--lbb-fg3)' }}>
                              held · {p.sameHead ? 'same' : 'different'}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p style={{ margin: '10px 0 0', fontSize: 11.5, color: 'var(--lbb-fg3)' }}>
                  {diff.unchangedCount} pair{diff.unchangedCount === 1 ? '' : 's'} moved less than
                  0.01 and kept the same call.{' '}
                  {diff.unchangedCount > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowAllPairs(v => !v)}
                      style={{
                        background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
                        font: '600 11.5px inherit', color: 'var(--lbb-accent-mid)',
                      }}
                    >{showAllPairs ? 'Show only changes' : 'Show every pair'}</button>
                  )}
                </p>
              </Section>

              <Section title="5. Your judgments">
                <p style={{ margin: '10px 0 0', font: '400 12.5px/1.6 var(--lbb-font)', color: 'var(--lbb-fg2)' }}>
                  A judgment is a call about the tapes, not about a run — so it survives
                  re-analysis. What changes is whether the algorithm still disagrees with you.
                </p>
                {diff.judgments.length === 0 ? (
                  <div style={{
                    marginTop: 10, padding: '14px 12px', borderRadius: 6,
                    border: '1px dashed var(--lbb-border2)', fontSize: 11.5,
                    color: 'var(--lbb-fg3)', textAlign: 'center',
                  }}>
                    No judgments recorded for this date yet — nothing to reconcile.
                  </div>
                ) : (
                  <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {diff.judgments.map(j => {
                      const copy = IMPACT_COPY[j.kind]
                      return (
                        <div key={j.key} style={{
                          display: 'grid', gridTemplateColumns: '118px auto minmax(0,1fr)',
                          gap: 10, alignItems: 'center', padding: '8px 10px',
                          borderLeft: `3px solid var(--lbb-${copy.tone}-bar)`,
                          background: 'var(--lbb-surface2)', borderRadius: '0 6px 6px 0',
                        }}>
                          <button
                            type="button"
                            onClick={() => onOpenPair(j.lbA, j.lbB)}
                            style={{
                              background: 'transparent', border: 'none', padding: 0,
                              cursor: 'pointer', textAlign: 'left',
                              font: '600 11px var(--lbb-mono)', color: 'var(--lbb-accent-mid)',
                            }}
                          >{short(j.lbA)} × {short(j.lbB)}</button>
                          <Pill tone={JUDGMENT_TONE[j.judgment] ?? 'mute'} soft>
                            {JUDGMENT_LABEL[j.judgment] ?? j.judgment}
                          </Pill>
                          <span style={{ fontSize: 11.5, lineHeight: 1.5, color: 'var(--lbb-fg2)' }}>
                            {copy.text}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                )}
                <p style={{ margin: '12px 0 0', fontSize: 11, lineHeight: 1.6, color: 'var(--lbb-fg3)' }}>
                  Judgments are never rewritten or deleted by a re-run, and a judgment whose pair
                  disappears is kept and marked orphaned rather than dropped. Viewing this diff
                  changes neither run.
                </p>
              </Section>
            </>
          )}
        </>
      )}
    </SheetShell>
  )
}

const TD: React.CSSProperties = {
  padding: '7px 9px 7px 0', borderBottom: '1px solid var(--lbb-border)',
  color: 'var(--lbb-fg2)', verticalAlign: 'top',
}

function Chip({ lb, kind }: { lb: number; kind: 'plain' | 'moved' | 'gone' }) {
  const tone = kind === 'moved' ? 'ok' : kind === 'gone' ? 'bad' : null
  return (
    <span
      title={kind === 'gone' ? 'left this family in the current run'
        : kind === 'moved' ? 'moved in from another family' : undefined}
      style={{
        font: '600 11px var(--lbb-mono)', borderRadius: 4, padding: '1px 6px',
        background: tone ? `var(--lbb-${tone}-bg)` : 'var(--lbb-surface2)',
        border: `1px solid ${tone ? `var(--lbb-${tone}-bar)` : 'var(--lbb-border)'}`,
        color: tone ? `var(--lbb-${tone}-fg)` : 'var(--lbb-fg2)',
        textDecoration: kind === 'gone' ? 'line-through' : undefined,
      }}
    >
      {kind === 'moved' ? '+' : kind === 'gone' ? '−' : ''}{short(lb)}
    </span>
  )
}
