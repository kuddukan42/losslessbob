/* ============================================================
   PipelineIcon — production React component
   LosslessBob pipeline stage icons (Option D · Pulse · Vivid)

   Requires pipeline-icons.css on the page.

   Usage:
     <PipelineIcon stage="verify" status="running" size={48} />

   stage:  "verify" | "lookup" | "rename" | "lbdir" | "collect"
   status: "pending" | "running" | "pass" | "action" | "blocked"
   size:   px (default 48). Glyph scales to ~0.56 of tile.
   ============================================================ */

// ── Glyph geometry (24×24 viewBox, 1.85 stroke) ────────────
const PIPE_GLYPHS = {
  verify: (
    <>
      <path d="M12 3.1l7.4 2.6v5.1c0 4.8-3.2 7.9-7.4 9.4-4.2-1.5-7.4-4.6-7.4-9.4V5.7L12 3.1z" />
      <path d="M8.5 12.0l2.4 2.4 4.6-5.0" />
    </>
  ),
  lookup: (
    <>
      <circle cx="10.4" cy="10.4" r="6.3" />
      <path d="M15.0 15.0l4.8 4.8" />
      <path d="M7.9 8.9h5.0" />
      <path d="M7.9 10.7h5.0" />
      <path d="M7.9 12.5h3.0" />
    </>
  ),
  rename: (
    <>
      <path d="M3.8 12.7l8.2-8.2a2 2 0 0 1 1.43-.6h4.95a1.6 1.6 0 0 1 1.6 1.6v4.95a2 2 0 0 1-.6 1.43l-8.2 8.2a2 2 0 0 1-2.83 0l-4.55-4.55a2 2 0 0 1 0-2.83z" />
      <circle cx="16.4" cy="7.6" r="1.3" />
    </>
  ),
  lbdir: (
    <>
      <path d="M6.6 3.2h6.4l5.4 5.4v10.6a1.6 1.6 0 0 1-1.6 1.6H6.6a1.6 1.6 0 0 1-1.6-1.6V4.8a1.6 1.6 0 0 1 1.6-1.6z" />
      <path d="M13 3.4v5.2h5" />
      <path d="M8.7 13.0h6.6" />
      <path d="M8.7 15.8h6.6" />
    </>
  ),
  collect: (
    <>
      <path d="M3.7 6.7h16.6v3.3H3.7z" />
      <path d="M5.1 10.0v8.5a1.6 1.6 0 0 0 1.6 1.6h10.6a1.6 1.6 0 0 0 1.6-1.6V10.0" />
      <path d="M9.9 13.2h4.2" />
    </>
  ),
};

function PipelineGlyph({ stage, size = 27 }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none"
         stroke="currentColor" strokeWidth="1.85"
         strokeLinecap="round" strokeLinejoin="round">
      {PIPE_GLYPHS[stage]}
    </svg>
  );
}

function PipelineIcon({ stage, status = "pending", size = 48 }) {
  const glyphSize = Math.round(size * 0.56);
  const isRunning = status === "running";
  return (
    <span
      className={`pipe-tile pipe-tile--${status}`}
      style={{ "--pipe-size": `${size}px` }}
    >
      {isRunning && (
        <>
          <span className="pipe-tile__ring" />
          <span className="pipe-tile__ring pipe-tile__ring--b" />
          <span className="pipe-tile__sheen-clip">
            <span className="pipe-tile__sheen" />
          </span>
        </>
      )}
      <span className="pipe-tile__glyph">
        <PipelineGlyph stage={stage} size={glyphSize} />
      </span>
    </span>
  );
}

// Stage metadata (labels + canonical order)
const PIPELINE_STAGES = [
  { key: "verify",  label: "Verify" },
  { key: "lookup",  label: "Lookup" },
  { key: "rename",  label: "Rename" },
  { key: "lbdir",   label: "LBDIR" },
  { key: "collect", label: "Collect" },
];

// export { PipelineIcon, PipelineGlyph, PIPELINE_STAGES };
