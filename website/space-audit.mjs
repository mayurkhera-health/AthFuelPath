import { chromium } from "playwright";

/**
 * Finds dead vertical space, mechanically, so a whitespace pass is a list of
 * measurements rather than an argument about screenshots.
 *
 * Four things it looks for:
 *
 *  1. COLUMN MISMATCH — a grid row whose tallest and shortest children differ by
 *     a lot. This is the Our Story hero bug: a 841px portrait beside 363px of
 *     copy leaves 478px of nothing, and no align-items value can remove it.
 *  2. GAP — an unusually large vertical distance between two consecutive
 *     siblings, relative to the median gap in that same container.
 *  3. SECTION SLACK — padding at the top or bottom of a section that no content
 *     is using, over and above the declared padding.
 *  4. SHORT SECTION — a section whose content occupies less than half its
 *     height, which usually means one of the above.
 */
const PAGES = ["/", "/coaches", "/our-story", "/safety", "/faq", "/signup", "/questions/before-a-530-practice", "/privacy"];
const WIDTHS = [390, 1440];

const PROBE = () => {
  const out = { cols: [], gaps: [], sections: [] };
  const box = (el) => el.getBoundingClientRect();
  const named = (el) => (typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : el.tagName.toLowerCase());

  /* 1 — grid/flex rows whose children are wildly different heights */
  document.querySelectorAll("*").forEach((el) => {
    const cs = getComputedStyle(el);
    if (!/grid|flex/.test(cs.display)) return;
    const kids = [...el.children].filter((k) => box(k).height > 8);
    if (kids.length < 2) return;
    const hs = kids.map((k) => box(k).height);
    const tops = kids.map((k) => Math.round(box(k).top));
    // same row only: all children start within 24px of each other
    if (Math.max(...tops) - Math.min(...tops) > 24) return;
    const diff = Math.max(...hs) - Math.min(...hs);
    if (diff >= 120) {
      out.cols.push({ sel: named(el), diff: Math.round(diff), hs: hs.map(Math.round).join(" vs ") });
    }
  });

  /* 2 — outsized gaps between consecutive siblings */
  document.querySelectorAll("section, .container, .section-head, main > div").forEach((el) => {
    const kids = [...el.children].filter((k) => box(k).height > 8);
    if (kids.length < 2) return;
    const gaps = [];
    for (let i = 1; i < kids.length; i++) gaps.push(Math.round(box(kids[i]).top - box(kids[i - 1]).bottom));
    const sorted = [...gaps].sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    gaps.forEach((g, i) => {
      if (g >= 96 && g > median * 2.2) {
        out.gaps.push({ sel: named(el), gap: g, median, after: named(kids[i]) });
      }
    });
  });

  /* 3 & 4 — section padding nothing is using, and mostly-empty sections */
  document.querySelectorAll("section, .closing").forEach((s) => {
    const r = box(s);
    if (r.height < 40) return;
    const kids = [...s.querySelectorAll("*")].filter((e) => {
      const b = box(e);
      return b.height > 6 && b.width > 6 && ((e.textContent || "").trim() || e.tagName === "IMG" || e.tagName === "SVG");
    });
    if (!kids.length) return;
    const top = Math.min(...kids.map((e) => box(e).top));
    const bot = Math.max(...kids.map((e) => box(e).bottom));
    const cs = getComputedStyle(s);
    const declaredT = parseFloat(cs.paddingTop), declaredB = parseFloat(cs.paddingBottom);
    const slackT = Math.round(top - r.top - declaredT);
    const slackB = Math.round(r.bottom - bot - declaredB);
    const fill = (bot - top) / r.height;
    if (slackT > 24 || slackB > 24 || fill < 0.55) {
      out.sections.push({
        sel: named(s), h: Math.round(r.height),
        pad: `${Math.round(declaredT)}/${Math.round(declaredB)}`,
        slack: `${slackT}/${slackB}`, fill: Math.round(fill * 100),
      });
    }
  });
  return out;
};

const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
for (const w of WIDTHS) {
  const ctx = await b.newContext({ viewport: { width: w, height: 900 } });
  console.log(`\n\n######################  ${w}px  ######################`);
  for (const u of PAGES) {
    const p = await ctx.newPage();
    await p.goto("http://localhost:3210" + u, { waitUntil: "networkidle" });
    await p.addStyleTag({ content: "html{scroll-behavior:auto!important}" });
    await p.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 500) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 40)); } window.scrollTo(0, 0); });
    await p.waitForTimeout(400);
    const r = await p.evaluate(PROBE);
    const total = r.cols.length + r.gaps.length + r.sections.length;
    console.log(`\n===== ${u} ${total ? `— ${total} findings` : "— clean"}`);
    for (const c of r.cols) console.log(`  COLUMN MISMATCH ${c.diff}px   ${c.sel}   heights ${c.hs}`);
    for (const g of r.gaps) console.log(`  GAP ${g.gap}px (median ${g.median}) in ${g.sel} after ${g.after}`);
    for (const s of r.sections) console.log(`  SECTION ${s.sel} h=${s.h} pad=${s.pad} extra-slack=${s.slack} content-fill=${s.fill}%`);
    await p.close();
  }
  await ctx.close();
}
await b.close();
