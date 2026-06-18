// Table primitive family. Every screen depends on these.
// The edge-bar convention: TR always injects a 3px leading <td> as a color bar.
// Colgroups MUST include a leading <col style={{ width: 3 }} /> for alignment.

import React from 'react'
import { Icon } from './Icon'
import type { StatusTone } from './primitives'
import { useSettingsStore } from '../store'

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
  onClick?: React.MouseEventHandler<HTMLTableCellElement>
  sorted?: 'asc' | 'desc' | null
  onResizeStart?: (e: React.MouseEvent) => void
}

export function TH({ children, align = 'left', width, style, onClick, sorted, onResizeStart }: THProps) {
  return (
    <th
      onClick={onClick}
      style={{
        textAlign: align,
        padding: '8px var(--lbb-d-pad)',
        fontWeight: 600, fontSize: 'var(--lbb-fs-10-5)',
        letterSpacing: '0.04em', textTransform: 'uppercase',
        color: sorted ? 'var(--lbb-fg2)' : 'var(--lbb-fg3)',
        background: 'var(--lbb-surface2)',
        borderBottom: '1px solid var(--lbb-border2)',
        whiteSpace: 'nowrap',
        cursor: onClick ? 'pointer' : 'default',
        userSelect: onClick ? 'none' : undefined,
        position: 'relative',
        width,
        ...style,
      }}
    >
      {children}
      {sorted === 'asc'  && <span style={{ marginLeft: 4, opacity: 0.7 }}>▲</span>}
      {sorted === 'desc' && <span style={{ marginLeft: 4, opacity: 0.7 }}>▼</span>}
      {!sorted && onClick && <span style={{ marginLeft: 4, opacity: 0.25 }}>⇅</span>}
      {onResizeStart && (
        <div
          onMouseDown={e => { e.stopPropagation(); e.preventDefault(); onResizeStart(e) }}
          onClick={e => e.stopPropagation()}
          style={{
            position: 'absolute', right: 0, top: 0, bottom: 0, width: 6,
            cursor: 'col-resize', zIndex: 1,
            borderRight: '2px solid transparent',
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.borderRightColor = 'var(--lbb-border2)' }}
          onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.borderRightColor = 'transparent' }}
        />
      )}
    </th>
  )
}

// ── TR ───────────────────────────────────────────────────────────────────────
// Renders the 3px edge-bar <td> automatically before children.

export interface TRProps {
  edge?: StatusTone
  selected?: boolean
  onClick?: React.MouseEventHandler<HTMLTableRowElement>
  onDoubleClick?: React.MouseEventHandler<HTMLTableRowElement>
  onContextMenu?: React.MouseEventHandler<HTMLTableRowElement>
  style?: React.CSSProperties
  children?: React.ReactNode
}

export const TR = React.forwardRef<HTMLTableRowElement, TRProps>(
  function TR({ edge, selected, onClick, onDoubleClick, onContextMenu, style, children }, ref) {
    const rowHighlight = useSettingsStore((s) => s.rowHighlight)
    const wash = (edge && rowHighlight) ? `var(--lbb-${edge}-bg)` : 'transparent'
    const bar  = (edge && rowHighlight) ? `var(--lbb-${edge}-bar)` : 'transparent'
    return (
      <tr
        ref={ref}
        onClick={onClick}
        onDoubleClick={onDoubleClick}
        onContextMenu={onContextMenu}
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
)

// ── TD ───────────────────────────────────────────────────────────────────────

export interface TDProps {
  children?: React.ReactNode
  mono?: boolean
  dim?: boolean
  align?: 'left' | 'center' | 'right'
  colSpan?: number
  style?: React.CSSProperties
  onClick?: React.MouseEventHandler<HTMLTableCellElement>
}

export function TD({ children, mono = false, dim = false, align = 'left', colSpan, style, onClick }: TDProps) {
  return (
    <td
      colSpan={colSpan}
      onClick={onClick}
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
  style?: React.CSSProperties
}

export const GroupRow = React.forwardRef<HTMLTableRowElement, GroupRowProps>(
  function GroupRow({ label, count, expanded = true, onToggle, colSpan = 99, style }, ref) {
    return (
      <tr ref={ref} style={style}>
        <td style={{ width: 3, padding: 0, background: 'transparent' }} />
        <td
          colSpan={colSpan}
          onClick={onToggle}
          style={{
            padding: '5px var(--lbb-d-pad)',
            background: 'var(--lbb-surface2)',
            fontSize: 'var(--lbb-fs-11)', fontWeight: 600, letterSpacing: '0.04em',
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
            <span style={{ marginLeft: 8, fontSize: 'var(--lbb-fs-10-5)', color: 'var(--lbb-fg3)', fontWeight: 500 }}>
              {count.toLocaleString()}
            </span>
          )}
        </td>
      </tr>
    )
  }
)
