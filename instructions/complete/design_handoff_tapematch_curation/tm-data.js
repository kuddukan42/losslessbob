// TapeMatch curation — demo data modeled on DATA_PRODUCED.md
window.TM = (() => {
  const FAM = { 1:"oklch(0.66 0.10 35)", 2:"oklch(0.62 0.09 240)", 3:"oklch(0.64 0.10 145)", 4:"oklch(0.68 0.10 75)", 5:"oklch(0.60 0.09 320)" };
  // featured date: 2001-11-19 MSG — 10 recordings, 5 families, 1 LB conflict
  const REC = [
    { lb:"LB-11201", fam:1, ref:true, ppm:0, kind:"reference", conf:9.8, rating:"A",  dur:"1:52:10", src:"Schoeps CCM4 (DFC) > SBM-1 > DAT master · taper crimson" },
    { lb:"LB-11458", fam:1, ppm:38,     kind:"aligned",   conf:9.1, rating:"A",  dur:"1:52:07", src:"Same DAT lineage, later clone > CDR > EAC > FLAC" },
    { lb:"LB-13022", fam:1, ppm:-1480,  kind:"staircase", conf:6.4, rating:"A-", dur:"1:51:44", src:"CDR trade copy; re-tracked, disc change gap repaired" },
    { lb:"LB-11890", fam:2, ppm:-25,    kind:"aligned",   conf:7.2, rating:"B+", dur:"1:49:58", src:"AKG 460 > D7 DAT; remaster w/ EQ + light NR (2013)" },
    { lb:"LB-12704", fam:2, ppm:-31,    kind:"aligned",   conf:7.0, rating:"B+", dur:"1:50:02", src:"Same AKG source, unremastered transfer, hiss intact" },
    { lb:"LB-11340", fam:3, ppm:-1512,  kind:"constant-speed-offset", conf:8.8, rating:"A-", dur:"1:51:30", src:"Neumann km140 > DAT; FOB section 12" },
    { lb:"LB-11977", fam:3, ppm:-1508,  kind:"constant-speed-offset", conf:8.5, rating:"A-", dur:"1:51:36", src:"km140 clone > standalone CD burner > EAC" },
    { lb:"LB-12455", fam:4, ppm:12480,  kind:"speed-unknown", conf:2.1, rating:"C",  dur:"1:47:12", src:"Unknown lineage; PAL/NTSC transfer-speed error suspected" },
    { lb:"LB-14210", fam:5, ppm:-1495,  kind:"constant-speed-offset", conf:8.0, rating:"B+", dur:"1:50:48", src:"Core Sound binaurals > MD > optical > CDR" },
    { lb:"LB-14567", fam:5, ppm:-1490,  kind:"splice",    conf:5.9, rating:"B",  dur:"1:48:20", src:"MD source, tape flip splice at 61:20; encore patched" },
  ];
  // pair overrides — key "shortA|shortB" sorted ascending
  const OV = {
    "11201|11458": { corr:0.94, win:0.98, hiss:0.92, fp:0.71, sim:99, same:true,  lbSays:1, lbText:"“clone of the crimson DAT master” — LB-11458 page" },
    "11201|13022": { corr:0.52, win:0.74, hiss:0.61, fp:0.55, sim:91, same:true,  lbSays:1, lbText:"“same recording, CDR generation with re-tracked indices”" },
    "11458|13022": { corr:0.49, win:0.70, hiss:0.58, fp:0.53, sim:89, same:true,  lbSays:1, lbText:"—" },
    "11890|12704": { corr:0.21, win:0.83, hiss:0.71, fp:0.44, sim:87, same:true, secondary:true, lbSays:1, lbText:"“remaster of the AKG source (see LB-12704)” — LB-11890 page" },
    "11340|11977": { corr:0.88, win:0.95, hiss:0.84, fp:0.66, sim:98, same:true,  lbSays:1, lbText:"“km140 clone, EAC transfer of the same tape”" },
    "14210|14567": { corr:0.61, win:0.79, hiss:0.44, fp:0.51, sim:93, same:true,  lbSays:1, lbText:"“both from taper olof's MD master”" },
    // the conflict: LB page claims same, algorithm says different
    "11201|11340": { corr:0.041, win:0.12, hiss:0.08, fp:0.38, sim:22, same:false, conflict:true, lbSays:1,
      lbText:"“probably the same recording as LB-11201, different transfer” — LB-11340 page. TapeMatch: near-zero residual correlation after alignment; windowed coverage 12%. Distinct microphones (DFC vs FOB) is the likely explanation." },
  };
  const h = (s) => { let x = 0; for (const c of s) x = (x * 31 + c.charCodeAt(0)) % 997; return x / 997; };
  const short = (lb) => lb.replace("LB-", "");
  function pair(a, b) {
    const A = REC.find(r=>r.lb===a), B = REC.find(r=>r.lb===b);
    const k = [short(a), short(b)].sort((x,y)=>+x-+y).join("|");
    if (OV[k]) return { key:k, ...OV[k] };
    if (A.kind === "speed-unknown" || B.kind === "speed-unknown")
      return { key:k, corr:null, win:null, hiss:null, fp:0.14 + h(k)*0.1, sim:null, same:false, nc:true, lbSays:null, lbText:null };
    const r = h(k);
    return { key:k, corr:0.004+r*0.04, win:0.02+r*0.08, hiss:0.03+r*0.09, fp:0.16+r*0.22, sim:Math.round(6+r*22), same:false, lbSays:null, lbText:null };
  }
  const DATE = { date:"2001-11-19", loc:"New York, NY", venue:"Madison Square Garden", run:"20260602_211540",
    verdict:"5 families from 10 recordings — 1 conflict with LB commentary", tone:"warn", model:"claude-sonnet-4-6", ran:"2026-06-03" };
  const NOTES = [
    { ref:"LB-11201 × LB-11340", tone:"bad", head:"Conflict — LB page claims same source, algorithm disagrees",
      body:"LB-11340's page says “probably the same recording as LB-11201.” Residual correlation is 0.041 with 12% windowed coverage — no acoustic evidence of a shared tape. DFC vs FOB mic placement would explain the LB confusion. Recommend human judgment; if confirmed different, set lb_wrong." },
    { ref:"Family 2 · LB-11890 + LB-12704", tone:"info", head:"Secondary-linked family — low primary correlation is expected",
      body:"Primary corr 0.21 sits below the 0.45 threshold because the 2013 remaster EQ'd the music. Windowed coverage 83% and quiet-hiss correlation 71% both indicate the same underlying tape. [low confidence] tag is normal here, not a defect." },
    { ref:"LB-12455", tone:"warn", head:"Speed-unknown — routed to fingerprint path only",
      body:"+12,480 ppm offset with ratio confidence 2.1 (< 6.0 minimum). Correlation not comparable — shown as n/c, not 0%. Likely a PAL/NTSC playback-speed error on an already-poor transfer." },
    { ref:"LB-13022", tone:"info", head:"Staircase lag curve — CDR re-tracking",
      body:"Discontinuous lag pattern from re-tracked disc indices. Windowed coverage (74%) carried the merge into Family 1; the LB page corroborates the CDR-generation claim." },
  ];
  const QUEUE = [
    { date:"2001-11-19", loc:"New York, NY",   recs:10, fams:5, status:"conflict", featured:true },
    { date:"2001-11-20", loc:"New York, NY",   recs:4,  fams:4, status:"review" },
    { date:"2022-06-11", loc:"Oakland, CA",    recs:4,  fams:3, status:"clean" },
    { date:"2001-11-17", loc:"Philadelphia, PA", recs:6, fams:4, status:"conflict" },
    { date:"2001-11-15", loc:"Washington, DC", recs:3,  fams:3, status:"clean" },
    { date:"2001-11-13", loc:"Charlottesville, VA", recs:3, fams:2, status:"curated" },
    { date:"2001-11-11", loc:"Atlantic City, NJ", recs:4, fams:4, status:"curated" },
    { date:"2001-11-09", loc:"Boston, MA",     recs:4,  fams:3, status:"clean" },
    { date:"2001-11-08", loc:"Boston, MA",     recs:4,  fams:4, status:"curated" },
    { date:"2001-11-06", loc:"Rochester, NY",  recs:3,  fams:3, status:"clean" },
    { date:"2001-11-04", loc:"Buffalo, NY",    recs:3,  fams:3, status:"curated" },
    { date:"2001-11-02", loc:"University Park, PA", recs:2, fams:2, status:"curated" },
  ];
  const STATUS = {
    conflict: { label:"conflict", tone:"bad" },
    review:   { label:"review",   tone:"warn" },
    clean:    { label:"clean",    tone:"ok" },
    curated:  { label:"curated",  tone:"mute" },
  };
  return { FAM, REC, DATE, NOTES, QUEUE, STATUS, pair, short, THRESH:{ corr:0.45, win:0.60, fpLo:0.15, fpHi:0.50 } };
})();
