# Handoff: lb-nc compact (phone-width) layout

> Retrieved 2026-10-02 from the Claude Design project "LosslessBob — lb-nc phone view"
> (`design_handoff_lbnc_phone_layout/README.md`). Frames:
> https://claude.ai/design/p/db99ba8e-0a99-4f9c-a2c1-635606ea08b8?file=lb-nc+Phone+View.dc.html

## Overview
lb-nc is a two-pane terminal file manager for LosslessBob (LB) concert folders. When you SSH in from a phone, the terminal is **35 columns × 33 rows**, and the current layout loses the information you need: LB numbers get cut, job status shows up twice, and most of the job/log area sits empty. This spec adds a **compact layout**, used automatically on narrow terminals, built from the two directions the user picked:

- **1b – LB-first rows + cursor strip** (smallest change)
- **1c – LB-first rows + cursor card** (bottom third merged into one card)

It also covers the **Apply renames** confirmation in both directions (**2a**, **2b**).

## About the design files
`lb-nc Phone View.dc.html` is a **design reference built in HTML**. Every frame is a cell-exact 35×33 terminal grid, with one `<div class="l">` per row and one `<i class="…">` per colour run. Do not ship the HTML. Rebuild the layout in lb-nc's existing TUI code with its current drawing and colour-pair approach. Frames 1a and 1e copy the real screenshots cell for cell; use them to check your measurements.

## Fidelity
**High fidelity, at the character-cell level.** Column positions, truncation points, glyphs and colour roles are final. Some LB numbers, the Hamburg→Paris rows and the canonical name `2017-04-02 STOCKHOLM, SWEDEN (LB-12571)` are stand-in data.

## When to use the compact layout
- Turn it on when terminal width is **< 50 cols**. Single pane only: show the active pane full width, with its letter in the header (`[L]`/`[R]`).
- Re-check on `SIGWINCH` / resize.
- All widths below assume W = 35. Write the code against W, not against 35.
  - Box inner width = W − 2.
  - Every row must be padded to exactly W cells. Glyphs such as `…`, `→`, `⇄`, `⇒`, `▶`, `■` and `≠` each count as **one cell**.

## Shared: header (2 rows)
```
 [L] DYLAN1:/2017        158G free
 4 tagged 2.5G · 119 LB · 3 off
```
- Row 1:
  - `[pane] DRIVE:/path` with a space on each side, in the **header** role (inverse). Truncate the path from the left with `…` if needed.
  - Free space for the pane's drive, right-aligned, in the **frame** role, with one trailing space.
- Row 2: a summary built from the parts that apply, joined with ` · `.
  - Tag count and size (`4 tagged 2.5G`) in the **tagged** role.
  - `119 LB` (LB folder count) and `3 off` (misfiled count) in the **frame** role.
  - In rename mode, the first part becomes `1 to rename` in the **flagged** role.
- This replaces the old `drives:` log row.

## Shared: list rows (LB-first)
Format, 33 cells inside the box:
```
▶04-02 12569 Stockholm, S… → 537M
│└┬──┘ └┬──┘ └────┬──────┘ │ └┬─┘
│ 5     5      13         1  4      cell widths, separated by single spaces
cursor
```
- **Col 0**: `▶` on the cursor row, otherwise a space.
- **Day**: `MM-DD`. Drop the year when the folder is a year folder (path ends in `/YYYY`). Otherwise show `YYYY-MM-DD` and shorten the name column by 5.
- **LB**: the number without the `LB-` prefix.
- **Name**: the folder name with the leading date and any `LB-nnnnn`, `(LB-nnnnn)` or `[LB-nnnnn]` removed and trimmed. Fit it to 13 cells: if longer, cut to 12 and add `…`; if shorter, pad with spaces.
- **Status glyph**: same meaning as today (`→` will move, `⇄` in progress, etc.).
- **Size**: right-aligned in 4 cells (`537M`, ` 1.2G`).
- **Colour roles**: same as today. Tagged = tagged role (amber, bold); cursor = cursor role (inverse bar across the full inner width); flagged/misfiled-name = flagged role (pink, bold); otherwise text.
- The `..` row stays as ` ..`.

## Variant 1b – cursor strip + log
Rows from top to bottom: header 2 · `┌` · `..` · **list (17)** · strip divider · strip (3) · log divider · log (3) · `└` · status bar · keys (2).
- **Strip divider**: `├─ LB-12569 ──────── misfiled ─┤`, with the LB number on the left and the state on the right (`misfiled`, `ok`, `rename?`, …), filled with `─`.
- **Strip rows**, each starting with one leading space:
  1. The full folder name, word-wrapped across rows 1–2. If it fits on one row, row 2 holds the `(LB-nnnnn)` part on its own.
  2. (continuation of the name)
  3. `→ /mnt/DYLAN2/Concerts/2017`: the destination, truncated from the left if needed.
- **Log divider**: `├─ log (running) ───┤`, or `├─ log ───┤` when idle.
- **Log rows**: the latest 3 events, newest at the bottom, in short form: ` 12575 moved → DYLAN2`, ` 13054 verifying 57/57 files`.
- **Status bar**: shown only while a job runs: ` 13054 verify 57/57 ` (status role), ` 100% ` (key role), then ` 3 queued` (status role), padded to W.

## Variant 1c – cursor card
Rows: header 2 · `┌` · `..` · **list (19)** · card divider · card (4) · job divider · last event (1) · `└` · keys (2). There is no status bar.
- The card divider and rows 1–3 are the same as the 1b strip.
- **Card row 4**, frame role: ` 537M fits · DYLAN2 412G free`, showing whether the folder fits on the destination drive. Use `doesn't fit` when it doesn't (consider using the flagged role for that case).
- **Job divider**: puts the running job in the divider: `├─ ■ 13054 verify 57/57 ─── +3 ─┤`. `■` + LB + phase + progress go on the left; the number of queued jobs (`+N`) goes on the right. When idle: `├─ log ───┤`.
- **Last event row**: one row, the most recent log event. The full log moves behind a key (suggestion: `L`, or reuse F3 View).

## Apply renames confirmation
Triggered by the existing Apply renames action. The current version (1e) is a 31-cell dialog that cuts off the name being confirmed. Use the form that matches the chosen variant.

### 2a – full-width dialog (pairs with 1b)
Takes the place of the strip, log and status rows. The list stays above it with 10 entries.
```
├┌─ Apply renames ──────── 1 of 1 ─┐┤
│ LB-12571 · 04-02 · 578M          │
│ from                             │   (muted)
│ Stockholm_spot LB-12571          │
│ to                               │   (muted)
│ 2017-04-02 STOCKHOLM, SWEDEN     │   word-wrapped, as many rows as needed
│ (LB-12571)                       │
│                                  │
│ In place. Logged to              │   (muted)
│ rename_history.                  │
│                                  │
│    [ y ] rename      [ n ]       │
└──────────────────────────────────┘
```
- The dialog covers the box's inner width (33 cells), with its own box drawn in the dialog roles.
- The title shows the position in the queue (`1 of N`). The y/n keys move through the queue.
- `[ y ] rename` uses the danger role. `[ n ]` uses the dialog text role.
- Keys: `y` apply the rename and go to the next one · `n` skip it · `Esc` close.

### 2b – rename in the card (pairs with 1c)
No dialog. When the cursor is on a row whose name ≠ canonical, the card becomes:
```
├─ LB-12571 ──────────── rename? ─┤
│ Stockholm_spot LB-12571         │   frame role (old name)
│ ⇒ 2017-04-02 STOCKHOLM, SWEDEN  │
│   (LB-12571)                    │
│ [ y ] rename   [ n ] keep       │   danger role / key role
```
- `y` and `n` act on the cursor row. After `y`/`n`, the cursor moves to the next flagged row and the card fills in again.
- The last-event row shows ` 12571 name ≠ canonical`.

## Key bar (compact)
Two rows, 5 slots × 7 cells (1 digit in the key role + 6 label cells in the bar role):
```
1Help  2Info  3View  4Pipe  5Scan
6Move  7File  8Misfd 9Menu  0Quit
```
The full labels fit, so drop the 3-letter abbreviations.

## State
Nothing new beyond what lb-nc already tracks. The compact renderer needs:
- `layout = compact` (from width) and `bottom = strip | card` (config option; pick a default after testing).
- Per-row data: date, LB number, cleaned name, full name, status glyph, size, tagged/flagged state, misfiled state, destination path.
- Destination drive free space (for the 1c fits line).
- The running job (LB, phase, done/total), the queue length, and the last N log events (with a short form for each).
- The rename queue (old name, canonical name, LB, size) and its position.

## Colour roles (sampled from screenshots)
| role | fg | bg | weight |
|---|---|---|---|
| background | — | `#0b5f9a` | |
| text | `#eef4fa` | bg | 500 |
| frame / muted (borders, dividers, dim info) | `#55adf8` | bg | |
| header / cursor / bar / status (inverse) | `#14213a` | `#3399f4` | header 700 |
| key digit | `#ffffff` | `#1c2540` | |
| tagged | `#f4b25c` | bg | bold |
| flagged | `#f690cd` | bg | bold |
| dialog text | `#262b40` | `#e1e3ea` | |
| dialog muted | `#4f5675` | `#e1e3ea` | |
| dialog field | `#f0f2f7` | `#2d3148` | |
| danger button | `#ffffff` | `#f04f4f` | bold |

Map these to lb-nc's existing curses/terminal colour pairs. The hex values are close matches to the screenshots, not new colours.

## Files
- `lb-nc Phone View.dc.html`: all frames.
  - Turn 2 (top): 2a and 2b, rename state.
  - Turn 1: 1a and 1e are the current screens (references); 1b, 1c and 1d are proposals (1d was not chosen).
- `term.css`: colour roles and cell metrics for the HTML reference only.
- `support.js`: the runtime the HTML reference needs to open in a browser.
