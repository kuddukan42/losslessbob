// BUG-221: 5 call sites built the LosslessBob detail-page URL with inconsistent
// zero-padding/prefixing, so some produced a 404. One helper, used everywhere.

export const LB_SITE_BASE = 'http://www.losslessbob.wonderingwhattochoose.com'

/** Canonical "LB-00042" display label for an LB number. */
export function lbLabel(lb: number | string): string {
  const digits = String(lb).replace(/^LB-/i, '')
  return `LB-${digits.padStart(5, '0')}`
}

/** LosslessBob detail-page URL for an LB number, always zero-padded + "LB-" prefixed. */
export function lbDetailUrl(lb: number | string): string {
  return `${LB_SITE_BASE}/detail/${lbLabel(lb)}.html`
}
