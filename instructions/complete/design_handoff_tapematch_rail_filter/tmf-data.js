// Add-on demo data: a realistic ~2,075-date queue for the TapeMatch rail.
// In production this array is the real crawl index; nothing here is part of the add-on UI.
window.TMF_DATA = (() => {
  function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}}
  const r = mulberry32(20011119);
  const PLACES = [
    ["New York, NY"],["Boston, MA"],["Philadelphia, PA"],["Washington, DC"],["Chicago, IL"],["Minneapolis, MN"],["Denver, CO"],["Berkeley, CA"],["Oakland, CA"],["Los Angeles, CA"],["San Francisco, CA"],["Seattle, WA"],["Portland, OR"],["Austin, TX"],["Dallas, TX"],["Atlanta, GA"],["Nashville, TN"],["Memphis, TN"],["New Orleans, LA"],["Miami, FL"],["Toronto, ON"],["Montreal, QC"],["Vancouver, BC"],["London, UK"],["Manchester, UK"],["Glasgow, UK"],["Dublin, IE"],["Paris, FR"],["Amsterdam, NL"],["Berlin, DE"],["Hamburg, DE"],["Munich, DE"],["Zurich, CH"],["Milan, IT"],["Rome, IT"],["Barcelona, ES"],["Madrid, ES"],["Stockholm, SE"],["Oslo, NO"],["Copenhagen, DK"],["Helsinki, FI"],["Vienna, AT"],["Prague, CZ"],["Warsaw, PL"],["Tokyo, JP"],["Osaka, JP"],["Sydney, AU"],["Melbourne, AU"],["Auckland, NZ"],["Tel Aviv, IL"],["Buffalo, NY"],["Rochester, NY"],["Pittsburgh, PA"],["Cleveland, OH"],["Columbus, OH"],["Detroit, MI"],["Milwaukee, WI"],["St. Louis, MO"],["Kansas City, MO"],["Phoenix, AZ"],["Albuquerque, NM"],["Salt Lake City, UT"],["Boise, ID"],["Charlottesville, VA"],["Asheville, NC"],["Athens, GA"],["Ann Arbor, MI"],["Madison, WI"],["University Park, PA"],["Atlantic City, NJ"],["Canberra, AU"],["Sheffield, UK"],["Liverpool, UK"],["Bristol, UK"],["Gothenburg, SE"],["Lyon, FR"],["Bologna, IT"],["Seville, ES"],["Bergen, NO"],["Lisbon, PT"],
  ];
  // Rough shape of a career's worth of touring — light 60s, heavy from '88 on.
  const COUNTS = {
    1961:3,1962:9,1963:14,1964:22,1965:41,1966:44,1969:2,1970:1,1971:2,1974:40,1975:31,1976:34,
    1978:114,1979:33,1980:44,1981:54,1984:28,1985:6,1986:59,1987:38,
    1988:71,1989:99,1990:93,1991:101,1992:92,1993:80,1994:104,1995:116,1996:86,1997:94,1998:110,1999:120,
    2000:112,2001:106,2002:107,2003:97,2004:112,2005:104,2006:100,2007:97,2008:99,2009:97,2010:101,
    2011:87,2012:73,2013:75,2014:80,2015:87,2016:78,2017:83,2018:84,2019:76,2021:35,2022:73,2023:66,2024:70,
  };
  const STATUSES = ["conflict","review","clean","curated"];
  const TARGET = 2075;
  const SCALE = TARGET / Object.values(COUNTS).reduce((a, b) => a + b, 0);
  const out = [];
  const seen = new Set();
  Object.keys(COUNTS).forEach((ys) => {
    const y = +ys, n = Math.max(1, Math.round(COUNTS[ys] * SCALE));
    for (let i = 0; i < n; i++) {
      let date, guard = 0;
      do {
        const m = 1 + Math.floor(r() * 12), day = 1 + Math.floor(r() * 28);
        date = `${y}-${String(m).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
      } while (seen.has(date) && guard++ < 40);
      seen.add(date);
      const p = r();
      // older/rarer tapes skew messier; recent years are mostly clean or already curated
      const messy = y < 1980 ? 0.34 : y < 1996 ? 0.22 : 0.13;
      const status = p < messy * 0.45 ? "conflict" : p < messy ? "review" : p < messy + (1 - messy) * 0.55 ? "clean" : "curated";
      const recs = 1 + Math.floor(r() * (y < 1980 ? 12 : 7));
      const fams = Math.max(1, Math.min(recs, Math.round(recs * (0.45 + r() * 0.5))));
      out.push({ date, loc: PLACES[Math.floor(r() * PLACES.length)][0], recs, fams, status });
    }
  });
  // splice in the real featured date so the add-on and the live screen agree
  const idx = out.findIndex((d) => d.date === "2001-11-19");
  const featured = { date:"2001-11-19", loc:"New York, NY", recs:10, fams:5, status:"conflict", featured:true };
  if (idx > -1) out[idx] = featured; else out.push(featured);
  while (out.length > TARGET) { const k = Math.floor(r() * out.length); if (!out[k].featured) out.splice(k, 1); }
  out.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  return out;
})();
