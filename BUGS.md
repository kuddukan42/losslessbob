BUG-383: Setup screen cards overflow the viewport below ~900px
Status: Open
File(s): gui_next/src/renderer/src/screens/ScreenSetup.tsx
Reported: 2026-10-20
Description: At 860px wide (sidebar forced icon-only) the 2-column card grid does not reflow: Master Data and the 3rd Integrations card are clipped at the right edge. Real Electron enforces a 1280x768 minimum window, so this only shows at high zoom / display scale. Not fixed in the sweep (needs a responsive grid decision).
Root cause: Unknown
Fix: —

BUG-375: Undefined CSS token var(--lbb-accent) renders uncoloured
Status: Open
File(s): gui_next/src/renderer/src/screens/ScreenFileIntegrity.tsx:135,gui_next/src/renderer/src/screens/ScreenDbEditor.tsx:565,gui_next/src/renderer/src/screens/ScreenDbEditor.tsx:656
Reported: 2026-10-18
Description: tokens.ts only defines --lbb-accent-{mid,soft,bg,line}; bare --lbb-accent is never set, so these 3 styles fall back to inherit/none (Known Tapers USER badge, recompute step colour, a File Integrity bar). Use --lbb-accent-mid. Found 2026-10-18 while linking /taper-curation.
Root cause: Unknown
Fix: —
