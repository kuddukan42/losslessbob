// BUG-221: 5 call sites built the LosslessBob detail-page URL with inconsistent
// zero-padding/prefixing, so some produced a 404. One helper, used everywhere.

const LB_SITE_BASE = 'http://www.losslessbob.wonderingwhattochoose.com'

/** LosslessBob detail-page URL for an LB number, always zero-padded + "LB-" prefixed. */
export function lbDetailUrl(lb: number | string): string {
  const digits = String(lb).replace(/^LB-/i, '')
  return `${LB_SITE_BASE}/detail/LB-${digits.padStart(5, '0')}.html`
}
