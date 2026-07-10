// Shared "why did this get its score" row list. Per instructions/
// SPEC_INTEGRATION_NOTES.md finding F3, evidence records share one common
// shape (`{kind, detail}` + optional extras) across the ranking, taper
// attribution, and (later) listening-insight specs — so there is exactly one
// EvidenceList component, built by whichever UI session ships first
// (FABLE_UNIFIED_RANKING phase 4) and reused by the others rather than each
// spec growing its own evidence renderer.
//
// Rendering follows FABLE_UNIFIED_RANKING.md §6's plain-row style: a detail
// sentence on the left, an optional signed point/score value on the right
// (e.g. "LB rating A− · +85", "carbonbit's picks · +8",
// "claimed superseded by LB-1234 · −6").

import React from 'react'

export interface EvidenceRecord {
  kind: string
  detail: string
  points?: number
  score?: number
  via_lb?: number
  fam_id?: string
  [extra: string]: unknown
}

export interface EvidenceListProps {
  evidence: EvidenceRecord[]
  emptyLabel?: string
}

function evidenceValue(e: EvidenceRecord): number | null {
  const v = e.points ?? e.score
  return typeof v === 'number' ? v : null
}

function valueTone(v: number | null): 'ok' | 'bad' | 'mute' {
  if (v == null || v === 0) return 'mute'
  return v > 0 ? 'ok' : 'bad'
}

function formatValue(v: number): string {
  const rounded = Math.round(v * 10) / 10
  const sign = rounded > 0 ? '+' : ''
  return `${sign}${rounded}`
}

export function EvidenceList({ evidence, emptyLabel }: EvidenceListProps) {
  if (evidence.length === 0) {
    if (!emptyLabel) return null
    return (
      <div style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg3)' }}>{emptyLabel}</div>
    )
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      {evidence.map((e, i) => {
        const value = evidenceValue(e)
        const tone = valueTone(value)
        // No --lbb-mute-fg variable exists in the theme; fg3 is the muted text color.
        const valueColor = tone === 'mute' ? 'var(--lbb-fg3)' : `var(--lbb-${tone}-fg)`
        return (
          <div
            key={`${e.kind}-${i}`}
            style={{
              display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10,
              padding: '6px 0',
              borderTop: i > 0 ? '1px solid var(--lbb-border)' : 'none',
            }}
          >
            <span style={{ fontSize: 'var(--t-meta)', color: 'var(--lbb-fg2)', minWidth: 0 }}>
              {e.detail}
            </span>
            {value != null && (
              <span style={{
                fontFamily: 'var(--lbb-mono)', fontSize: 'var(--t-mono-sm)', fontWeight: 'var(--w-semi)',
                color: valueColor, whiteSpace: 'nowrap', flexShrink: 0,
                fontVariantNumeric: 'tabular-nums',
              }}>
                {formatValue(value)}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}
