---
description: Refresh one page of the agentic wiki (docs/wiki/) from its sources — stalest page first, or a named page
---

# /wiki-update [PageName]

Regenerate **one** page of `docs/wiki/` per invocation (token budget discipline).

## Procedure

1. Read `docs/wiki/Home.md` (small). If `$ARGUMENTS` names a page, pick it.
   Otherwise pick the stalest page: oldest "Last updated" date, preferring pages
   whose sources have commits newer than that date
   (`git log --since=<date> --oneline -- <source paths>`).
2. Read the current page (small). Its `> Sources:` header lists authoritative
   sources. Gather updates **grep-first**: `grep -n` the source files for the
   relevant sections, then targeted Read with offset/limit. Never full-read
   PROJECT.md/BUGS.md/TODO.md.
3. Rewrite the page:
   - Keep the `> Sources: … · Status: fresh <today>` header format.
   - Prose overview + tables; link sibling pages relatively (`[GUI](GUI.md)`).
   - Wiki summarizes and orients — it must not duplicate PROJECT.md detail
     (route lists, full schemas). Point to the PROJECT.md section instead.
   - Keep each page under ~60 lines.
4. Update the page's row in `Home.md` (status `fresh`, today's date).
5. If a whole new area of the codebase has appeared, add a new page + Home row
   (same header format, status `seeded`).

## Rules

- One page per run unless the user explicitly asks for more.
- Facts must come from current sources, not memory — verify file paths exist.
- This is a docs change: it still goes through `/session-close` bookkeeping
  if part of a code session, but a wiki-only refresh needs no CHANGELOG entry.
