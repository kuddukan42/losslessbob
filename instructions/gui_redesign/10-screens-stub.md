# 10 · Stub Screens — Sub-tools & Assets

These 7 screens are referenced in the nav but **were not designed in detail** during the prototype phase. They have slots in the app shell (`screen-pipeline.jsx`-style files like `screen-drillins.jsx` and `screen-assets.jsx` exist as placeholders).

Behavior is described below so the developer can either:
- Implement them with a "coming soon" empty state initially, OR
- Design + implement them later as separate work items.

## Ingest sub-tools (Verify / Lookup / Rename / LBDIR)

These four screens are **single-folder versions** of the Pipeline screen's four step columns. The Pipeline screen does them in batch; these screens let a power-user run one operation on one folder for finer control.

Shared layout pattern:
- Top: a path picker / "Open folder…" button
- Middle: results panel specific to the operation
- Bottom: an action button to apply / confirm

### Verify
- Pick a folder. Show its files in a table with: filename, expected checksum (from `checksums` table), actual checksum (computed), match Y/N
- Bottom action: "Mark as verified" (writes pass to `lb_status_history`)
- The Pipeline screen uses this same logic for batch verification

### Lookup
- Pick a folder OR enter checksums manually
- Run lookup against the master DB
- Show match table: candidate LB#, confidence score, location/date
- Bottom action: "Confirm match" / "Mark as new entry"

### Rename
- Pick a folder
- Show its current name + a suggested canonical name (per LosslessBob naming convention)
- Show a diff
- Bottom action: "Apply rename"

### LBDIR
- Pick a folder
- Generate the canonical `lbdir.txt` (a text file listing the folder's contents w/ checksums in LB format)
- Show preview
- Bottom action: "Write lbdir.txt to folder"

## Asset screens

### Attachments
- Browse all attached files for any LB#: `lbdir.txt`, `ffp.txt`, `info.txt`, etc.
- Layout: file list left (mono filenames + size), preview pane right (monospace text viewer for the selected file)
- Use the same edge-bar treatment for status (current/stale/missing)

### Spectrograms
- Gallery of spectrogram images per LB#
- Layout: filter row + responsive grid of spectrogram thumbnails (~240px wide each)
- Click thumbnail → fullscreen lightbox
- The `app.css` already has `.lbb-spec-canvas` styled background as a placeholder visualization (dark→amber→cream gradient w/ noise overlay)

### Map
- Concert venue map with ~6,676 pinned locations
- Layout: full-bleed map left, side panel right with filtered location list
- Markers: dots colored by decade or by ownership
- Click marker → side panel shows shows-at-that-venue list
- Use Leaflet or MapLibre with a muted basemap; `app.css` has a `.lbb-map-canvas` placeholder style showing dots-on-cream/dark backdrop for the empty state / loading

## Implementation note

When implementing these stubs as placeholders first, use this shape:

```jsx
function ScreenVerify() {
  return (
    <div style={{ padding: "60px 40px", maxWidth: 720, margin: "0 auto" }}>
      <h1>Verify</h1>
      <Banner tone="info" icon="info" title="Coming soon">
        This dedicated tool will let you verify a single folder's checksums against the master DB.
        For now, use the <strong>Pipeline</strong> screen for batch verification.
      </Banner>
    </div>
  );
}
```

That keeps the nav working without blocking shipping the rest.
