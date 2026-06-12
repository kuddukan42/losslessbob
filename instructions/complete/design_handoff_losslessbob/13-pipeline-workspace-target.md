# 13 · Pipeline Workspace — the visual target (read me first)

## The goal, stated plainly
When this work is done, the in-app **Pipeline Workspace** must look and behave **exactly like**
`_source/Pipeline Workspace (standalone).html`. That file is the **pixel-and-copy source of
truth.** Open it, click through every folder in the queue, and trigger every state — what you see
there is the spec. If the app differs from it, the app is wrong.

How to exercise every state in the standalone: each sample folder is wired to a different
situation — clean pass, no-checksums, shntool-missing, ambiguous LB#, not-found, wrong-LB,
reconcile-needed, extras-cleanup, mount-routing. Click each one in the left queue and step through
Verify → Lookup → Rename → LBDIR → Collect.

## Why the build fell short (so it doesn't happen again)
Three things compounded — none of them mean "start over":

1. **The wrong source shipped in the handoff.** The original bundle's `_source/` held the *old*
   batch-table `screen-pipeline.jsx`, and doc `06` pointed at it. The new Workspace
   (`pipeline2-*.jsx`) wasn't included. **Fixed:** all `pipeline2-*` files + this standalone are now
   in `_source/`, and `06` is marked superseded.
2. **The detail landed in the wrong place.** CC built genuinely rich **standalone** Verify / Lookup
   / LBDIR screens (they stay — they're the advanced power-tools), but the **pipeline's own stage
   panels** were left thin. The polish exists; it just isn't reused inside the Workspace.
3. **No state-level spec.** Handed raw JSX without a checklist, an agent builds the happy path and
   summarizes the branching states away.

## The plan (detail in docs 14 + 15)
- **Don't rebuild, harvest.** Lift the rich render bodies out of the standalone screens into shared
  `components/pipeline/*Detail.tsx` and render them in **both** the standalone screen and the
  pipeline panel. One source of truth per stage. (Doc 14 §1 — the harvest map.)
- **The data already exists.** `verifyStore`, `lookupStore`, `lbdirStore` already carry every
  table/picker/state the design needs, and the backend already sends it. (Doc 15.)
- **Only the Collect mount picker is new** — that's the `storage-mounts` feature, the one place
  new backend fields are required. (Doc 15.)
- **Match the copy exactly.** Every banner title, button label, tooltip, and status word is
  transcribed in doc 14 §3. The wording *is* the design.

## Reading order for whoever picks this up
1. **This doc** — the target + why.
2. **Open `_source/Pipeline Workspace (standalone).html`** — internalize the look and every state.
3. **`14-pipeline-gap-punchlist.md`** — the harvest map, per-stage gaps, exact copy, commit order.
4. **`15-data-contract.md`** — what data already exists vs. the new mount fields.
5. Source of truth as you build: `_source/pipeline2-stages.jsx` (every state) + `pipeline2-data.js`
   (fixtures) + `pipeline2-app.jsx` (how the shell/queue/gating compose).

`06-screen-pipeline.md` is **superseded** — background on the abandoned batch-table approach only.
