import { useCallback, useRef, useState } from 'react'

// Drag-to-resize single width (e.g. a side panel), persisted to localStorage
// under `storageKey`. Same write-on-drag-end behavior as useResizableColumns.
export function useResizableWidth(storageKey: string, defaultWidth: number, min = 280, max = 720) {
  const [width, setWidth] = useState<number>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw) return Math.min(max, Math.max(min, JSON.parse(raw)))
    } catch {}
    return defaultWidth
  })

  const widthRef = useRef(width)
  widthRef.current = width

  // Panel is anchored to the right edge, so dragging the left-edge handle
  // right (positive dx) should shrink it, not grow it.
  const startResize = useCallback((startX: number, startWidth: number) => {
    const onMove = (e: MouseEvent) => {
      const newWidth = Math.min(max, Math.max(min, startWidth - (e.clientX - startX)))
      setWidth(newWidth)
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      try { localStorage.setItem(storageKey, JSON.stringify(widthRef.current)) } catch {}
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [storageKey, min, max])

  return { width, startResize }
}

// Drag-to-resize column widths, persisted to localStorage under `storageKey`.
// Widths are written on drag end (not every mousemove) to avoid thrashing storage.
export function useResizableColumns<K extends string>(storageKey: string, defaults: Record<K, number>) {
  const [widths, setWidths] = useState<Record<K, number>>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw) return { ...defaults, ...(JSON.parse(raw) as Partial<Record<K, number>>) }
    } catch {}
    return defaults
  })

  const widthsRef = useRef(widths)
  widthsRef.current = widths

  const startResize = useCallback((key: K, startX: number, startWidth: number) => {
    const onMove = (e: MouseEvent) => {
      const newWidth = Math.max(40, startWidth + e.clientX - startX)
      setWidths(w => ({ ...w, [key]: newWidth }))
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      try { localStorage.setItem(storageKey, JSON.stringify(widthsRef.current)) } catch {}
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [storageKey])

  return { widths, startResize }
}
