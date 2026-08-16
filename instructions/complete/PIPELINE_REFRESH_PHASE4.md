# Pipeline Refresh — Phase 4 spec: human queues as first-class blockers

> Companion to `PIPELINE_REFRESH_INVENTORY.md` (57-step inventory, D1–D8),
> `PIPELINE_REFRESH_PHASE1.md` (read-only freshness planner),
> `PIPELINE_REFRESH_PHASE2.md` (CLI-only steps become buttons) and
> `PIPELINE_REFRESH_PHASE3.md` (chained execution in dependency order).
> Phase 4 of 4 — the last phase. Written 2026-08-16. Tracks TODO-310.
>
> It adds one module, no tables, three routes, one new field on every step row,
> a queue panel on the freshness card, and nav badges. It runs nothing new: the
> work a queue represents is a human's, and the only thing software can do about
> it is stop hiding it.

---

## 1. Context — why this phase exists

Phases 1–3 made *machine* work visible and runnable: freshness is computed,
steps are buttons, chains execute in order. Human work is still invisible.
Inventory D5: four review queues sit mid-graph, each with no "N items waiting"
surface outside its own screen, each degrading downstream output silently.

Measured on the live DB, 2026-08-16:

| Queue | Pending now | Where it is decided today |
|---|---|---|
| Taper conflicts (`taper_attributions.conflict=1`, undecided) | **129** of 130 | per-LB in the Library detail panel, or the mobile queue page — no desktop list |
| Setlist-fingerprint suggestions (`status='pending'`) | **242 LBs** (691 rows) | `/fingerprint` (curator) |
| TapeMatch date curation (dates with pairs, never accepted) | **3,057** of 3,060 | `/tapematch` |
| Xref ingest filesets (`status='staged'`) | **0** | **no GUI at all** — four routes, zero screens |

Two of those numbers are the phase's whole design problem. 129 is a queue that
should drain to zero and visibly has not. 3,057 is not a backlog anyone intends
to clear — TapeMatch curation is opt-in, 3 dates deep, and rendering it as
"3,057 items waiting" would train the user to ignore every badge the card shows.
And the queue with the *cleanest* count (xref, 0) is the one with nowhere to go.

Intended outcome: every human queue has one honest count in one place, the steps
whose output it degrades say so, the chain preview mentions it without refusing
to run, and the one queue with no screen gets a way in.

**Out of scope:** incremental / affected-LB execution (inventory D4 and
requirement 4 stay open — see §8), parallel chains, and any scheduling.

---

## 2. Binding decisions (tj — **confirm before implementing**)

| # | Decision |
|---|---|
| 1 | Queues are a **separate registry**, not `STEPS` entries. A queue is not runnable, has no upstream, and must never enter a Phase 3 chain plan. `backend/queues.py` owns it; `refresh.py` does not import it (same one-way rule Phase 3 kept for `refresh_exec`). |
| 2 | Two queue **kinds**. `gate` — expected to drain to zero; gets a count, a badge, and step attention. `backlog` — open-ended by nature; gets a *ratio* ("3 of 3,060 curated"), never a badge, never attention. TapeMatch date curation is the only `backlog` today. |
| 3 | A pending queue **never changes a step's `state`**. `stale`/`blocked`/`fresh`/`unknown` keep their Phase 1 meanings exactly; queues ride on a new, orthogonal `attention` field. A red card and a refusal to run are the wrong response to "a human hasn't reviewed 129 rows". |
| 4 | Therefore a chain **never refuses to start** on a queue. `plan_chain` gains `advisories` — text the preview dialog shows above the confirm button, and nothing else. |
| 5 | Counts come from the **app DB only**. TapeMatch judgments live in `tools/tapematch/observations.db`, which the nightly analysis runs hold locked for hours; the freshness path must never open it. The app-DB mirror (`tapematch_pairs` vs `tapematch_date_curation`) is the sanctioned proxy — `db.py` already documents why the curation verdict lives app-side. |
| 6 | **No new tables.** Queue counts are derived on read; there is no snapshot history, no snooze, no dismiss-until. D8 is not reopened. |
| 7 | Xref ingest is **display-only** (tj, 2026-08-16): the panel shows its count and nothing else. `checksums` is Jeff's table — it is populated by his site updates, and this install does not author rows in it. The staged filesets are files his flat-file drop did not include; the resolution is a later drop or a word to Jeff, not a local Approve button. `POST /api/xref_ingest/approve`/`reject` stay curl-only, exactly as today. Every other queue deep-links to the screen that already owns it. |
| 8 | `master_publish` gains an **advisory, not a gate**, when any `gate` queue is non-empty — this answers inventory open question 4 in the direction that does not add a way for a publish to fail. |

Decision 2 is the one to argue with first: it is a judgment about what the user
intends, not a fact about the data.

---

## 3. Deliverables

### 3.1 `backend/queues.py` (new, ~180 lines)

```python
class RefreshQueue(NamedTuple):
    queue_id: str          # 'taper_conflicts'
    label: str             # i18n key suffix (queue_id verbatim, Phase 1 style)
    kind: str              # 'gate' | 'backlog'
    count_sql: str         # -> one row, one int: items still awaiting a human
    total_sql: str | None  # 'backlog' only -> denominator for the ratio
    blocks: tuple[str, ...]        # step_ids whose output this degrades
    screen: str | None     # GUI route to send the user to, or None
    action: str            # one line: what the human actually does there

QUEUES: tuple[RefreshQueue, ...]

def queue_counts(db_path: str | None = None) -> list[dict]
def attention_by_step(queues: list[dict]) -> dict[str, list[dict]]
```

`queue_counts` opens one connection via `db.get_connection(db_path)`, runs each
`count_sql` through `refresh._run_scalar` (reused, not reimplemented — it already
swallows a missing table into `None`, which is exactly the "install without that
feature" case), and returns:

```python
[{"queue_id": "taper_conflicts", "kind": "gate", "count": 129, "total": None,
  "blocks": ["attribute_tapers", "compute_show_picks", "master_publish"],
  "screen": "/library?view=taperReview", "action": "confirm, reject or mark unresolved",
  "state": "pending"}]        # 'pending' | 'clear' | 'unknown'
```

`state='unknown'` when the count SQL returned `None` (table absent) — the same
honesty rule Phase 1 applied to steps with no signal. A `backlog` queue is never
`pending`; it is `clear` when `count == 0` and otherwise reports its ratio.

**The four queues, with SQL verified against the live DB (§1 numbers, all four
queries under 1.5 ms — cheap enough to fold into `/api/refresh/status`):**

| `queue_id` | kind | `count_sql` | `blocks` | screen |
|---|---|---|---|---|
| `taper_conflicts` | gate | `SELECT COUNT(*) FROM taper_attributions ta WHERE ta.conflict=1 AND NOT EXISTS (SELECT 1 FROM taper_confirmations tc WHERE tc.lb_number=ta.lb_number)` | `attribute_tapers`, `compute_show_picks`, `master_publish` | `/library?view=taperReview` |
| `fingerprint_suggestions` | gate | `SELECT COUNT(DISTINCT lb_number) FROM setlist_fingerprint_suggestions WHERE status='pending'` | `setlist_fingerprint` | `/fingerprint` |
| `xref_filesets` | gate | `SELECT COUNT(*) FROM xref_ingest_filesets WHERE status='staged'` | `xref_ingest`, `lb_master_reconcile` | `null` (inline, §3.5) |
| `tapematch_dates` | backlog | `SELECT COUNT(*) FROM (SELECT DISTINCT concert_date AS d FROM tapematch_pairs) x WHERE NOT EXISTS (SELECT 1 FROM tapematch_date_curation c WHERE c.concert_date=x.d)` · total: `SELECT COUNT(DISTINCT concert_date) FROM tapematch_pairs` | `tapematch_sync` | `/tapematch` |

Counting *decision units*, not rows, is deliberate: 691 fingerprint suggestion
rows are 242 decisions (one per LB), and a user shown 691 will read the queue as
three times more work than it is.

A test asserts every `blocks` entry is a real `refresh.STEPS` step_id — the same
integrity direction Phase 3's registry test enforces, for the same reason.

### 3.2 `refresh.compute_plan()` — one new field per step

Each step dict gains `attention: [{"queue_id", "count", "kind"}]`, empty for the
23 steps no queue names. Computed by `compute_plan` calling `queues.queue_counts`
once and mapping through `attention_by_step` — **not** by `refresh` importing
`queues` at module scope. Per decision 1 the dependency runs the other way, so
the call is a lazy import inside `compute_plan`, guarded so an ImportError leaves
`attention` empty rather than breaking the card.

The top-level response gains `queues: [...]` (the `queue_counts` list verbatim)
and `queue_pending_total: int` (sum over `kind='gate'` only — the number the nav
badge shows).

No change to `_step_state`, no change to any state value, no change to the
existing keys. That is decision 3 expressed as a diff constraint.

### 3.3 `refresh_exec.plan_chain()` — advisories

The plan dict gains:

```python
"advisories": [{"queue_id": "fingerprint_suggestions", "count": 242,
                "step_id": "setlist_fingerprint",
                "kind": "queue"}]
```

One entry per `gate` queue that `blocks` a step in `runnable`, plus one with
`kind='publish'` when `master_publish` is in `runnable` and any gate queue is
non-empty (decision 8). `blocked_by_running` and the 409 behaviour are untouched
— advisories never affect `POST /api/refresh/chain/start`.

### 3.4 Routes (`backend/app.py`)

| Route | Body / query | Response |
|---|---|---|
| `GET /api/refresh/queues` | — | `{"queues": [...], "pending_total": n, "computed_at": …}` |

Only one new route, and no existing route is called by anything new (decision 7
leaves the xref routes curl-only). `/api/refresh/status` already gains `queues` via §3.2, and
the standalone route exists so the nav badge can poll something cheap without
recomputing the whole 27-step plan every 30 s.

### 3.5 GUI — queue panel on `DataFreshnessCard.tsx`

A section below the trigger groups, above nothing else:

- **Gate queues** — one row each: label, count pill (warn-coloured when > 0,
  muted when 0), the `action` line, and a "Review →" button that navigates to
  `screen`. A `clear` gate renders muted with a check, not hidden: a queue that
  disappeared when empty would leave the user unable to confirm it is empty.
- **`xref_filesets`** — count only, no Review button and no expander (decision 7).
  Its `action` line says what a non-zero count means rather than offering to act:
  *"site-mirror checksum files Jeff's DB drop didn't include — resolved by a
  later drop"*. This is the one queue the app reports and cannot resolve, and the
  panel should read that way.
- **Backlog queues** — one row, ratio + thin progress bar ("3 of 3,060 dates
  curated"), no pill, no colour. It reads as information, not as debt.
- **Step rows** — a step with non-empty `attention` gets a small inline marker
  after its state chip (`⚑ 129 to review`), which is a button to the same screen.
  Never coloured like `stale`; it is a distinct, quieter treatment.
- **Chain preview dialog** — `advisories` render as a short list above the
  confirm button, prefixed "Running anyway is fine —". Confirm stays enabled.

`ScreenLibrary` gains a `view` search-param reader (it already consumes `lb`
through `useSearchParams`, so this is a small addition next to it) so
`/library?view=taperReview` lands on the right view.

### 3.6 GUI — nav badges (`AppShell.tsx` + `lib/navigation.ts`)

`NAV_GROUPS` items already carry an optional `count`, and `AppShell` already
overrides one dynamically (`collectionCount`). Extend the same pattern: poll
`/api/refresh/queues` every 60 s in `AppShell`, and map `library`,
`fingerprint` and `tapematch` nav items to their queue's count. `backlog` kind
contributes nothing, so `/tapematch` shows no badge (decision 2).

`ScreenHome`'s card gets the same data from its existing `/api/refresh/status`
query — no second poller there.

New `en.json` keys: `refresh.queues.{title,pending,clear,unknown,review,action,
ratio,attention,advisoryQueue,advisoryPublish}`
plus one label key per `queue_id`. Then `/gui-next-i18n`.

### 3.7 `tools/refresh_status.py`

`--queues` prints the four queues with counts, kind, state and blocked steps,
and exits. Same dry-run-from-a-terminal role `--chain` plays for Phase 3.

---

## 4. Files touched

| File | Change |
|---|---|
| `backend/queues.py` | **new** — `RefreshQueue`, `QUEUES`, `queue_counts`, `attention_by_step` |
| `backend/refresh.py` | `attention` per step, `queues` + `queue_pending_total` in the response, lazy import. No state-logic change |
| `backend/refresh_exec.py` | `advisories` in `plan_chain`. No execution change |
| `backend/app.py` | +1 route (`GET /api/refresh/queues`) |
| `gui_next/.../components/DataFreshnessCard.tsx` | queue panel, inline xref list, step attention markers, advisory list |
| `gui_next/.../components/AppShell.tsx`, `lib/navigation.ts` | queue-count badges |
| `gui_next/.../screens/ScreenLibrary.tsx` | read `?view=` |
| `gui_next/.../locales/en.json` | new keys (+ `/gui-next-i18n`) |
| `tests/test_queues.py` | **new** |
| `tests/test_refresh.py`, `tests/test_refresh_exec.py` | `attention` shape, advisories |
| `PROJECT.md`, `CHANGELOG.md`, `TODO.md` | reference sections + `/session-close` |

Build order: `queues.py` + `tools/refresh_status.py --queues` (fully testable,
ships no UI) → `refresh` field → `plan_chain` advisories → route → card panel →
xref inline list → nav badges.

The first commit is again the one worth landing alone: it is the half with the
SQL that has to be right, and it changes nothing a user sees.

---

## 5. Tests

**`tests/test_queues.py` (new).** Synthetic DB, no network.

- **Registry integrity**: every `blocks` entry is a real `refresh.STEPS`
  step_id; every `kind='backlog'` queue has a `total_sql`; every `kind='gate'`
  queue has `total_sql=None`; `queue_id`s are unique.
- **Counts**: each `count_sql` against a fixture with known rows returns the
  expected number; a decided taper conflict (row in `taper_confirmations`) drops
  out; a `dismissed` fingerprint suggestion drops out; suggestions are counted
  per LB, not per row (two rows, one LB → 1).
- **Missing table** → `state='unknown'`, `count=None`, and no exception.
- **`attention_by_step`** maps each queue onto every step in `blocks` and leaves
  unnamed steps absent from the dict.
- **`backlog` kind** never yields `state='pending'` and never contributes to
  `queue_pending_total`.

**`tests/test_refresh.py` (additions).** `compute_plan` step dicts all carry an
`attention` list; **no step's `state` differs** from the same fixture computed
with `queues` monkeypatched to raise — the regression test for decision 3, and
the reason this phase cannot quietly turn the card red.

**`tests/test_refresh_exec.py` (additions).** A non-empty gate queue produces an
advisory on a plan containing its blocked step, and `start` still returns
`started` (not 409) with that advisory present.

---

## 6. Verification

1. `.venv/bin/python3 -m pytest tests/test_queues.py tests/test_refresh.py tests/test_refresh_exec.py -v`, then the targeted backend suite.
2. `/backend-restart`.
3. `.venv/bin/python3 tools/refresh_status.py --queues` — reconcile against §1's table (129 / 242 / 3,057 / 0 as of 2026-08-16).
4. `curl localhost:5174/api/refresh/status | jq '.queue_pending_total, (.steps[] | select(.attention | length > 0) | .step_id)'` — total is gates only; attention lands on exactly the steps §3.1 names.
5. Confirm one taper conflict in the Library detail panel → the count drops by one on the next poll, and no step's `state` changes.
6. `POST /api/refresh/chain/preview {"trigger":"T3"}` — the fingerprint advisory appears; `start` still succeeds.
7. Stage an xref fileset (or fabricate one in a scratch DB) → the count appears with no Review affordance; grep the card for any call to `/api/xref_ingest/` and expect zero hits (decision 7).
8. `/gui-check` (mandatory), then `/verify` Tier A on Home and Library (the card grows a panel; the sidebar grows badges).
9. `/gui-next-i18n`.
10. `PROJECT.md`: routes section (+1), module reference (`queues`), GUI screens section (queue panel). `/wiki-update` on `Collection-Pipeline.md`.
11. `/session-close`.

---

## 7. Residual risks

- **Decision 2 is a judgment, not a measurement.** If tj actually intends to
  curate all 3,060 TapeMatch dates, `backlog` is the wrong kind and the panel
  under-reports the largest queue in the system. Changing it later is a one-line
  registry edit, which is why it is a registry field.
- **129 conflicts with no desktop queue screen.** The deep link goes to a Library
  *view*, which is a filtered list of performances — not a review workflow with a
  next-item button. This phase makes the number visible and the mobile queue page
  remains the only real workflow. If reviewing 129 rows through the Library view
  proves painful, that is a follow-up screen, not a Phase 4 expansion.
- **`xref_filesets` is a count with no resolution path** (decision 7). If it ever
  goes non-zero and stays there, the panel is showing debt the user cannot pay
  from inside the app. That is the honest state of it — `checksums` is Jeff's —
  but it is also the one queue whose badge could sit non-zero forever, so it is
  deliberately excluded from any nav badge and lives only in the panel.
- **Badge fatigue.** Three badges that never reach zero are worse than no badges.
  The gate queues are chosen to be drainable; if `fingerprint_suggestions` sits
  at 242 for months, the badge is lying about urgency in the same way the
  TapeMatch count would.
- **A fifth poller.** `AppShell` gains a 60 s `/api/refresh/queues` poll on top of
  activity, stats and the card's own. The route is four sub-millisecond counts,
  but it is one more thing running forever in the background of an idle app.

---

## 8. What Phase 4 deliberately does not do — and what stays open after it

Phase 4 closes inventory requirement 5 (D5) and, with it, the requirement list
that Phases 1–3 covered: 1 (D1/D8, Phase 2's `refresh_step_runs`), 2 (D2,
Phase 2), 3 (D3, Phases 1+3), 6 (D6/D7, Phase 1's card), 7 and 8 (respected
throughout).

**Left open when the four phases are done:**

- **Requirement 4 / D4 — nothing is incremental.** Every wholesale step still
  reprocesses the whole corpus; `ranker_scan`'s backlog mode remains the only
  counter-example. This is the largest remaining item in the inventory and it
  has no spec.
- **15 `manual` steps** (Phase 3 §3.1) are still unchained, each carrying its
  one-line reason.
- **Inventory open questions 1–3 and 5–6** are unanswered; question 4 is answered
  by decision 8 (advisory, not gate).
- **No scheduling.** Nothing in the four phases auto-starts anything; every run
  is still begun by a human, per inventory §5 requirement 8.
- **Taper conflict review has no dedicated desktop workflow** (§7).
