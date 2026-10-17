# 06 · Pipeline — Primary Workflow

> ⚠️ **SUPERSEDED — read this first.** This document describes the *original* batch-table
> pipeline (`_source/screen-pipeline.jsx`). The shipping design is the **Pipeline Workspace**
> (`_source/pipeline2-*.jsx`), a queue + per-folder 5-stage detail panel — a different layout.
> For the current design build from those files and read **`14-pipeline-gap-punchlist.md`**
> (per-stage spec + what's still missing in the implementation) and **`15-data-contract.md`**
> (the API fields the panels need). Keep this doc only as background on the earlier approach.

Source: `_source/screen-pipeline.jsx`. **This is the highest-value screen in the app.** Build it second (after Home), or even before Home.

## Purpose

A user drops 50–100 new folders. The app runs each through 4 steps (verify → lookup → rename → LBDIR) and lets the user bulk-apply the renames once everything's vetted. The old app had this spread across 4 separate tools; the redesign unifies it.

## Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│ Top progress banner — counts + "Apply all 32" big CTA                  │  ~64px
├──────────────┬─────────────────────────────────────────────────────────┤
│              │  Filter chips · search · density · reveal-folder        │  ~48px
│ Folder queue ├─────────────────────────────────────────────────────────┤
│ rail (264px) │  Selection bar (visible when ≥1 row selected)           │  ~44px
│              ├─────────────────────────────────────────────────────────┤
│ - queue list │                                                         │
│ - "Run all"  │  Main table with grouped rows:                          │
│   actions    │    • Need attention   (14)                              │
│              │    • Ready to rename  (32)                              │
│              │    • Done             (36)                              │
│              │                                                         │
└──────────────┴─────────────────────────────────────────────────────────┘
```

The screen body is a grid: `grid-template-columns: 264px 1fr`, full height, flex-column inside the right pane.

## Pieces

### Top progress banner

- Subtle gradient bg: `linear-gradient(180deg, var(--lbb-accent-soft) 0%, transparent 140%)`
- Padding 12px 24px, bottom hairline border
- Layout: 36×36 accent-filled icon square | title block | counter pills | spacer | bulk actions
- Title: 16px/700 "Pipeline · 82 folders queued", 12px subtitle "Last run finished 14 minutes ago…"
- Counter pills (3, with dots): green "36 done", amber "32 ready to rename", red "14 need attention"
- Right-side: ghost "Bulk actions" + **primary CTA** "Apply all 32 proposed renames" (this button changes label based on what's pending)

### Folder queue rail (264px wide)

A left-aligned column inside the screen, separate from the app sidebar.

Top: 
- Label "Folder queue" + count badge
- Filter input

Middle (scrollable):
- Each item = 8px square status indicator (color from severity) + monospace folder name (truncated)
- Active item: `accent-soft` bg, `accent-mid` text

Bottom (sticky):
- Three small block buttons: `Add folders…`, `Scan tree…`, `Clear queue`
- A boxed "Run on selected" panel:
  - Title: uppercase fg3 small
  - Primary "Run all 4 steps" full-width
  - 2×2 grid: Verify / Lookup / Rename / LBDIR (secondary buttons)

### Main table area (right pane)

**Filter chips bar** (top):
- All / Need attention / Ready to rename / Done — each with count
- Separator
- Specific filters: Not found / Mismatch / Incomplete
- Spacer
- Filter input (240px), density icon button, reveal icon button

**Selection bar** (appears when 1+ rows selected):
- `accent-soft` bg, 8px 20px padding, 1px bottom border
- "{n} selected" in accent color + meta "· shift-click to extend · ⌘A all in view"
- Right side: ghost Clear, secondary Verify selected, secondary Lookup selected, primary "Apply {n} selected renames"

**Table** (scrollable):

Columns: edge / checkbox / Folder / Verify / Lookup / Rename / LBDIR / LB# / Action

Each of the 4 step headers has a **numbered circle badge** prefix (1/2/3/4) — important visual marker.

Rows grouped under `<GroupRow>` headers by severity bucket:

- **Need attention** (edge="bad" rows) — show what's wrong as a Pill in each step column. Action: secondary "Open" button
- **Ready to rename** (edge="warn" rows, often selected) — Verify ✓ Lookup ✓ Rename "Proposed" LBDIR ✓ → Action: **primary "Apply"** button per row. LB# is shown in accent color, weight 600.
- **Done** (edge="ok" rows) — all 4 steps Pass. Action: just a "Done" pill. Row text dimmer.

The whole table is virtualized in production — the prototype shows a "… 67 more folders below · virtual scroll" footer row.

### Step pill rendering

```jsx
<StepPill tone="ok|warn|bad|info|mute" label="Pass|Incomplete|Mismatch|...|—" />
```

A `Pill` with `min-width: 56px`, centered. `mute` tone always renders "—" (step hasn't run / N/A).

## Data shape

```ts
type PipelineRow = {
  folderName: string;           // displayed in mono
  folderPath: string;           // full disk path
  selected: boolean;
  severity: "attn" | "ready" | "done";
  steps: {
    verify:  "ok" | "warn" | "bad" | "mute";
    lookup:  "ok" | "warn" | "bad" | "mute";
    rename:  "ok" | "warn" | "bad" | "mute";
    lbdir:   "ok" | "warn" | "bad" | "mute";
  };
  proposedLBNumber: string | null;        // "LB-16591"
  proposedRename: { from: string; to: string } | null;
  errors: { step: string; message: string }[];
};
```

## Key interactions

| Action | Behavior |
|---|---|
| Drop folders onto window | Append to queue, run verify in background |
| Click a queue rail item | Scroll table to that row + highlight it |
| Check a row checkbox | Add to selection; selection bar appears |
| Shift-click row | Range select |
| ⌘A | Select all rows in current filter |
| Click "Apply" on a row | Apply that rename → row moves to Done bucket |
| Click bulk "Apply all 32" | Apply all rename-ready rows; show progress in top banner |
| Click `Open` on attention row | Reveal in OS file manager OR open the per-folder sub-tool |
| Click a column header | Sort by that step's status |

## Production notes

- **Virtualize this table.** 100+ rows is realistic; the design assumes virtual scroll with sticky header.
- The 4 sub-tools (Verify, Lookup, Rename, LBDIR) shown in the sidebar nav are **the same operations** as the 4 step columns here. The dedicated screens are for power-users who want to do one operation in isolation; the Pipeline is for batches. They share state.
- Long-running verify/scan operations should report progress in the **StatusBar** at app-level (via `statusExtra` prop on AppShell).
