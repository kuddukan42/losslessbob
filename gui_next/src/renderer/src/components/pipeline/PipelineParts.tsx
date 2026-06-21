import React from 'react'
import { Icon } from '../Icon'
import { Pill } from '../primitives'
import type { IconName } from '../Icon'
import { PipelineIcon } from './PipelineIcon'
import type { PipelineStage, PipelineStatus } from './PipelineIcon'

// ── State vocabulary ───────────────────────────────────────────────────────────

export type StepState = 'pass' | 'blocked' | 'action' | 'running' | 'pending' | 'mute'
export type Tone = 'ok' | 'bad' | 'warn' | 'info' | 'mute'
export type Bucket = 'needs' | 'ready' | 'running' | 'shelf' | 'done' | 'all'

interface StateDef { tone: Tone; label: string }

const STATE: Record<StepState, StateDef> = {
  pass:    { tone: 'ok',   label: 'Pass'    },
  blocked: { tone: 'bad',  label: 'Blocked' },
  action:  { tone: 'warn', label: 'Action'  },
  running: { tone: 'info', label: 'Running' },
  pending: { tone: 'mute', label: 'Pending' },
  mute:    { tone: 'mute', label: '—'       },
}

interface BucketDef { tone: Tone; label: string }

const BUCKET: Record<Bucket, BucketDef> = {
  needs:   { tone: 'warn', label: 'Needs you' },
  ready:   { tone: 'ok',   label: 'Ready'     },
  running: { tone: 'info', label: 'Running'   },
  shelf:   { tone: 'mute', label: 'Shelf'     },
  done:    { tone: 'ok',   label: 'Done'      },
  all:     { tone: 'mute', label: 'All'       },
}

// ── Stage descriptor ───────────────────────────────────────────────────────────

export interface StageDesc {
  key: string
  label: string
  n: number
}

export const DEFAULT_STAGES: StageDesc[] = [
  { key: 'verify', label: 'Verify',  n: 1 },
  { key: 'lookup', label: 'Lookup',  n: 2 },
  { key: 'lbdir',  label: 'LBDIR',   n: 3 },
  { key: 'rename', label: 'Rename',  n: 4 },
  { key: 'file',   label: 'Collect', n: 5 },
]

// ── Step data shape used by tracker components ─────────────────────────────────

export interface StepData { state: StepState; label?: string }
export interface FolderRow {
  folder: string
  folderName?: string
  steps: Record<string, StepData>
  bucket?: Bucket
  lb?: string | null
  progress?: { done: number; total: number } | null
}

// ── StateGlyph ────────────────────────────────────────────────────────────────

interface StateGlyphProps { state: StepState; size?: number }

export function StateGlyph({ state, size = 12 }: StateGlyphProps) {
  const tone = STATE[state].tone
  const col = `var(--lbb-${tone}-fg)`
  if (state === 'pass')
    return <Icon name="check" size={size} style={{ color: col }} />
  if (state === 'blocked')
    return <Icon name="x" size={size} style={{ color: col }} />
  if (state === 'action')
    return (
      <span style={{ fontWeight: 800, fontSize: size, color: col, lineHeight: 1,
        fontFamily: 'var(--lbb-mono)' }}>!</span>
    )
  if (state === 'running')
    return (
      <span className="p2-spin" style={{
        width: size, height: size, borderRadius: '50%',
        border: `2px solid color-mix(in oklab, ${col} 30%, transparent)`,
        borderTopColor: col, display: 'inline-block',
      }} />
    )
  return (
    <span style={{ width: size - 4, height: size - 4, borderRadius: '50%',
      border: '1.5px solid var(--lbb-fg3)' }} />
  )
}

// ── StatusTag ─────────────────────────────────────────────────────────────────

interface StatusTagProps {
  state: StepState
  children?: React.ReactNode
  soft?: boolean
  style?: React.CSSProperties
}

export function StatusTag({ state, children, soft = true, style }: StatusTagProps) {
  const s = STATE[state]
  return (
    <Pill tone={s.tone} soft={soft} style={{ gap: 5, ...style }}>
      <span style={{ display: 'inline-flex', width: 12, justifyContent: 'center' }}>
        <StateGlyph state={state} size={11} />
      </span>
      {children ?? s.label}
    </Pill>
  )
}

// ── StageNode ─────────────────────────────────────────────────────────────────

// Map the pipeline's stage keys/states onto the PipelineIcon vocabulary. The
// tracker uses 'file' for the Collect stage and a 'mute' (not-applicable) state;
// the tiles only know 'collect' and treat the absence of progress as 'pending'.
const STAGE_TO_TILE: Record<string, PipelineStage> = {
  verify: 'verify', lookup: 'lookup', lbdir: 'lbdir', rename: 'rename',
  file: 'collect', collect: 'collect',
}
const STATE_TO_TILE: Record<StepState, PipelineStatus> = {
  pass: 'pass', blocked: 'blocked', action: 'action',
  running: 'running', pending: 'pending', mute: 'pending',
}

interface StageNodeProps {
  stage: StageDesc
  state: StepState
  current: boolean
  /** Retained for API compatibility; tiles render the glyph, not the number. */
  n?: number
  size?: number
}

export function StageNode({ stage, state, current, size = 24 }: StageNodeProps) {
  const tileStage = STAGE_TO_TILE[stage.key] ?? 'verify'
  const tileStatus = STATE_TO_TILE[state]
  return (
    <span
      title={`${stage.label}: ${STATE[state].label}`}
      style={{
        position: 'relative', display: 'inline-flex', flex: `0 0 ${size}px`,
        borderRadius: size * 0.30, zIndex: 1,
        boxShadow: current ? '0 0 0 3px var(--lbb-accent-soft)' : 'none',
      }}
    >
      <PipelineIcon stage={tileStage} status={tileStatus} size={size} />
    </span>
  )
}

// ── StageTracker ──────────────────────────────────────────────────────────────

interface StageTrackerProps {
  folder: FolderRow
  stages?: StageDesc[]
  currentKey?: string | null
  onPick?: (key: string) => void
  /** Tile px (default 30). Glyph + Pulse animation scale with this. */
  size?: number
}

export function StageTracker({
  folder, stages = DEFAULT_STAGES, currentKey, onPick, size = 30,
}: StageTrackerProps) {
  // Fixed-width connectors keep the group compact and left-aligned (rather than
  // stretching edge-to-edge), and the generous padding gives the running Pulse
  // rings — which expand ~22px past each tile — room to breathe on all sides
  // without being clipped by the column edges.
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'flex-start',
      padding: '14px 36px',
    }}>
      {stages.map((st, i) => {
        const stepData = folder.steps[st.key] ?? { state: 'mute' as StepState }
        const state = stepData.state
        const next = stages[i + 1]
        return (
          <React.Fragment key={st.key}>
            <button
              type="button"
              onClick={onPick ? (e) => { e.stopPropagation(); onPick(st.key) } : undefined}
              style={{ background: 'none', border: 'none', padding: 0,
                cursor: onPick ? 'pointer' : 'default',
                display: 'inline-flex', alignItems: 'center' }}
            >
              <StageNode stage={st} state={state} current={currentKey === st.key} n={st.n} size={size} />
            </button>
            {next && (
              <span style={{
                flex: '0 0 18px', height: 2, margin: '0 4px',
                background: state === 'pass' ? 'var(--lbb-ok-bar)' : 'var(--lbb-border2)',
                borderRadius: 2,
              }} />
            )}
          </React.Fragment>
        )
      })}
    </div>
  )
}

// ── StageStepper ──────────────────────────────────────────────────────────────

interface StageStepperProps {
  folder: FolderRow
  stages?: StageDesc[]
  activeKey?: string | null
  onPick: (key: string) => void
}

export function StageStepper({
  folder, stages = DEFAULT_STAGES, activeKey, onPick,
}: StageStepperProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'stretch', width: '100%' }}>
      {stages.map((st, i) => {
        const stepData = folder.steps[st.key] ?? { state: 'mute' as StepState }
        const state = stepData.state
        const active = activeKey === st.key
        const next = stages[i + 1]
        const s = STATE[state]
        return (
          <React.Fragment key={st.key}>
            <button type="button" data-testid={`stage-tab-${st.key}`} onClick={() => onPick(st.key)} style={{
              flex: '0 0 auto', display: 'flex', alignItems: 'center', gap: 10,
              padding: '8px 12px', borderRadius: 8, cursor: 'pointer',
              background: active ? 'var(--lbb-accent-soft)' : 'transparent',
              border: `1px solid ${active ? 'var(--lbb-accent-mid)' : 'transparent'}`,
              fontFamily: 'inherit', textAlign: 'left',
            }}>
              <StageNode stage={st} state={state} current={active} n={st.n} />
              <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                <span style={{ fontSize: 13, fontWeight: 700,
                  color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)',
                  letterSpacing: -0.01 }}>{st.label}</span>
                <span style={{ fontSize: 10.5, fontWeight: 600,
                  color: `var(--lbb-${s.tone}-fg)`, letterSpacing: 0.02 }}>{s.label}</span>
              </span>
            </button>
            {next && (
              <span style={{ flex: 1, minWidth: 24, alignSelf: 'center', height: 2,
                background: state === 'pass' ? 'var(--lbb-ok-bar)' : 'var(--lbb-border2)',
                borderRadius: 2 }} />
            )}
          </React.Fragment>
        )
      })}
    </div>
  )
}

// ── QueueRow ──────────────────────────────────────────────────────────────────

interface QueueRowProps {
  folder: FolderRow
  active: boolean
  onClick: () => void
}

export function QueueRow({ folder, active, onClick }: QueueRowProps) {
  const bucket = folder.bucket ?? 'needs'
  const b = BUCKET[bucket]
  const name = folder.folderName ?? folder.folder.split('/').pop() ?? folder.folder
  const hasBlocked = Object.values(folder.steps).some(s => s.state === 'blocked')
  const tone = hasBlocked ? 'bad' : b.tone
  const statusLabel = hasBlocked ? 'Blocked' : b.label
  return (
    <button
      onClick={onClick}
      style={{
        width: '100%', display: 'flex', alignItems: 'center', gap: 9,
        padding: '8px 10px', marginBottom: 2, borderRadius: 7,
        background: active ? 'var(--lbb-accent-soft)' : 'transparent',
        color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
        border: `1px solid ${active ? 'var(--lbb-accent-mid)' : 'transparent'}`,
        textAlign: 'left', fontFamily: 'inherit', cursor: 'pointer',
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--lbb-surface2)' }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
    >
      <span style={{ width: 8, height: 8, borderRadius: 2,
        background: `var(--lbb-${tone}-bar)`, flex: '0 0 8px' }} />
      <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 11,
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg)' }}>{name}</span>
        <span style={{ fontSize: 10, color: `var(--lbb-${tone}-fg)`,
          fontWeight: 600, letterSpacing: 0.02 }}>
          {bucket === 'running' && folder.progress
            ? `Verifying ${folder.progress.done}/${folder.progress.total}…`
            : folder.lb ? `${statusLabel} · ${folder.lb}` : statusLabel}
        </span>
      </span>
    </button>
  )
}

export { STATE, BUCKET }
