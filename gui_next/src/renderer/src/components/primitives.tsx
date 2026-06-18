// Primitive UI components. All theme-aware via CSS variables set by tokens.ts.
// Ported from _source/lbb-ui.jsx.

import React from 'react'
import { Icon } from './Icon'
import type { IconName } from './Icon'

export type StatusTone = 'ok' | 'warn' | 'bad' | 'info' | 'mute'
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ComponentSize = 'sm' | 'md' | 'lg'

// ── Pill ────────────────────────────────────────────────────────────────────

export interface PillProps {
  tone?: StatusTone
  soft?: boolean
  dot?: boolean
  children?: React.ReactNode
  style?: React.CSSProperties
}

export function Pill({ tone = 'mute', soft = false, dot = false, children, style }: PillProps) {
  const fg = `var(--lbb-${tone}-fg)`
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '1px 7px', borderRadius: 999,
      fontSize: 'var(--lbb-fs-10-5)', fontWeight: 600, letterSpacing: '0.02em',
      color: fg,
      background: soft ? `var(--lbb-${tone}-bg)` : 'transparent',
      border: `1px solid ${soft ? 'transparent' : fg}`,
      whiteSpace: 'nowrap', lineHeight: 1.45,
      ...style,
    }}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: '50%', background: fg }} />}
      {children}
    </span>
  )
}

// ── Chip ────────────────────────────────────────────────────────────────────

export interface ChipProps {
  active?: boolean
  onClick?: () => void
  children?: React.ReactNode
  count?: number
  icon?: IconName | string
  size?: 'sm' | 'md'
  style?: React.CSSProperties
}

export function Chip({ active = false, onClick, children, count, icon, size = 'md', style }: ChipProps) {
  const pad  = size === 'sm' ? '2px 8px' : '3px 10px'
  const font = size === 'sm' ? 11 : 11.5
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: pad, fontSize: font, fontFamily: 'inherit',
        borderRadius: 999, cursor: 'pointer',
        border: `1px solid ${active ? 'var(--lbb-accent-mid)' : 'var(--lbb-border2)'}`,
        background: active ? 'var(--lbb-accent-soft)' : 'var(--lbb-surface)',
        color: active ? 'var(--lbb-accent-mid)' : 'var(--lbb-fg2)',
        fontWeight: active ? 600 : 500, lineHeight: 1.5,
        ...style,
      }}
    >
      {icon && <Icon name={icon} size={12} />}
      {children}
      {count !== undefined && (
        <span style={{ fontSize: 'var(--lbb-fs-10)', opacity: 0.6, fontWeight: 500 }}>{count.toLocaleString()}</span>
      )}
    </button>
  )
}

// ── Button ──────────────────────────────────────────────────────────────────

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ComponentSize
  icon?: IconName | string
  iconRight?: IconName | string
  block?: boolean
}

const BTN_HEIGHTS: Record<ComponentSize, number> = { sm: 24, md: 30, lg: 36 }
const BTN_PADX:   Record<ComponentSize, number> = { sm: 8, md: 12, lg: 14 }
const BTN_FONTS:  Record<ComponentSize, number> = { sm: 11.5, md: 12.5, lg: 13.5 }

const BTN_COLORS: Record<ButtonVariant, { bg: string; fg: string; border: string; hover: string }> = {
  primary:   { bg: 'var(--lbb-accent-mid)',  fg: 'var(--lbb-accent-onMid)', border: 'var(--lbb-accent-mid)', hover: 'var(--lbb-accent-hi)' },
  secondary: { bg: 'var(--lbb-surface)',     fg: 'var(--lbb-fg)',           border: 'var(--lbb-border2)',    hover: 'var(--lbb-surface2)'  },
  ghost:     { bg: 'transparent',            fg: 'var(--lbb-fg2)',          border: 'transparent',           hover: 'var(--lbb-surface2)'  },
  danger:    { bg: 'var(--lbb-surface)',     fg: 'var(--lbb-bad-fg)',       border: 'var(--lbb-bad-fg)',     hover: 'var(--lbb-bad-bg)'    },
}

export function Button({
  variant = 'secondary', size = 'md', icon, iconRight, block,
  children, disabled, style, onClick, ...rest
}: ButtonProps) {
  const c = BTN_COLORS[variant]
  const iconSize = size === 'sm' ? 12 : 14
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
        height: BTN_HEIGHTS[size], padding: `0 ${BTN_PADX[size]}px`,
        fontSize: BTN_FONTS[size], fontWeight: 600, fontFamily: 'inherit',
        borderRadius: 6, cursor: disabled ? 'not-allowed' : 'pointer',
        background: c.bg, color: c.fg,
        border: `1px solid ${c.border}`,
        opacity: disabled ? 0.5 : 1,
        boxShadow: variant === 'primary' ? '0 1px 0 rgba(0,0,0,0.05)' : 'none',
        whiteSpace: 'nowrap', width: block ? '100%' : 'auto',
        transition: 'background 120ms ease, border-color 120ms ease',
        ...style,
      }}
      onMouseEnter={e => { if (!disabled) e.currentTarget.style.background = c.hover }}
      onMouseLeave={e => { if (!disabled) e.currentTarget.style.background = c.bg }}
      {...rest}
    >
      {icon      && <Icon name={icon}      size={iconSize} />}
      {children}
      {iconRight && <Icon name={iconRight} size={iconSize} />}
    </button>
  )
}

// ── IconButton ───────────────────────────────────────────────────────────────

export interface IconButtonProps {
  icon: IconName | string
  size?: number
  onClick?: React.MouseEventHandler<HTMLButtonElement>
  title?: string
  active?: boolean
  style?: React.CSSProperties
}

export function IconButton({ icon, size = 28, onClick, title, active, style }: IconButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      style={{
        width: size, height: size, padding: 0,
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
        background: active ? 'var(--lbb-surface2)' : 'transparent',
        color: active ? 'var(--lbb-fg)' : 'var(--lbb-fg2)',
        border: '1px solid transparent',
        transition: 'background 120ms ease',
        ...style,
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--lbb-surface2)' }}
      onMouseLeave={e => { e.currentTarget.style.background = active ? 'var(--lbb-surface2)' : 'transparent' }}
    >
      <Icon name={icon} size={Math.round(size * 0.55)} />
    </button>
  )
}

// ── Input ────────────────────────────────────────────────────────────────────

export interface InputProps {
  icon?: IconName | string
  placeholder?: string
  value?: string
  onChange?: React.ChangeEventHandler<HTMLInputElement>
  size?: ComponentSize
  width?: number | string
  style?: React.CSSProperties
}

const INPUT_HEIGHTS: Record<ComponentSize, number> = { sm: 24, md: 30, lg: 36 }
const INPUT_FONTS:  Record<ComponentSize, number> = { sm: 11.5, md: 12.5, lg: 13.5 }

export function Input({ icon, placeholder, value, onChange, size = 'md', width, style }: InputProps) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      height: INPUT_HEIGHTS[size], padding: '0 10px',
      background: 'var(--lbb-surface)', borderRadius: 6,
      border: '1px solid var(--lbb-border2)',
      width: width ?? 'auto',
      ...style,
    }}>
      {icon && <Icon name={icon} size={13} style={{ color: 'var(--lbb-fg3)' }} />}
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        style={{
          flex: 1, height: '100%', border: 'none', outline: 'none',
          background: 'transparent', color: 'var(--lbb-fg)',
          fontSize: INPUT_FONTS[size], fontFamily: 'inherit', minWidth: 0,
        }}
      />
    </div>
  )
}

// ── Kbd ──────────────────────────────────────────────────────────────────────

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      minWidth: 18, height: 18, padding: '0 4px',
      fontSize: 'var(--lbb-fs-10-5)', fontFamily: 'var(--lbb-mono)', fontWeight: 500,
      background: 'var(--lbb-surface2)', color: 'var(--lbb-fg2)',
      border: '1px solid var(--lbb-border)',
      borderRadius: 3, lineHeight: 1,
    }}>{children}</kbd>
  )
}

// ── Card ─────────────────────────────────────────────────────────────────────

export interface CardProps {
  title?: string
  subtitle?: string
  action?: React.ReactNode
  pad?: number
  style?: React.CSSProperties
  children?: React.ReactNode
}

export function Card({ title, subtitle, action, children, pad = 16, style }: CardProps) {
  return (
    <div style={{
      background: 'var(--lbb-surface)',
      border: '1px solid var(--lbb-border)',
      borderRadius: 8, overflow: 'hidden',
      boxShadow: 'var(--lbb-shadow)',
      ...style,
    }}>
      {(title || action) && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: `${pad - 4}px ${pad}px`,
          borderBottom: '1px solid var(--lbb-border)',
        }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            {title    && <div style={{ fontSize: 'var(--lbb-fs-12-5)', fontWeight: 600, letterSpacing: 0.01 }}>{title}</div>}
            {subtitle && <div style={{ fontSize: 'var(--lbb-fs-11)', color: 'var(--lbb-fg3)', marginTop: 2 }}>{subtitle}</div>}
          </div>
          {action}
        </div>
      )}
      <div style={{ padding: pad }}>{children}</div>
    </div>
  )
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

export interface ToolbarProps {
  children?: React.ReactNode
  bordered?: boolean
  pad?: string
  style?: React.CSSProperties
}

export function Toolbar({ children, bordered = true, pad = '10px 14px', style }: ToolbarProps) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: pad,
      borderBottom: bordered ? '1px solid var(--lbb-border)' : 'none',
      flexWrap: 'wrap',
      ...style,
    }}>{children}</div>
  )
}

// ── Banner ───────────────────────────────────────────────────────────────────

export interface BannerProps {
  tone?: StatusTone
  icon?: IconName | string
  title?: string
  action?: React.ReactNode
  children?: React.ReactNode
  style?: React.CSSProperties
}

export function Banner({ tone = 'info', icon = 'info', title, children, action, style }: BannerProps) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 10,
      padding: '10px 12px', borderRadius: 6,
      background: `var(--lbb-${tone}-bg)`, color: `var(--lbb-${tone}-fg)`,
      border: `1px solid var(--lbb-${tone}-bar)`,
      fontSize: 'var(--lbb-fs-12)',
      ...style,
    }}>
      <Icon name={icon} size={14} style={{ marginTop: 2, flex: '0 0 auto' }} />
      <div style={{ flex: 1 }}>
        {title && <div style={{ fontWeight: 600, marginBottom: 2, color: `var(--lbb-${tone}-fg)` }}>{title}</div>}
        <div style={{ color: 'var(--lbb-fg2)' }}>{children}</div>
      </div>
      {action}
    </div>
  )
}

// ── Stat ─────────────────────────────────────────────────────────────────────

export interface StatProps {
  value: React.ReactNode
  label?: string
  delta?: string
  tone?: StatusTone
}

export function Stat({ value, label, delta, tone = 'ok' }: StatProps) {
  return (
    <div>
      <div style={{
        fontSize: 'var(--lbb-fs-22)', fontWeight: 700,
        fontVariantNumeric: 'tabular-nums',
        fontFamily: 'var(--lbb-mono)',
        letterSpacing: '-0.01em',
      }}>{value}</div>
      <div style={{ fontSize: 'var(--lbb-fs-11-5)', color: 'var(--lbb-fg3)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 6 }}>
        {label}
        {delta && <Pill tone={tone} soft style={{ fontSize: 'var(--lbb-fs-9-5)', padding: '0 5px' }}>{delta}</Pill>}
      </div>
    </div>
  )
}

// ── SectionHead ───────────────────────────────────────────────────────────────

export interface SectionHeadProps {
  title: string
  subtitle?: string
  action?: React.ReactNode
  style?: React.CSSProperties
}

export function SectionHead({ title, subtitle, action, style }: SectionHeadProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 12, ...style }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h3 style={{
          margin: 0, fontSize: 'var(--lbb-fs-13)', fontWeight: 700,
          letterSpacing: '0.04em', textTransform: 'uppercase',
          color: 'var(--lbb-fg2)',
        }}>{title}</h3>
        {subtitle && <div style={{ marginTop: 4, fontSize: 'var(--lbb-fs-12)', color: 'var(--lbb-fg3)' }}>{subtitle}</div>}
      </div>
      {action}
    </div>
  )
}

// ── Toast ───────────────────────────────────────────────────────────────────
// Ported from ScreenCollection.tsx's local Toast — shared so other screens
// (e.g. the Library action system) don't reimplement the same fixed-position
// notice.

export type ToastTone = 'ok' | 'bad' | 'info'

export interface ToastProps {
  msg: string
  tone: ToastTone
  onDone: () => void
}

export function Toast({ msg, tone, onDone }: ToastProps) {
  React.useEffect(() => {
    const t = setTimeout(onDone, 3500)
    return () => clearTimeout(t)
  }, [onDone])

  const bg     = tone === 'ok'  ? 'var(--lbb-ok-bg)'   : tone === 'bad' ? 'var(--lbb-err-bg)'  : 'var(--lbb-surface2)'
  const border = tone === 'ok'  ? 'var(--lbb-ok-bar)'  : tone === 'bad' ? 'var(--lbb-err-bar)' : 'var(--lbb-border2)'
  const color  = tone === 'ok'  ? 'var(--lbb-ok-fg)'   : tone === 'bad' ? 'var(--lbb-err-fg)'  : 'var(--lbb-fg)'

  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 999,
      background: bg, border: `1px solid ${border}`, borderRadius: 8,
      padding: '10px 16px', color, fontSize: 'var(--lbb-fs-13)', fontWeight: 500,
      boxShadow: '0 4px 16px rgba(0,0,0,0.15)', maxWidth: 400,
    }}>
      {msg}
    </div>
  )
}

// ── ConfirmDialog ─────────────────────────────────────────────────────────────
// Ported from ScreenCollection.tsx's local ConfirmDialog.

export interface ConfirmDialogProps {
  title: string
  body: string
  onConfirm: () => void
  onCancel: () => void
  confirmLabel?: string
  cancelLabel?: string
}

export function ConfirmDialog({ title, body, onConfirm, onCancel, confirmLabel = 'Confirm', cancelLabel = 'Cancel' }: ConfirmDialogProps) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border)',
        borderRadius: 10, padding: 24, maxWidth: 440, width: '90%',
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <div style={{ fontSize: 'var(--lbb-fs-14)', fontWeight: 700, color: 'var(--lbb-fg)', marginBottom: 8 }}>{title}</div>
        <div style={{ fontSize: 'var(--lbb-fs-12-5)', color: 'var(--lbb-fg2)', marginBottom: 20, lineHeight: 1.5 }}>{body}</div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <Button variant="ghost" size="sm" onClick={onCancel}>{cancelLabel}</Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  )
}
