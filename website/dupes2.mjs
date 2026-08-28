import { chromium } from "playwright";

/**
 * Semantic repetition audit. dupes.mjs finds identical strings; this finds the
 * same POINT made twice in different words, which is the kind of repetition a
 * reader actually notices.
 *
 *   A. sentence pairs above a Jaccard similarity threshold on content words
 *   B. repeated 3-word phrases across the site, ranked
 *   C. repeated CLAIMS — how many times each core promise is asserted
 */
const PAGES = ["/", "/parents", "/coaches", "/our-story", "/safety", "/faq", "/signup", "/questions/before-a-530-practice"];

const PROBE = () =>
  [...document.querySelectorAll("p,li,h1,h2,h3,h4,dd,span.coach-trust__p,figcaption")]
    .filter((el) => !el.closest("header") && !el.closest("footer") && !el.closest(".sticky-bar") && !el.closest(".sheet"))
    .map((el) => {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
      return (el.children.length ? own : (el.textContent || "").trim()).replace(/\s+/g, " ");
    })
    .filter((t) => t.length > 30);

const STOP = new Set(("a an the and or but of to in on for with at by from is are was were be been being it its this that these those you your yours " +
  "they them their we us our as so if then than can could will would do does did not no also just what when who how any every each one two " +
  "there here about into out up down over under more most some all which while because s t re ve").split(/\s+/));
const words = (s) => s.toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter((w) => w.length > 2 && !STOP.has(w));
const jac = (a, b) => {
  const A = new Set(a), B = new Set(b);
  let i = 0; for (const x of A) if (B.has(x)) i++;
  return i / (A.size + B.size - i);
};

const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const rows = [];
for (const u of PAGES) {
  const p = await ctx.newPage();
  await p.goto("http://localhost:3210" + u, { waitUntil: "networkidle" });
  const ts = await p.evaluate(PROBE);
  const seen = new Set();
  for (const t of ts) { const k = t.toLowerCase(); if (seen.has(k)) continue; seen.add(k); rows.push({ page: u, t, w: words(t) }); }
  await p.close();
}
await b.close();

console.log(`Scanned ${rows.length} distinct text blocks across ${PAGES.length} pages.\n`);

console.log("========== A. SAME POINT, DIFFERENT WORDS (Jaccard >= 0.42) ==========");
const pairs = [];
for (let i = 0; i < rows.length; i++)
  for (let j = i + 1; j < rows.length; j++) {
    if (rows[i].w.length < 5 || rows[j].w.length < 5) continue;
    if (rows[i].t.toLowerCase() === rows[j].t.toLowerCase()) continue;
    const s = jac(rows[i].w, rows[j].w);
    if (s >= 0.42) pairs.push({ s, a: rows[i], b: rows[j] });
  }
pairs.sort((x, y) => y.s - x.s).forEach((p) => {
  console.log(`\n  ${(p.s * 100).toFixed(0)}%  ${p.a.page}  vs  ${p.b.page}`);
  console.log(`     "${p.a.t.slice(0, 105)}"`);
  console.log(`     "${p.b.t.slice(0, 105)}"`);
});
if (!pairs.length) console.log("  none");

console.log("\n\n========== B. REPEATED 3-WORD PHRASES (>=3 occurrences) ==========");
const grams = new Map();
for (const r of rows) {
  const w = r.w;
  for (let i = 0; i + 2 < w.length; i++) {
    const g = w.slice(i, i + 3).join(" ");
    if (!grams.has(g)) grams.set(g, []);
    grams.get(g).push(r.page);
  }
}
[...grams.entries()]
  .filter(([, v]) => v.length >= 3)
  .sort((a, c) => c[1].length - a[1].length)
  .slice(0, 30)
  .forEach(([g, v]) => console.log(`  ${String(v.length).padStart(2)}x  "${g}"   ${[...new Set(v)].join(", ")}`));

console.log("\n\n========== C. HOW OFTEN EACH CLAIM IS ASSERTED ==========");
const CLAIMS = {
  "team-level only / never individual data": /team[- ]level|individual athlete|any one athlete|never sees|never shown|not monitor/i,
  "no calories / no weight / no BMI": /calorie|body composition|\bbmi\b|weight or body|no weight/i,
  "parents set it up / nothing for you to manage": /parents set it up|nothing new to manage|nothing for you to maintain|no roster|families set up/i,
  "built around your existing schedule": /schedule you (have )?already|around the schedule|already planned|actual (training|soccer) schedule|club calendar/i,
  "written by a Registered Dietitian": /registered dietitian|\bRDN\b|MS, RDN/i,
  "three minutes / quick setup": /three minutes|four minutes|couple of taps|in seconds|one tap/i,
  "not medical nutrition therapy": /not medical nutrition therapy|medical disclaimer/i,
  "practices, games and tournament weekends": /tournament weekend|practices, games|games and tournament/i,
  "waitlist / not open yet": /waitlist|not open yet|when it opens|early access/i,
};
for (const [name, re] of Object.entries(CLAIMS)) {
  const hits = rows.filter((r) => re.test(r.t));
  const byPage = new Map();
  hits.forEach((h) => byPage.set(h.page, (byPage.get(h.page) || 0) + 1));
  console.log(`\n  ${String(hits.length).padStart(2)}x  ${name}`);
  console.log(`        ${[...byPage.entries()].map(([p, n]) => `${p} (${n})`).join("  ")}`);
}
