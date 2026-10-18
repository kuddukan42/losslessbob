// TODO-368: shared display formatters (were copied per screen). For LB labels
// use lbLabel() from ./lbUrl.

/** Human byte size, 1024-based: "0 B", "512 KB", "3.4 MB", "12 GB". */
export function fmtBytes(n: number): string {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = n
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`
}

/** Locale-grouped integer ("12,345"); "—" when the value is missing. */
export function fmtNum(n: number | null | undefined): string {
  return n != null ? n.toLocaleString() : '—'
}
