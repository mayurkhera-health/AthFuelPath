import { chromium } from "playwright";

/* WCAG relative luminance + contrast, measured against the nearest ancestor
   that actually paints a background — not against an assumed token. */
const IN_PAGE = () => {
  const lum = ([r, g, b]) => {
    const f = (c) => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const rgb = (s) => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
  const bgOf = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = getComputedStyle(n).backgroundColor;
      const p = rgb(c);
      const a = (c.match(/[\d.]+/g) || [])[3];
      if (p.length === 3 && (a === undefined || Number(a) > 0.9)) return p;
      n = n.parentElement;
    }
    return [255, 255, 255];
  };
  const out = [];
  const seen = new Set();
  document.querySelectorAll("p,span,li,a,button,small,label,b,strong,h1,h2,h3,legend,figcaption").forEach((el) => {
    if (el.children.length) return;
    const t = (el.textContent || "").trim();
    if (!t) return;
    const cs = getComputedStyle(el);
    const fs = parseFloat(cs.fontSize);
    const bold = parseInt(cs.fontWeight, 10) >= 700;
    const fg = rgb(cs.color), bg = bgOf(el);
    const L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    // "large text" gets 3:1; everything else 4.5:1
    const large = fs >= 24 || (bold && fs >= 18.66);
    const need = large ? 3 : 4.5;
    const key = `${cs.color}|${bg.join(",")}|${Math.round(fs)}|${bold}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      ok: ratio >= need, ratio: Math.round(ratio * 100) / 100, need,
      fs: Math.round(fs), bold, cls: (el.className || el.tagName).toString().slice(0, 30),
      fg: cs.color, bg: `rgb(${bg.join(", ")})`, text: t.slice(0, 30),
    });
  });
  return out;
};

const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
let bad = 0;
for (const u of (process.argv.slice(2).length ? process.argv.slice(2) : ["/coaches"])) {
  const p = await ctx.newPage();
  await p.goto("http://localhost:3210" + u, { waitUntil: "networkidle" });
  const rows = await p.evaluate(IN_PAGE);
  const fails = rows.filter((r) => !r.ok);
  console.log(`\n===== ${u} — ${rows.length} distinct text/background pairs, ${fails.length} below threshold =====`);
  for (const r of fails) {
    bad++;
    console.log(`  ${r.ratio}:1 (needs ${r.need}) ${r.fs}px${r.bold ? " bold" : ""}  ${r.fg} on ${r.bg}  .${r.cls}  "${r.text}"`);
  }
  await p.close();
}
await b.close();
console.log(bad ? `\n${bad} FAIL` : "\nCONTRAST ALL PASS");
