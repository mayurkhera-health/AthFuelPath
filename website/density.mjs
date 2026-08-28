import { chromium } from "playwright";

/**
 * Ink density: what share of a page's vertical space actually carries something.
 *
 * space-audit.mjs looks for slack BEYOND the declared padding and found almost
 * none — which is the point. The airiness is the declared rhythm itself: the
 * section padding, the section-head margins, the gaps between blocks. This
 * measures that directly.
 *
 * For each page it walks every pixel row of the document and asks whether any
 * leaf element (text, image, rule, bar) covers it. Rows nothing covers are dead.
 * It then reports the biggest contiguous dead bands and where they sit, so a
 * tightening pass targets the worst offenders rather than shaving every token.
 */
const PAGES = ["/", "/coaches", "/our-story", "/safety", "/faq", "/signup", "/questions/before-a-530-practice"];

const PROBE = () => {
  const H = Math.ceil(document.documentElement.scrollHeight);
  const covered = new Uint8Array(H + 2);
  const label = new Array(H + 2);

  const name = (el) => {
    let n = el;
    for (let i = 0; i < 4 && n; i++) {
      if (typeof n.className === "string" && n.className.trim()) return "." + n.className.trim().split(/\s+/)[0];
      n = n.parentElement;
    }
    return el.tagName.toLowerCase();
  };

  document.querySelectorAll("*").forEach((el) => {
    if (el.children.length && !/^(IMG|SVG|HR)$/.test(el.tagName)) {
      // only leaves carry ink; a wrapper's box is not content
      const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      if (!hasText) return;
    }
    const r = el.getBoundingClientRect();
    if (r.height < 1 || r.width < 1) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || Number(cs.opacity) < 0.05) return;
    const top = Math.max(0, Math.floor(r.top + window.scrollY));
    const bot = Math.min(H, Math.ceil(r.bottom + window.scrollY));
    for (let y = top; y < bot; y++) { covered[y] = 1; if (!label[y]) label[y] = name(el); }
  });

  // contiguous dead bands
  const bands = [];
  let start = null;
  for (let y = 0; y <= H; y++) {
    if (!covered[y]) { if (start === null) start = y; }
    else if (start !== null) {
      if (y - start >= 56) bands.push({ y: start, h: y - start, after: label[start - 1] || "?", before: label[y] || "?" });
      start = null;
    }
  }
  const ink = covered.reduce((a, c) => a + c, 0);
  return { H, ink, dead: H - ink, bands: bands.sort((a, b) => b.h - a.h) };
};

const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
for (const w of [1440, 390]) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 } });
  console.log(`\n############### ${w}px ###############`);
  for (const u of PAGES) {
    const p = await ctx.newPage();
    await p.goto("http://localhost:3210" + u, { waitUntil: "networkidle" });
    await p.addStyleTag({ content: "html{scroll-behavior:auto!important}" });
    await p.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 40)); } window.scrollTo(0, 0); });
    await p.waitForTimeout(300);
    const r = await p.evaluate(PROBE);
    const pct = Math.round((r.dead / r.H) * 100);
    const banded = r.bands.reduce((a, x) => a + x.h, 0);
    console.log(`\n${u}  height ${r.H}px · dead ${r.dead}px (${pct}%) · ${r.bands.length} bands ≥56px totalling ${banded}px`);
    for (const x of r.bands.slice(0, 8)) console.log(`   ${String(x.h).padStart(4)}px at y=${String(x.y).padStart(5)}   between ${x.after} → ${x.before}`);
    await p.close();
  }
  await ctx.close();
}
await b.close();
