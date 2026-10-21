BUG-383: Setup screen cards overflow the viewport below ~900px
Status: Open
File(s): gui_next/src/renderer/src/screens/ScreenSetup.tsx
Reported: 2026-10-20
Description: At 860px wide (sidebar forced icon-only) the 2-column card grid does not reflow: Master Data and the 3rd Integrations card are clipped at the right edge. Real Electron enforces a 1280x768 minimum window, so this only shows at high zoom / display scale. Not fixed in the sweep (needs a responsive grid decision).
Root cause: Unknown
Fix: —
