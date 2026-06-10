// pipeline2-confirm.jsx
// A reusable confirmation gate for destructive / disk-mutating actions in the
// Pipeline Workspace. Promise-based: call `const ok = await confirm({...})`
// and branch on the result. Two tones:
//   danger — irreversible (e.g. clearing the queue). Red, requires intent.
//   warn   — reversible-but-writes-to-disk (e.g. moving files). Amber, lighter.
//
// Usage:
//   const [confirm, ConfirmHost] = window.LBB_P2_useConfirm();
//   ... render <ConfirmHost /> once near the root ...
//   if (await confirm({ tone:"danger", title, body, confirmLabel })) { doit(); }

(() => {
  const Icon = window.LBB_Icon;
  const { Button } = window;

  const TONE = {
    danger: { accent: "bad",  icon: "trash", confirmVariant: "danger" },
    warn:   { accent: "warn", icon: "folder", confirmVariant: "primary" },
    info:   { accent: "info", icon: "info",  confirmVariant: "primary" },
  };

  function ConfirmDialog({ open, opts, onResolve }) {
    const cardRef = React.useRef(null);

    React.useEffect(() => {
      if (!open) return;
      const t = setTimeout(() => {
        const btn = cardRef.current && cardRef.current.querySelector("[data-confirm-btn]");
        if (btn) btn.focus();
      }, 30);
      const onKey = (e) => {
        if (e.key === "Escape") { e.preventDefault(); onResolve(false); }
        if (e.key === "Enter")  { e.preventDefault(); onResolve(true); }
      };
      window.addEventListener("keydown", onKey, true);
      return () => { clearTimeout(t); window.removeEventListener("keydown", onKey, true); };
    }, [open, onResolve]);

    if (!open) return null;
    const o = opts || {};
    const tone = TONE[o.tone] || TONE.danger;
    const accent = tone.accent;

    return (
      <div
        onMouseDown={(e) => { if (e.target === e.currentTarget) onResolve(false); }}
        style={{
          position: "absolute", inset: 0, zIndex: 200,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "color-mix(in oklab, var(--lbb-fg) 38%, transparent)",
          backdropFilter: "blur(1.5px)",
          animation: "p2cfade 120ms ease-out",
        }}>
        <div ref={cardRef} role="alertdialog" aria-modal="true" style={{
          width: 432, maxWidth: "calc(100% - 48px)",
          background: "var(--lbb-bg)", borderRadius: 12,
          border: "1px solid var(--lbb-border)",
          boxShadow: "var(--lbb-shadowLg, 0 24px 60px rgba(0,0,0,0.35))",
          overflow: "hidden",
          animation: "p2cpop 140ms cubic-bezier(.2,.8,.2,1)",
        }}>
          {/* Header */}
          <div style={{ display: "flex", gap: 14, padding: "18px 20px 14px" }}>
            <div style={{
              width: 38, height: 38, borderRadius: 10, flex: "0 0 38px",
              background: `var(--lbb-${accent}-bg)`, color: `var(--lbb-${accent}-fg)`,
              border: `1px solid var(--lbb-${accent}-bar)`,
              display: "inline-flex", alignItems: "center", justifyContent: "center",
            }}>
              <Icon name={o.icon || tone.icon} size={19} />
            </div>
            <div style={{ flex: 1, minWidth: 0, paddingTop: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: -0.01, color: "var(--lbb-fg)" }}>{o.title}</div>
              {o.body && <div style={{ fontSize: 12.5, color: "var(--lbb-fg2)", lineHeight: 1.5, marginTop: 5 }}>{o.body}</div>}
            </div>
          </div>

          {/* Optional detail / preview list */}
          {o.items && o.items.length > 0 && (
            <div style={{ margin: "0 20px 4px", border: "1px solid var(--lbb-border)", borderRadius: 8, overflow: "hidden" }}>
              {o.items.slice(0, 4).map((it, i) => (
                <div key={i} style={{
                  display: "flex", alignItems: "center", gap: 9, padding: "7px 11px",
                  borderBottom: i < Math.min(o.items.length, 4) - 1 ? "1px solid var(--lbb-border)" : "none",
                  background: i % 2 ? "var(--lbb-surface)" : "var(--lbb-surface2)",
                }}>
                  <Icon name={it.icon || "folder"} size={12} style={{ color: "var(--lbb-fg3)", flex: "0 0 auto" }} />
                  <span style={{ flex: 1, fontFamily: "var(--lbb-mono)", fontSize: 11, color: "var(--lbb-fg)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{it.label}</span>
                  {it.meta && <span style={{ fontFamily: "var(--lbb-mono)", fontSize: 10.5, color: "var(--lbb-fg3)" }}>{it.meta}</span>}
                </div>
              ))}
              {o.items.length > 4 && (
                <div style={{ padding: "5px 11px", fontSize: 10.5, color: "var(--lbb-fg3)", textAlign: "center", fontStyle: "italic", background: "var(--lbb-surface2)", borderTop: "1px solid var(--lbb-border)" }}>
                  + {o.items.length - 4} more
                </div>
              )}
            </div>
          )}

          {/* Reassurance / consequence line */}
          {o.note && (
            <div style={{ display: "flex", alignItems: "flex-start", gap: 8, margin: "10px 20px 0", padding: "9px 11px", borderRadius: 7, background: `var(--lbb-${accent}-bg)`, border: `1px solid var(--lbb-${accent}-bar)` }}>
              <Icon name={o.tone === "danger" ? "alert" : "info"} size={13} style={{ color: `var(--lbb-${accent}-fg)`, marginTop: 1, flex: "0 0 auto" }} />
              <span style={{ fontSize: 11.5, color: "var(--lbb-fg2)", lineHeight: 1.45 }}>{o.note}</span>
            </div>
          )}

          {/* Footer actions */}
          <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "16px 20px 18px", marginTop: 6 }}>
            <div style={{ flex: 1 }} />
            <Button variant="ghost" size="md" onClick={() => onResolve(false)}>{o.cancelLabel || "Cancel"}</Button>
            <Button data-confirm-btn variant={o.confirmVariant || tone.confirmVariant} size="md" icon={o.confirmIcon || (o.tone === "danger" ? "trash" : "check")} onClick={() => onResolve(true)}>
              {o.confirmLabel || "Confirm"}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Hook: returns [confirm(opts) -> Promise<bool>, <ConfirmHost/>]
  function useConfirm() {
    const [state, setState] = React.useState({ open: false, opts: null });
    const resolver = React.useRef(null);

    const confirm = React.useCallback((opts) => new Promise((resolve) => {
      resolver.current = resolve;
      setState({ open: true, opts });
    }), []);

    const onResolve = React.useCallback((v) => {
      setState({ open: false, opts: null });
      if (resolver.current) { resolver.current(v); resolver.current = null; }
    }, []);

    const Host = React.useCallback(() => (
      <ConfirmDialog open={state.open} opts={state.opts} onResolve={onResolve} />
    ), [state.open, state.opts, onResolve]);

    return [confirm, Host];
  }

  window.LBB_P2_useConfirm = useConfirm;
  window.LBB_P2_ConfirmDialog = ConfirmDialog;
})();
