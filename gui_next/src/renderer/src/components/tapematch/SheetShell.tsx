/**
 * The overlay shell §11's `report.md` view and §12's run diff both use.
 *
 * README §12: the diff "reuses the report's sheet shell exactly … deliberate:
 * these are two readings of the same artifact set, and a curator shouldn't
 * have to learn a second overlay." So it is one component, not two copies —
 * the filename slot, the path slot, the actions and the outline rail are the
 * only differences between them.
 */

import React, { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

/** Keep tab focus inside the sheet while it is open. */
function trapFocus(e: React.KeyboardEvent<HTMLDivElement>): void {
  if (e.key !== 'Tab') return
  const root = e.currentTarget
  const focusables = root.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
  )
  if (!focusables.length) return
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  if (e.shiftKey && (document.activeElement === first || document.activeElement === root)) {
    e.preventDefault(); last.focus()
  }
}

export interface SheetShellProps {
  /** The mono filename slot — `report.md`, `Run diff`. */
  name: string
  /** The dim path slot under it — a run dir, or the date + venue. */
  path: string | null
  label: string
  /** Header controls, right-aligned before the close button. */
  actions: React.ReactNode
  /** Optional banner between header and body (§11's stale banner). */
  banner?: React.ReactNode
  /** The 196px rail. Omit for a sheet with no outline. */
  rail?: React.ReactNode
  /** Extra CSS the sheet needs (§11.1's print block). */
  css?: string
  onClose: () => void
  /** The scrolling document column; gets the ref for offset-based scrolling. */
  children: React.ReactNode
  docRef?: React.RefObject<HTMLDivElement>
}

export function SheetShell({
  name, path, label, actions, banner, rail, css, onClose, children, docRef,
}: SheetShellProps): React.JSX.Element {
  const sheetRef = useRef<HTMLDivElement>(null)
  useEffect(() => { sheetRef.current?.focus() }, [])

  // Esc closes this layer first — capture phase, stopping propagation, so the
  // stack unwinds diff → report → dossier (§11/§12 shell).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose() }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose])

  return createPortal(
    <div className="rpWrap" style={{
      position: 'fixed', inset: 0, zIndex: 40, display: 'flex',
      alignItems: 'center', justifyContent: 'center', padding: 26,
    }}>
      <div onClick={onClose} style={{
        position: 'absolute', inset: 0, background: 'rgba(5,8,14,.62)',
      }} />
      <div
        ref={sheetRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        tabIndex={-1}
        className="rpSheet"
        onKeyDown={trapFocus}
        style={{
          position: 'relative', width: 'min(1040px, 95vw)', height: 'min(880px, 94vh)',
          background: 'var(--lbb-surface)', border: '1px solid var(--lbb-border2)',
          borderRadius: 10, boxShadow: '0 24px 70px rgba(0,0,0,.55)', overflow: 'hidden',
          display: 'flex', flexDirection: 'column', minHeight: 0, outline: 'none',
        }}
      >
        <div className="rpHead" style={{
          display: 'flex', alignItems: 'center', gap: 12, padding: '11px 14px',
          borderBottom: '1px solid var(--lbb-border)', background: 'var(--lbb-surface2)',
          flex: '0 0 auto',
        }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ font: '700 13px var(--lbb-mono)', color: 'var(--lbb-fg)' }}>{name}</div>
            {path && (
              <div title={path} style={{
                font: '500 10.5px var(--lbb-mono)', color: 'var(--lbb-fg3)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                maxWidth: 520, direction: 'rtl', textAlign: 'left',
              }}>{path}</div>
            )}
          </div>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            {actions}
          </div>
        </div>
        {banner}
        <div className="rpBody" style={{
          display: 'grid',
          gridTemplateColumns: rail ? '196px minmax(0,1fr)' : 'minmax(0,1fr)',
          flex: 1, minHeight: 0,
        }}>
          {rail && (
            <div className="rpOutline" style={{
              background: 'var(--lbb-surface2)', borderRight: '1px solid var(--lbb-border)',
              overflowY: 'auto', padding: '12px 8px', minHeight: 0,
            }}>{rail}</div>
          )}
          <div ref={docRef} className="rpDoc" style={{
            overflowY: 'auto', padding: '22px 30px 60px', minHeight: 0, position: 'relative',
          }}>{children}</div>
        </div>
      </div>
      {css && <style>{css}</style>}
    </div>,
    document.body,
  )
}
