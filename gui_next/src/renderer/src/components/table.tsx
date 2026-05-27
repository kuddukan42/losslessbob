// Table primitive family. Every screen depends on these.
// The edge-bar convention: TR always injects a 3px leading <td> as a color bar.
// Colgroups MUST include a leading <col style={{ width: 3 }} /> for alignment.

import React from 'react'
import { Icon } from './Icon'
import type { StatusTone } from './primitives'

// ── TableShell ───────────────────────────────────────────────────────────────

export interface TableShellProps {
  stickyHeader?: boolean
  style?: React.CSSProperties
  children?: React.ReactNode
}

export function TableShell({ stickyHeader = true, style, children }: TableShellProps) {
  return (
    <table
      className={stickyHeader ? 'lbb-sticky' : undefined}
      style={{
        width: '100%',
        borderCollapse: 'separate',
        borderSpacing: 0,
        fontSize: 'var(--lbb-d-font)',
        lineHeight: 1.4,
        tableLayout: 'fixed',
        ...style,
      }}
    >
      {children}
    </table>
  )
}

// ── TH ───────────────────────────────────────────────────────────────────────

export interface THProps {
  children?: React.ReactNode
  align?: 'left' | 'center' | 'right'
  width?: number | string
  style?: React.CSSProperties
}

export function TH({ children, align = 'left', width, style }: THProps) {
  return (
    <th style={{
      textAlign: align,
      padding: '8px var(--lbb-d-pad)',
      fontWeight: 600, fontSize: 10.5,
      letterSpacing: '0.04em', textTransform: 'uppercase',
      color: 'var(--lbb-fg3)',
      background: 'var(--lbb-surface2)',
      borderBottom: '1px solid var(--lbb-border2)',
      whiteSpace: 'nowrap',
      width,
      ...style,
    }}>{children}</th>
  )
}

// ── TR ───────────────────────────────────────────────────────────────────────
// Renders the 3px edge-bar <td> automatically before children.

export interface TRProps {
  edge?: StatusTone
  selected?: boolean
  onClick?: React.MouseEventHandler<HTMLTableRowElement>
  style?: React.CSSProperties
  children?: React.ReactNode
}

export function TR({ edge, selected, onClick, style, children }: TRProps) {
  const wash = edge ? `var(--lbb-${edge}-bg)` : 'transparent'
  const bar  = edge ? `var(--lbb-${edge}-bar)` : 'transparent'
  return (
    <tr
      onClick={onClick}
      data-selected={selected ? 'true' : undefined}
      style={{
        background: selected ? 'var(--lbb-accent-soft)' : wash,
        cursor: onClick ? 'pointer' : 'default',
        ...style,
      }}
    >
      <td style={{
        width: 3, padding: 0,
        background: bar,
        borderBottom: '1px solid var(--lbb-border)',
      }} />
      {children}
    </tr>
  )
}

// ── TD ───────────────────────────────────────────────────────────────────────

export interface TDProps {
  children?: React.ReactNode
  mono?: boolean
  dim?: boolean
  align?: 'left' | 'center' | 'right'
  colSpan?: number
  style?: React.CSSProperties
}

export function TD({ children, mono = false, dim = false, align = 'left', colSpan, style }: TDProps) {
  return (
    <td
      colSpan={colSpan}
      style={{
        textAlign: align,
        padding: 'calc(var(--lbb-d-pad) - 2px) var(--lbb-d-pad)',
        borderBottom: '1px solid var(--lbb-border)',
        color: dim ? 'var(--lbb-fg3)' : 'var(--lbb-fg2)',
        fontFamily: mono ? 'var(--lbb-mono)' : 'inherit',
        fontSize: mono ? 'calc(var(--lbb-d-font) - 0.5px)' : 'var(--lbb-d-font)',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        verticalAlign: 'middle',
        ...style,
      }}
    >
      {children}
    </td>
  )
}

// ── GroupRow ─────────────────────────────────────────────────────────────────
// Section divider row inside a tbody. Spans the full table width.
// colSpan should equal (number of data columns) — the edge bar column is separate.

export interface GroupRowProps {
  label: string
  count?: number
  expanded?: boolean
  onToggle?: () => void
  colSpan?: number
}

export function GroupRow({ label, count, expanded = true, onToggle, colSpan = 99 }: GroupRowProps) {
  return (
    <tr>
      <td style={{ width: 3, padding: 0, background: 'transparent' }} />
      <td
        colSpan={colSpan}
        onClick={onToggle}
        style={{
          padding: '5px var(--lbb-d-pad)',
          background: 'var(--lbb-surface2)',
          fontSize: 11, fontWeight: 600, letterSpacing: '0.04em',
          textTransform: 'uppercase',
          color: 'var(--lbb-fg2)',
          cursor: onToggle ? 'pointer' : 'default',
          borderBottom: '1px solid var(--lbb-border)',
          borderTop: '1px solid var(--lbb-border)',
          userSelect: 'none',
        }}
      >
        <Icon name={expanded ? 'chevDown' : 'chevRight'} size={11} style={{ marginRight: 4 }} />
        {label}
        {count !== undefined && (
          <span style={{ marginLeft: 8, fontSize: 10.5, color: 'var(--lbb-fg3)', fontWeight: 500 }}>
            {count.toLocaleString()}
          </span>
        )}
      </td>
    </tr>
  )
}
