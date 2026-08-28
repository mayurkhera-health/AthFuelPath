import { chromium } from "playwright";

/**
 * Repetition audit. Extracts every visible text block on every page, then
 * reports:
 *   A. exact strings that appear more than once (across pages and within one)
 *   B. near-duplicate sentences (same content words, different wording)
 *   C. every call to action, with its label and where it sits
 *
 * Text is taken from leaf elements only, so a wrapper's concatenated text is
 * not counted as a separate string.
 */
const PAGES = ["/", "/parents", "/coaches", "/our-story", "/safety", "/faq", "/signup", "/questions/before-a-530-practice"];

const PROBE = () => {
  const blocks = [];
  const ctas = [];
  const seen = new Set();
  const chrome = (el) => !!(el.closest("header") || el.closest("footer") || el.closest(".sticky-bar") || el.closest(".sheet"));

  document.querySelectorAll("p,span,li,h1,h2,h3,h4,b,strong,small,label,legend,figcaption,dt,dd,a,button,summary").forEach((el) => {
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
    const t = (el.children.length ? own : (el.textContent || "").trim()).replace(/\s+/g, " ");
    if (!t || t.length < 12) return;
    const key = t.toLowerCase();
    if (seen.has(key + el.tagName)) return;
    seen.add(key + el.tagName);
    blocks.push({ t, tag: el.tagName, chrome: chrome(el), cls: (typeof el.className === "string" ? el.className : "").split(/\s+/)[0] || "" });
  });

  document.querySelectorAll("a.btn, button.btn, a[href='/signup'], a[href*='coach-access'], .tlink").forEach((el) => {
    const t = (el.textContent || "").trim().replace(/\s+/g, " ");
    if (!t) return;
    ctas.push({ t, href: el.getAttribute("href") || "(button)", chrome: chrome(el) });
  });
  return { blocks, ctas };
};

/* content words only, so "Join the waitlist" and "join our waitlist" collide */
const STOP = new Set("a an the and or but of to in on for with at by from is are was were be been it its this that these those you your their they them we us our as so if then than can could will would do does did not no your you're".split(" "));
const fingerprint = (s) =>
  s.toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter((w) => w && !STOP.has(w)).sort().join(" ");

const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const all = [];
const allCtas = [];
for (const u of PAGES) {
  const p = await ctx.newPage();
  await p.goto("http://localhost:3210" + u, { waitUntil: "networkidle" });
  const r = await p.evaluate(PROBE);
  r.blocks.forEach((x) => all.push({ ...x, page: u }));
  r.ctas.forEach((x) => allCtas.push({ ...x, page: u }));
  await p.close();
}
await b.close();

/* ---- A. exact repeats (page chrome excluded, it is supposed to repeat) ---- */
const exact = new Map();
for (const x of all.filter((x) => !x.chrome)) {
  const k = x.t.toLowerCase();
  if (!exact.has(k)) exact.set(k, []);
  exact.get(k).push(x);
}
console.log("========== A. EXACT REPEATS (body content, chrome excluded) ==========");
[...exact.entries()]
  .filter(([, v]) => v.length > 1)
  .sort((a, b2) => b2[1].length - a[1].length)
  .forEach(([, v]) => {
    console.log(`\n  ${v.length}x  "${v[0].t.slice(0, 110)}"`);
    console.log(`        ${v.map((x) => `${x.page}${x.cls ? " ." + x.cls : ""}`).join("  |  ")}`);
  });

/* ---- B. near-duplicates ---- */
const fp = new Map();
for (const x of all.filter((x) => !x.chrome && x.t.length >= 24)) {
  const k = fingerprint(x.t);
  if (k.split(" ").length < 4) continue;
  if (!fp.has(k)) fp.set(k, []);
  fp.get(k).push(x);
}
console.log("\n\n========== B. NEAR-DUPLICATES (same content words) ==========");
[...fp.values()]
  .filter((v) => v.length > 1 && new Set(v.map((x) => x.t.toLowerCase())).size > 1)
  .forEach((v) => {
    console.log("");
    v.forEach((x) => console.log(`  ${x.page.padEnd(34)} "${x.t.slice(0, 100)}"`));
  });

/* ---- C. CTA inventory ---- */
console.log("\n\n========== C. CTA INVENTORY ==========");
const byPage = new Map();
for (const c of allCtas) {
  if (!byPage.has(c.page)) byPage.set(c.page, []);
  byPage.get(c.page).push(c);
}
for (const [page, list] of byPage) {
  const body = list.filter((c) => !c.chrome);
  console.log(`\n${page}  —  ${list.length} total, ${body.length} in body content`);
  const counts = new Map();
  for (const c of list) {
    const k = `${c.t} -> ${c.href}${c.chrome ? "   [chrome]" : ""}`;
    counts.set(k, (counts.get(k) || 0) + 1);
  }
  [...counts.entries()].forEach(([k, n]) => console.log(`   ${n > 1 ? n + "x " : "   "}${k}`));
}
