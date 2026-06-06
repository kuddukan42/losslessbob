import React from 'react'
import { useTranslation } from 'react-i18next'
import { Icon } from './Icon'
import { Button, Input } from './index'
import { useFolderQueueStore } from '../lib/folderQueueStore'

interface FolderQueueRailProps {
  label: string
  /** Override the count display (e.g. "3/10" when filtering). Defaults to total folder count. */
  countLabel?: string
  filter: string
  onFilterChange: (v: string) => void
  filterPlaceholder?: string
  /** Extra controls rendered below the filter input (e.g. a "Hide verified" checkbox). */
  headerExtra?: React.ReactNode
  width?: number
  children: React.ReactNode
  /** Action buttons rendered above the always-present Clear button. */
  footer?: React.ReactNode
  /** Called after clearFolders() to let screens reset their own selection state. */
  onClear?: () => void
}

export function FolderQueueRail({
  label, countLabel, filter, onFilterChange, filterPlaceholder = 'Filter…',
  headerExtra, width = 280, children, footer, onClear,
}: FolderQueueRailProps): React.JSX.Element {
  const { t } = useTranslation()
  const { folders, clearFolders } = useFolderQueueStore()

  const handleClear = () => {
    clearFolders()
    onClear?.()
  }

  return (
    <aside style={{
      width, flex: `0 0 ${width}px`,
      background: 'var(--lbb-surface)', borderRight: '1px solid var(--lbb-border)',
      display: 'flex', flexDirection: 'column', minHeight: 0,
    }}>
      <div style={{ padding: '12px 12px 8px', borderBottom: '1px solid var(--lbb-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          <Icon name="folder" size={13} style={{ color: 'var(--lbb-fg3)' }} />
          <span style={{
            fontSize: 'var(--lbb-fs-10-5)', fontWeight: 700, color: 'var(--lbb-fg3)',
            letterSpacing: 0.1, textTransform: 'uppercase',
          }}>{label}</span>
          <span style={{
            marginLeft: 'auto', fontSize: 'var(--lbb-fs-11)', fontWeight: 600,
            color: 'var(--lbb-fg2)', fontVariantNumeric: 'tabular-nums',
          }}>{countLabel ?? folders.length}</span>
        </div>
        <Input
          icon="search"
          placeholder={filterPlaceholder}
          size="sm"
          style={{ width: '100%' }}
          value={filter}
          onChange={e => onFilterChange(e.target.value)}
        />
        {headerExtra}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 6px' }}>
        {children}
      </div>

      <div style={{
        padding: 12, borderTop: '1px solid var(--lbb-border)',
        display: 'flex', flexDirection: 'column', gap: 6,
      }}>
        {footer}
        <Button variant="ghost" size="sm" icon="trash" block disabled={!folders.length} onClick={handleClear}>
          {t('common.clearList')}
        </Button>
      </div>
    </aside>
  )
}
