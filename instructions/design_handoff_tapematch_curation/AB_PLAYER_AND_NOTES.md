# The A/B player and `human_notes` — for Q10

Both are shipped, working parts of the current `ScreenTapeMatch` that tj wants carried
forward. The design didn't know they existed, so §8's dossier stack (header → verdict →
conflict callout → evidence bars → LB page says → judgment) has no slot for either.

They are **not** two blocks of equal weight, which is the main thing to know:

- **`human_notes` is already part of the judgment control** — it's the free-text field
  that saves alongside the judgment value in the same request. §8's judgment control just
  needs to grow a textarea.
- **The A/B player is a genuinely new block** and needs a home in the vertical order.

---

## 1. `human_notes` — an addition to §8's judgment control

Today's judgment panel is one unit:

```
JUDGMENT   LB-00790 × LB-05503          ← 11px/700 uppercase label + 13px mono pair
[ same ][ different ][ uncertain ][ lb wrong ][ clear ]
┌───────────────────────────────────────┐
│ notes… (3 rows, resize:vertical)      │
└───────────────────────────────────────┘
                        [ Cancel ][ Save ]
```

- The five chips are the same four-value vocabulary §8 specifies
  (`confirmed_same` / `confirmed_different` / `uncertain` / `lb_wrong`) plus a Clear.
- Textarea: `rows=3`, `min-height:60px`, `resize:vertical`, 12px, `--lbb-surface` on
  `--lbb-border2`, 6px radius.
- Both fields save together in one `POST /api/tapematch/pairs/judgment`; notes are
  trimmed, and empty saves as null.
- Container: 14px padding, 8px radius, `--lbb-surface2` on `--lbb-border`, column, gap 10.

### The question this raises for §3

The current control has an **explicit Cancel / Save**, and a save can fail: HTTP 409
returns a `locked` error when the run is being written, rendered as an inline error line
in bad-fg.

But §10.7 says `Accept families` should "flush any pending judgments," which implies
judgments accumulate unsaved and commit later. Those are two different models. **Which is
it — does each judgment save on click (no Save button, optimistic, with a rollback path
for the 409), or do judgments stay pending until Accept flushes them?** §3's
`· 2 judged` counter reads more naturally as the second, but the shipped behavior is the
first.

---

## 2. The A/B player — needs a slot in §8

What it does: fetches one **performance-time-aligned** WAV clip per source, starts both
`<audio>` elements together, and keeps them sample-aligned for the clip's duration. So
switching between A and B is an **instant mute swap** — never a reload or reseek. You hear
the same moment of the same show from two tapes, and the differences pop out immediately.
It is the single most decisive piece of evidence for a same-or-different call, which is an
argument for placing it high in the stack rather than after the evidence bars.

```
A/B LISTENING                        [ not eligible ]

Position [    ] s   Duration [ 20 ] s   [ Load ]
Leave position blank to auto-pick a loud aligned moment.

[ ▶ Play ]   [ A · LB-00790 ][ B · LB-05503 ]
```

**States:**

- **Ineligible** — when the pair isn't cleanly aligned (`ab_eligible: false` from
  `GET /api/tapematch/pairs`). Whole panel drops to `opacity: .55`, every control inert,
  a mute `not eligible` pill sits next to the title. This is common — speed-offset and
  staircase pairs generally can't be aligned, which is exactly the population §6 is about.
- **Empty** — loaded nothing yet. Only the position/duration/Load row shows.
- **Loading** — Load button reads `Loading…`, disabled.
- **Loaded** — Play/Pause primary button plus the A/B chip pair appear.
- **Error** — one line in `--lbb-bad-fg`. Five distinct messages: not eligible, position
  out of range, folder missing, locked, generic load failure.

**Current styling** (matches the judgment panel deliberately): 14px padding, 8px radius,
`--lbb-surface2` on `--lbb-border`, column flex gap 10, title 11px/700 uppercase
`.04em` in `--lbb-fg3`. Number inputs are 56px wide, 5px radius, 11.5px.

### What design needs to decide

1. **Where in the §8 stack?** The argument for high (right under the verdict, above the
   evidence bars) is that listening settles the question the evidence bars only
   circumstantially support. The argument for low (just above judgment) is that it pairs
   with the decision it informs, and the two panels already share a visual language.
2. **Does the ineligible state earn its space?** It will be showing dimmed-and-inert on a
   large share of pairs. Options: keep it visible as-is, collapse to a single line, or
   omit the block entirely when ineligible.
3. **The A/B chips are the only "which source am I hearing" indicator.** With the dossier
   in drawer mode at ≤1520px, is a chip pair still enough, or does playback need a more
   prominent active-source treatment?
4. **Nothing shows playback progress** — no scrubber, no elapsed time, and the clip just
   ends. Was that a deliberate minimum, or should §8 specify a progress affordance?
