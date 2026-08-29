import { chromium } from "playwright";

/**
 * Performance audit. Measures what a visitor actually downloads and how long
 * the page takes to become useful — not what the files weigh on disk.
 *
 * The distinction matters here. next/image resizes and re-encodes every image
 * on the way out, so a 483KB PNG source and a 56KB WebP source can arrive as
 * the same optimised bytes. Source weight affects the container image and the
 * cold-start CPU, not the visitor. This measures the visitor.
 *
 * Per page: bytes by resource type, the LCP element and its timing, CLS, and
 * the largest individual responses.
 */
const PAGES = ["/", "/parents", "/coaches", "/our-story", "/safety", "/faq", "/signup"];

const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });

for (const [w, label, dsf] of [[1440, "desktop", 1], [390, "mobile", 2]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: 844 }, deviceScaleFactor: dsf });
  console.log(`\n\n################  ${label} (${w}px)  ################`);
  const totals = { doc: 0, js: 0, css: 0, img: 0, font: 0, other: 0 };

  for (const u of PAGES) {
    const p = await ctx.newPage();
    const by = { doc: 0, js: 0, css: 0, img: 0, font: 0, other: 0 };
    const big = [];

    /* transferSize from Resource Timing, not content-length. Next serves the
       HTML and the JS chunks gzipped and chunked, so content-length is absent
       on exactly the responses that matter most — measuring it reported 0KB of
       JavaScript on a page that ships React. */
    await p.goto("http://localhost:3210" + u, { waitUntil: "networkidle" });

    const res = await p.evaluate(() => performance.getEntriesByType("resource")
      .map((r) => ({ n: r.name, t: r.initiatorType, size: r.transferSize || r.encodedBodySize || 0 }))
      .concat([{ n: location.href, t: "document", size: (performance.getEntriesByType("navigation")[0] || {}).transferSize || 0 }]));
    for (const r of res) {
      const k = r.t === "document" || /\/$|\/[a-z-]+$/.test(new URL(r.n).pathname) && r.t === "navigation" ? "doc"
        : /\.js(\?|$)/.test(r.n) || r.t === "script" ? "js"
        : /\.css(\?|$)/.test(r.n) || r.t === "css" || r.t === "link" && /\.css/.test(r.n) ? "css"
        : /_next\/image|\.(webp|png|jpe?g|svg|avif)/.test(r.n) || r.t === "img" ? "img"
        : /woff|font/.test(r.n) ? "font" : "other";
      by[k] += r.size;
      big.push({ len: r.size, k, url: r.n.replace("http://localhost:3210", "") });
    }

    const vitals = await p.evaluate(() => new Promise((res) => {
      const out = { lcp: 0, lcpEl: "?", cls: 0, ttfb: 0, domReady: 0 };
      const nav = performance.getEntriesByType("navigation")[0];
      if (nav) { out.ttfb = Math.round(nav.responseStart); out.domReady = Math.round(nav.domContentLoadedEventEnd); }
      try {
        new PerformanceObserver((l) => {
          const e = l.getEntries().at(-1);
          out.lcp = Math.round(e.startTime);
          const el = e.element;
          out.lcpEl = el ? `${el.tagName}${el.className ? "." + String(el.className).split(" ")[0] : ""}${el.currentSrc ? " " + el.currentSrc.split("/").pop().slice(0, 34) : ""}` : "?";
        }).observe({ type: "largest-contentful-paint", buffered: true });
        new PerformanceObserver((l) => {
          for (const e of l.getEntries()) if (!e.hadRecentInput) out.cls += e.value;
        }).observe({ type: "layout-shift", buffered: true });
      } catch { /* older engines */ }
      setTimeout(() => { out.cls = Math.round(out.cls * 1000) / 1000; res(out); }, 900);
    }));

    const tot = Object.values(by).reduce((a, c) => a + c, 0);
    for (const k of Object.keys(by)) totals[k] += by[k];
    const kb = (n) => (n / 1024).toFixed(0).padStart(4);
    console.log(`\n${u}`);
    console.log(`  transfer ${kb(tot)}KB   doc ${kb(by.doc)}  js ${kb(by.js)}  css ${kb(by.css)}  img ${kb(by.img)}  font ${kb(by.font)}`);
    console.log(`  LCP ${String(vitals.lcp).padStart(4)}ms  CLS ${vitals.cls}   TTFB ${vitals.ttfb}ms   element: ${vitals.lcpEl}`);
    big.sort((a, c) => c.len - a.len).slice(0, 3).forEach((x) =>
      console.log(`     ${(x.len / 1024).toFixed(0).padStart(4)}KB ${x.k.padEnd(4)} ${decodeURIComponent(x.url).slice(0, 76)}`));
    await p.close();
  }

  const grand = Object.values(totals).reduce((a, c) => a + c, 0);
  console.log(`\n  ---- ${label} across ${PAGES.length} pages: ${(grand / 1024).toFixed(0)}KB ----`);
  Object.entries(totals).forEach(([k, v]) => v && console.log(`       ${k.padEnd(6)} ${(v / 1024).toFixed(0).padStart(5)}KB  ${Math.round((v / grand) * 100)}%`));
  await ctx.close();
}
await b.close();
