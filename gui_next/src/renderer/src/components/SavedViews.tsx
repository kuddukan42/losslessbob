// Saved smart views — sidebar section (UI5 / FABLE_IDEAS UI#5).
//
// Renders the user's saved Library recording-lens filter sets as pinned sidebar
// entries with a LIVE count badge. Clicking a view restores its filters and
// jumps to the Library; hover reveals rename / delete. The section hides itself
// entirely when no views exist, so new installs never see empty chrome — the
// entry point to create one lives in ScreenLibrary's toolbar ("Save view").

import React, { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { useSavedViewsStore } from '../lib/savedViewsStore'
import { applyRecordingFilters } from '../lib/libraryFilterStore'
import { useLibraryRows, countForView } from '../lib/libraryRows'

export function SavedViews({ onNav }: { onNav: (id: string) => void }): React.JSX.Element | null {
  const { t } = useTranslation()
  const views = useSavedViewsStore(s => s.views)
  const renameView = useSavedViewsStore(s => s.renameView)
  const removeView = useSavedViewsStore(s => s.removeView)

  // Only pay for the catalog fetch once at least one view needs counting.
  const rows = useLibraryRows(views.length > 0)
  const counts = useMemo(() => {
    const m: Record<string, number> = {}
    for (const v of views) m[v.id] = countForView(rows, v.filters)
    return m
  }, [rows, views])

  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [hoverId, setHoverId] = useState<string | null>(null)

  if (views.length === 0) return null

  const apply = (id: string, filters: Parameters<typeof applyRecordingFilters>[0]) => {
    if (editingId === id || confirmingId === id) return
    applyRecordingFilters(filters)
    onNav('library')
  }

  const commitRename = () => {
    if (editingId) renameView(editingId, draft)
    setEditingId(null)
  }

  return (
    <div style={{ marginTop: 14 }}>
      <div
        style={{
          fontSize: 'var(--lbb-fs-10)',
          fontWeight: 700,
          color: 'var(--lbb-fg3)',
          letterSpacing: 0.12,
          textTransform: 'uppercase',
          padding: '6px 10px',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        <Icon name="star" size={12} />
        <span>{t('savedViews.title')}</span>
      </div>

      {views.map(v => {
        const isEditing = editingId === v.id
        const isConfirming = confirmingId === v.id
        const showActions = hoverId === v.id && !isEditing && !isConfirming
        const count = counts[v.id]

        if (isEditing) {
          return (
            <div key={v.id} style={{ padding: '2px 10px', marginBottom: 1 }}>
              <input
                autoFocus
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') commitRename()
                  if (e.key === 'Escape') setEditingId(null)
                }}
                onBlur={commitRename}
                style={{
                  width: '100%',
                  padding: '5px 8px',
                  border: '1px solid var(--lbb-accent-mid)',
                  borderRadius: 6,
                  background: 'var(--lbb-surface)',
                  color: 'var(--lbb-fg)',
                  fontSize: 'var(--lbb-fs-12-5)',
                  fontFamily: 'inherit',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>
          )
        }

        return (
          <div
            key={v.id}
            onMouseEnter={() => setHoverId(v.id)}
            onMouseLeave={() => setHoverId(null)}
            style={{ position: 'relative' }}
          >
            <button
              type="button"
              data-testid={`saved-view-${v.id}`}
              onClick={() => apply(v.id, v.filters)}
              title={v.name}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '7px 10px',
                marginBottom: 1,
                border: '1px solid transparent',
                borderRadius: 6,
                background: 'transparent',
                color: 'var(--lbb-fg2)',
                fontSize: 'var(--lbb-fs-12-5)',
                fontWeight: 500,
                textAlign: 'left',
                cursor: 'pointer',
                lineHeight: 1.2,
                fontFamily: 'inherit',
                transition: 'background 0.1s',
              }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--lbb-surface2)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
            >
              <Icon name="filter" size={14} />
              <span
                style={{
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {v.name}
              </span>

              {isConfirming ? (
                <span style={{ display: 'inline-flex', gap: 2 }}>
                  <span
                    role="button"
                    title={t('savedViews.confirmDelete')}
                    onClick={e => { e.stopPropagation(); removeView(v.id); setConfirmingId(null) }}
                    style={actionIconStyle('var(--lbb-warn-fg)')}
                  >
                    <Icon name="check" size={13} />
                  </span>
                  <span
                    role="button"
                    title={t('common.cancel')}
                    onClick={e => { e.stopPropagation(); setConfirmingId(null) }}
                    style={actionIconStyle('var(--lbb-fg3)')}
                  >
                    <Icon name="x" size={13} />
                  </span>
                </span>
              ) : showActions ? (
                <span style={{ display: 'inline-flex', gap: 2 }}>
                  <span
                    role="button"
                    title={t('savedViews.rename')}
                    onClick={e => { e.stopPropagation(); setDraft(v.name); setEditingId(v.id) }}
                    style={actionIconStyle('var(--lbb-fg3)')}
                  >
                    <Icon name="rename" size={13} />
                  </span>
                  <span
                    role="button"
                    title={t('savedViews.delete')}
                    onClick={e => { e.stopPropagation(); setConfirmingId(v.id) }}
                    style={actionIconStyle('var(--lbb-fg3)')}
                  >
                    <Icon name="trash" size={13} />
                  </span>
                </span>
              ) : (
                <span
                  style={{
                    fontSize: 'var(--lbb-fs-10-5)',
                    color: 'var(--lbb-fg3)',
                    fontVariantNumeric: 'tabular-nums',
                    fontWeight: 500,
                  }}
                >
                  {count === undefined ? '…' : count.toLocaleString()}
                </span>
              )}
            </button>
          </div>
        )
      })}
    </div>
  )
}

function actionIconStyle(color: string): React.CSSProperties {
  return {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 20,
    height: 20,
    borderRadius: 4,
    color,
    cursor: 'pointer',
  }
}
