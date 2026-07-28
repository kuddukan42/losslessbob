// Parsers for the real on-disk documents. No schema change, no re-crawl —
// everything below is read out of the text that tapematch_session.py / gen_analysis.py
// already write. If a field isn't here, the files don't carry it.
window.TMParse = (() => {
  const ent = (s) => s.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  const strong = (s) => s.replace(/\*\*(.+?)\*\*/g, "$1").replace(/\*(.+?)\*/g, "$1");
  const cells = (line) => line.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  const isRule = (line) => /^\|[\s:|-]+\|$/.test(line);

  // A5 + B2 — tone from the real headline vocabulary. Ordered; first match wins.
  const TONE_RULES = [
    [/\bMISS\b/, "bad"],
    // B2 — the conflict vocabulary the corpus actually uses. Same tier as MISS.
    [/contradicted|contradicts|\bdisagrees?\b|conflicts with/i, "bad"],
    [/\bINCOMPLETE\b/i, "warn"],
    [/speed offset/i, "warn"],
    [/\bLOW CONFIDENCE\b/i, "warn"],
    // B2 — reliability caveats are a review flag, not a contradiction.
    [/mismatch|unreliable|uncorroborated|coincidence|inflated|needs review/i, "warn"],
    // A3's gap language, so a title-only coverage note keys the same way as the table
    [/coverage gap|not found on disk|no tapematch comparison/i, "warn"],
  ];
  // B2 — tone never keys on quoted commentary. Scraped LB text carries words like
  // DISAGREES out of a table it was swept up from; only the generator's own prose counts.
  const unquoted = (s) => (s || "").replace(/"[^"]*"/g, " ").replace(/[“][^”]*[”]/g, " ");
  const tone = (head) => (TONE_RULES.find(([re]) => re.test(unquoted(head))) || [, "info"])[1];
  // the tone bar carries the alarm; the source's own ⚠️ is stripped on render (A5)
  const cleanHead = (h) => h.replace(/\s*[⚠️❗️!]+\uFE0F?\s*$/u, "").trim();

  // ── B1 — what a `###` heading's left side actually is ───────────────────────
  // 21% of real cards are not `<ref> — <headline>`. Three subject kinds, and the
  // shape of the card follows the subject, not the presence of an em-dash.
  const REF_RE = /^LB-\d{3,}(?:\s*(?:\/|→|×|x|vs\.?|,|\+|and)\s*LB-\d{3,})*(?:\s*\([^)]*\))?$/i;
  const FAM_RE = /^Family\s+(\d+)$/i;
  function subject(left) {
    const s = left.trim();
    if (REF_RE.test(s)) return { kind: "ref", ref: s, refs: s.match(/LB-\d{3,}/gi) || [] };
    const f = s.match(FAM_RE);
    if (f) return { kind: "family", ref: s, fam: +f[1], refs: [] };
    return null;
  }
  // B1 — a heading with a subject is a card; a heading with none is a statement block.
  function card(heading) {
    const h = heading.trim();
    const split = h.match(/^(.+?)\s+—\s+(.+)$/);
    const subj = subject(split ? split[1] : h);
    if (subj) {
      const head = split ? cleanHead(split[2]) : "";
      return Object.assign({ kind: subj.kind, head, headRaw: split ? split[2].trim() : "", lines: [] }, subj,
        // no headline → the finding is in the body, so the body decides the tone
        { tone: head ? tone(split[2]) : "body" });
    }
    return { kind: "statement", title: split ? split[1].trim() : h, lead: split ? cleanHead(split[2]) : "", ref: "", refs: [], lines: [], tone: tone(h) };
  }

  function parseReport(md) {
    const lines = md.split("\n");
    const doc = { title: "", date: "", loc: "", generated: "", coverage: { entries: null, found: null, cols: [], rows: [] }, ascii: [], commentary: [], audit: null };
    let i = 0;
    for (; i < lines.length; i++) {
      const l = lines[i];
      let m;
      if ((m = l.match(/^# tapematch session — (\S+) — (.+)$/))) { doc.date = m[1]; doc.loc = m[2]; doc.title = l.slice(2); continue; }
      if ((m = l.match(/^\*Generated: (.+)\*$/))) { doc.generated = m[1]; continue; }
      if (l.startsWith("## ")) break;
    }
    while (i < lines.length) {
      const head = lines[i].slice(3).trim(); i++;
      const body = [];
      while (i < lines.length && !lines[i].startsWith("## ")) body.push(lines[i++]);
      const key = head.toLowerCase();
      if (key === "coverage") {
        const sum = body.find((l) => /DB entries:/.test(l));
        if (sum) {
          const e = sum.match(/DB entries:\s*\*\*(\d+)\*\*/), f = sum.match(/Found on disk:\s*\*\*(\d+)\*\*/);
          doc.coverage.entries = e ? +e[1] : null; doc.coverage.found = f ? +f[1] : null;
        }
        const tbl = body.filter((l) => l.trim().startsWith("|"));
        if (tbl.length) {
          doc.coverage.cols = cells(tbl[0]);
          doc.coverage.rows = tbl.slice(1).filter((l) => !isRule(l)).map((l) => {
            const c = cells(l).map(ent);
            const row = { lb: c[0], onDisk: c[1], rating: c[2], timing: c[3], src: c[4], folder: c[5] };
            row.missing = /not found/i.test(row.folder || "") || row.onDisk === "—" || row.onDisk === "-";
            if (row.missing) row.folder = "";
            return row;
          });
        }
      } else if (key === "tapematch output") {
        const inner = body.join("\n").replace(/^\s*```[a-z]*\n?/, "").replace(/```\s*$/, "").replace(/\n+$/, "");
        // A1 — split on the generator's own === SECTION === markers
        const parts = inner.split(/^=== (.+?) ===$/m);
        if (parts[0].trim()) doc.ascii.push({ label: "preamble", lines: parts[0].replace(/\n+$/, "").split("\n") });
        for (let k = 1; k < parts.length; k += 2) {
          const bodyLines = (parts[k + 1] || "").replace(/^\n+|\n+$/g, "").split("\n");
          doc.ascii.push({ label: parts[k].trim(), lines: bodyLines });
        }
        doc.ascii.forEach((b) => {
          b.wide = Math.max(...b.lines.map((l) => l.length));
          b.content = b.lines.filter((l) => l.trim());
          b.single = b.content.length === 1 && b.wide <= 90;
        });
      } else if (key === "lb page commentary") {
        let cur = null;
        body.forEach((l) => {
          const m = l.match(/^### (.+)$/);
          if (m) {
            const bits = m[1].split("|").map((s) => s.trim());
            cur = { lb: bits[0], meta: bits.slice(1).map((b) => b.replace(/^(rating|timing):\s*/, "")).filter(Boolean), metaRaw: bits.slice(1), body: "" };
            doc.commentary.push(cur);
          } else if (cur && l.trim()) cur.body += (cur.body ? " " : "") + ent(l.trim());
        });
      } else if (/^commentary vs tapematch audit/i.test(key)) {
        const tbl = body.filter((l) => l.trim().startsWith("|"));
        if (tbl.length) doc.audit = {
          cols: cells(tbl[0]),
          rows: tbl.slice(1).filter((l) => !isRule(l)).map((l) => {
            const c = cells(l).map(ent);
            return { pair: c[0], verdict: strong(c[1]), disagrees: /DISAGREES/i.test(c[1]), snippet: c[2] };
          }),
        };
      }
    }
    return doc;
  }

  function parseAnalysis(md) {
    const lines = md.split("\n");
    const doc = { date: "", loc: "", model: "", verdict: "", cols: [], rows: [], notOnDisk: [], cards: [], epilogue: [], algoNote: "" };
    let i = 0, m;
    for (; i < lines.length; i++) {
      const l = lines[i];
      if ((m = l.match(/^# Analysis — (\S+) — (.+)$/))) { doc.date = m[1]; doc.loc = m[2]; continue; }
      if ((m = l.match(/^\*(.+?) — (.+?)\*$/))) { doc.model = m[1]; doc.ran = m[2]; continue; }
      if (l.startsWith("## ")) break;
    }
    let section = "";
    for (; i < lines.length; i++) {
      const l = lines[i], t = l.trim();
      if ((m = l.match(/^## Verdict:\s*(.+)$/))) { doc.verdict = m[1].trim(); section = "verdict"; continue; }
      if ((m = l.match(/^## (.+)$/))) { section = /algorithm/i.test(m[1]) ? "algo" : "other"; continue; }
      if ((m = l.match(/^### (.+)$/))) { doc.cards.push(card(m[1])); section = "card"; continue; }
      if (!t) continue;
      if (t.startsWith("|")) { if (isRule(t)) continue; const c = cells(t).map(ent); if (!doc.cols.length) doc.cols = c; else doc.rows.push({ lb: c[0], rating: c[1], timing: c[2], src: c[3], fam: c[4], notes: c[5] }); continue; }
      if ((m = t.match(/^Not on disk:\s*(.+)$/))) { doc.notOnDisk = m[1].split(/,\s*/); continue; }
      if (section === "card") { doc.cards[doc.cards.length - 1].lines.push(ent(t)); continue; }
      if (section === "algo") { doc.algoNote += (doc.algoNote ? " " : "") + ent(t); continue; }
      doc.epilogue.push(ent(t));
    }
    doc.cards.forEach(finishCard);
    return doc;
  }

  // Body shape. Lines the generator writes as `label: value` become a key/value row —
  // that is where the finding lives on a ref-only card, and the differing half of an
  // 11-card stack is the value, not the key. Bullets stay bullets. Everything else is prose.
  const KV_RE = /^([A-Za-z][A-Za-z0-9 .]{0,26}):\s*(.+)$/;
  function finishCard(c) {
    const blocks = [];
    (c.lines || []).forEach((ln) => {
      const b = blocks[blocks.length - 1];
      let m;
      if (/^[-*]\s+/.test(ln)) {
        const item = ln.replace(/^[-*]\s+/, "");
        if (b && b.kind === "ul") b.items.push(item); else blocks.push({ kind: "ul", items: [item] });
      } else if (!c.head && (m = ln.match(KV_RE))) {
        blocks.push({ kind: "kv", k: m[1], v: m[2], quote: /^["“]/.test(m[2]) });
      } else if (b && b.kind === "p") b.text += " " + ln;
      else blocks.push({ kind: "p", text: ln });
    });
    c.blocks = blocks;
    c.body = blocks.filter((b) => b.kind === "p").map((b) => b.text).join(" ");
    if (c.tone === "body") {
      // only the generator's own lines vote — a kv value is quoted LB commentary
      const own = blocks.map((b) => (b.kind === "kv" ? (b.quote ? "" : b.v) : b.kind === "p" ? b.text : b.items.join(" "))).join(" ");
      c.tone = tone(own);
    }
    return c;
  }

  return { parseReport, parseAnalysis, tone, cleanHead, ent, card, subject, finishCard, TONE_RULES };
})();
