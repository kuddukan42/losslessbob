import React from 'react'
import { Icon } from '../Icon'
import { Button } from '../primitives'
import type { IconName } from '../Icon'
import type { ButtonVariant } from '../primitives'

// ── Types ─────────────────────────────────────────────────────────────────────

export type ConfirmTone = 'danger' | 'warn' | 'info'

export interface ConfirmItem { label: string; icon?: IconName; meta?: string }

export interface ConfirmOpts {
  tone?: ConfirmTone
  title: string
  body?: string
  note?: string
  items?: ConfirmItem[]
  icon?: IconName
  confirmLabel?: string
  cancelLabel?: string
  confirmIcon?: IconName
  confirmVariant?: ButtonVariant
}

interface ToneDef { accent: string; icon: IconName; confirmVariant: ButtonVariant }

const TONE: Record<ConfirmTone, ToneDef> = {
  danger: { accent: 'bad',  icon: 'trash',  confirmVariant: 'danger'  },
  warn:   { accent: 'warn', icon: 'folder', confirmVariant: 'primary' },
  info:   { accent: 'info', icon: 'info',   confirmVariant: 'primary' },
}

// ── ConfirmDialog ─────────────────────────────────────────────────────────────

interface ConfirmDialogProps {
  open: boolean
  opts: ConfirmOpts | null
  onResolve: (v: boolean) => void
}

export function ConfirmDialog({ open, opts, onResolve }: ConfirmDialogProps) {
  const cardRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    if (!open) return
    const t = setTimeout(() => {
      const btn = cardRef.current?.querySelector<HTMLButtonElement>('[data-confirm-btn]')
      btn?.focus()
    }, 30)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onResolve(false) }
      if (e.key === 'Enter')  { e.preventDefault(); onResolve(true) }
    }
    window.addEventListener('keydown', onKey, true)
    return () => { clearTimeout(t); window.removeEventListener('keydown', onKey, true) }
  }, [open, onResolve])

  if (!open || !opts) return null

  const tone = TONE[opts.tone ?? 'danger']
  const accent = tone.accent

  return (
    <div
      onMouseDown={(e) => { if (e.target === e.currentTarget) onResolve(false) }}
      style={{
        position: 'fixed', inset: 0, zIndex: 200,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'color-mix(in oklab, var(--lbb-fg) 38%, transparent)',
        backdropFilter: 'blur(1.5px)',
      }}
    >
      <div
        ref={cardRef}
        role="alertdialog"
        aria-modal="true"
        style={{
          width: 432, maxWidth: 'calc(100% - 48px)',
          background: 'var(--lbb-bg)', borderRadius: 12,
          border: '1px solid var(--lbb-border)',
          boxShadow: '0 24px 60px rgba(0,0,0,0.35)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', gap: 14, padding: '18px 20px 14px' }}>
          <div style={{
            width: 38, height: 38, borderRadius: 10, flex: '0 0 38px',
            background: `var(--lbb-${accent}-bg)`, color: `var(--lbb-${accent}-fg)`,
            border: `1px solid var(--lbb-${accent}-bar)`,
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon name={opts.icon ?? tone.icon} size={19} />
          </div>
          <div style={{ flex: 1, minWidth: 0, paddingTop: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: -0.01,
              color: 'var(--lbb-fg)' }}>{opts.title}</div>
            {opts.body && (
              <div style={{ fontSize: 12.5, color: 'var(--lbb-fg2)', lineHeight: 1.5,
                marginTop: 5 }}>{opts.body}</div>
            )}
          </div>
        </div>

        {/* Optional item list */}
        {opts.items && opts.items.length > 0 && (
          <div style={{ margin: '0 20px 4px', border: '1px solid var(--lbb-border)',
            borderRadius: 8, overflow: 'hidden' }}>
            {opts.items.slice(0, 4).map((it, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'center', gap: 9, padding: '7px 11px',
                borderBottom: i < Math.min(opts.items!.length, 4) - 1
                  ? '1px solid var(--lbb-border)' : 'none',
                background: i % 2 ? 'var(--lbb-surface)' : 'var(--lbb-surface2)',
              }}>
                <Icon name={it.icon ?? 'folder'} size={12}
                  style={{ color: 'var(--lbb-fg3)', flex: '0 0 auto' }} />
                <span style={{ flex: 1, fontFamily: 'var(--lbb-mono)', fontSize: 11,
                  color: 'var(--lbb-fg)', whiteSpace: 'nowrap', overflow: 'hidden',
                  textOverflow: 'ellipsis' }}>{it.label}</span>
                {it.meta && (
                  <span style={{ fontFamily: 'var(--lbb-mono)', fontSize: 10.5,
                    color: 'var(--lbb-fg3)' }}>{it.meta}</span>
                )}
              </div>
            ))}
            {opts.items.length > 4 && (
              <div style={{ padding: '5px 11px', fontSize: 10.5, color: 'var(--lbb-fg3)',
                textAlign: 'center', fontStyle: 'italic', background: 'var(--lbb-surface2)',
                borderTop: '1px solid var(--lbb-border)' }}>
                + {opts.items.length - 4} more
              </div>
            )}
          </div>
        )}

        {/* Note / consequence line */}
        {opts.note && (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8,
            margin: '10px 20px 0', padding: '9px 11px', borderRadius: 7,
            background: `var(--lbb-${accent}-bg)`,
            border: `1px solid var(--lbb-${accent}-bar)` }}>
            <Icon name={opts.tone === 'danger' ? 'alert' : 'info'} size={13}
              style={{ color: `var(--lbb-${accent}-fg)`, marginTop: 1, flex: '0 0 auto' }} />
            <span style={{ fontSize: 11.5, color: 'var(--lbb-fg2)',
              lineHeight: 1.45 }}>{opts.note}</span>
          </div>
        )}

        {/* Footer */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 9,
          padding: '16px 20px 18px', marginTop: 6 }}>
          <div style={{ flex: 1 }} />
          <Button variant="ghost" size="md" onClick={() => onResolve(false)}>
            {opts.cancelLabel ?? 'Cancel'}
          </Button>
          <Button
            data-confirm-btn="true"
            variant={opts.confirmVariant ?? tone.confirmVariant}
            size="md"
            icon={opts.confirmIcon ?? (opts.tone === 'danger' ? 'trash' : 'check')}
            onClick={() => onResolve(true)}
          >
            {opts.confirmLabel ?? 'Confirm'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── useConfirm hook ───────────────────────────────────────────────────────────

export function useConfirm(): [
  (opts: ConfirmOpts) => Promise<boolean>,
  React.FC,
] {
  const [state, setState] = React.useState<{ open: boolean; opts: ConfirmOpts | null }>({
    open: false, opts: null,
  })
  const resolverRef = React.useRef<((v: boolean) => void) | null>(null)

  const confirm = React.useCallback((opts: ConfirmOpts) =>
    new Promise<boolean>((resolve) => {
      resolverRef.current = resolve
      setState({ open: true, opts })
    }),
  [])

  const onResolve = React.useCallback((v: boolean) => {
    setState({ open: false, opts: null })
    if (resolverRef.current) { resolverRef.current(v); resolverRef.current = null }
  }, [])

  const Host: React.FC = React.useCallback(() => (
    <ConfirmDialog open={state.open} opts={state.opts} onResolve={onResolve} />
  ), [state.open, state.opts, onResolve])

  return [confirm, Host]
}

// ── ConfirmDialogProvider (context-based alternative) ────────────────────────

interface ConfirmContextValue { confirm: (opts: ConfirmOpts) => Promise<boolean> }

const ConfirmCtx = React.createContext<ConfirmContextValue | null>(null)

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const [confirm, Host] = useConfirm()
  return (
    <ConfirmCtx.Provider value={{ confirm }}>
      {children}
      <Host />
    </ConfirmCtx.Provider>
  )
}

export function useConfirmContext(): (opts: ConfirmOpts) => Promise<boolean> {
  const ctx = React.useContext(ConfirmCtx)
  if (!ctx) throw new Error('useConfirmContext must be used inside ConfirmDialogProvider')
  return ctx.confirm
}
