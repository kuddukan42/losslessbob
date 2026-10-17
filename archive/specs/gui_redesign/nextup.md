Read PROJECT.md, BUGS.md, TODO.md.

We're on branch feat/gui-redesign implementing the gui_next Electron/React app.
Phases done: 0,1,2,3,4a,4b,4c. Next target: Phase 4d (Search screen).

Read instructions/gui_redesign/08-screen-search.md in full.

Then implement Phase 4d:
1. Create gui_next/src/renderer/src/screens/ScreenSearch.tsx
2. Use the design spec from 08-screen-search.md
3. Follow the same patterns as ScreenCollection/ScreenPipeline:
   - useVirtualizer for the results table
   - useEffect + fetch against localhost:5174 with SAMPLE_DATA fallback
   - Primitives from components/ (TableShell/TH/TR/TD, Button, Chip, Input, Pill, etc.)
4. Register route in App.tsx: replace PlaceholderScreen at /search with ScreenSearch

Use our primitives from gui_next/src/renderer/src/components/. Match the design spec exactly.
Ask before adding new dependencies.
