// ── Clipboard ─────────────────────────────────────────────────────────────────
//
// `navigator.clipboard.writeText` is unreliable in this app: the packaged
// renderer is a file:// document and the async Clipboard API rejects with
// "Document is not focused" whenever the write is triggered from a handler that
// runs while a context menu or modal is closing — exactly the shape of the
// "post to forum, then copy the topic link" flow. The Electron main process has
// no such precondition, so prefer the IPC path and keep the web API as a
// fallback for the browser-only dev/verify harness.

/**
 * Copy text to the system clipboard.
 *
 * Args:
 *     text: The text to place on the clipboard. Empty strings are a no-op.

 * Returns:
 *     True if the text reached the clipboard, False if every path failed.
 */
export async function copyText(text: string): Promise<boolean> {
  if (!text) return false
  try {
    if (typeof window.api?.writeClipboard === 'function') {
      return await window.api.writeClipboard(text)
    }
  } catch { /* fall through to the web API */ }
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
